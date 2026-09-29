"""Read and validate the agent sources in agent_sources/.

Each agent is one Markdown file, agent_sources/<name>.md, whose front matter
holds everything about the agent and whose body holds its instructions.
load_agents turns every source into an Agent, or reports every problem found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from agent_front_matter import SourceError, parse_front_matter

SOURCES_DIR = "agent_sources"

# The hand-maintained agent index sits beside the sources and is not an agent.
INDEX_FILENAME = "README.md"

# The only source format version this reader understands. A source declares it
# with `schema: 1`, so a reader such as CAI can refuse a version it does not know.
SCHEMA_VERSION = 1

# Every tool an agent can target. CAI reads the sources itself; the others
# get generated files.
TOOLS = ("claude", "codex", "cursor", "hermes", "cai")

# ---------------------------------------------------------------------------
# What each tool supports
# ---------------------------------------------------------------------------

# A source names a tier rather than a model; agent_render.TIER_MODELS says what
# each tier means for each tool.
TIERS = ("frontier", "strong", "standard", "fast")

# Reasoning effort levels, named as Claude Code names them.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# The colors the repository's agent authoring contract allows for Claude Code.
CLAUDE_COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")

# Claude Code tool names a source may list under `tools`. Only Claude Code
# enforces the list; the other tools see it as a comment.
KNOWN_TOOLS = (
    "Agent",
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "Skill",
    "Task",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
)

# Tools that change files, which a read-only agent must not list.
WRITE_TOOLS = ("Edit", "NotebookEdit", "Write")

# Settings a per-tool block may carry, and what each value must be. A tuple
# lists the allowed strings; int, bool, and list name the required type.
TOOL_SETTINGS: dict[str, dict[str, object]] = {
    "claude": {
        "permissionMode": (
            "default",
            "manual",
            "acceptEdits",
            "plan",
            "auto",
            "bypassPermissions",
            "dontAsk",
        ),
        "maxTurns": int,
        "background": bool,
        "isolation": ("worktree",),
        "memory": ("user", "project", "local"),
    },
    "codex": {},
    "cursor": {"is_background": bool},
    "hermes": {},
    # CAI reads these itself; they are validated here so a typo fails `just ci`.
    "cai": {
        "selection": ("auto", "lock"),
        "max_steps": int,
        "max_turns": int,
        "ingest_personas": list,
        "mcp_servers": list,
    },
}

# ---------------------------------------------------------------------------
# Source file rules
# ---------------------------------------------------------------------------

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

# The body section the generator adds for tools that cannot preload skills. A
# source must not write it, whether or not the agent has skills today, so
# adding a skill later never turns a valid source into an invalid one.
SKILLS_HEADING = "## Skill Dependencies"

REQUIRED_KEYS = ("schema", "name", "description")
TOP_LEVEL_KEYS = (
    "schema",
    "name",
    "description",
    "model",
    "effort",
    "color",
    "readonly",
    "tools",
    "skills",
    "suggested_skills",
    "exclude",
    # A key named after a tool holds that tool's own settings.
    *TOOLS,
)


@dataclass
class Agent:
    """One validated agent source, holding exactly what the renderers need."""

    name: str
    path: str  # the source path relative to the repository, for messages
    description: str
    body: str
    tier: str | None = None
    # A tool's own model; a string for most tools, a preference list for CAI.
    models: dict[str, object] = field(default_factory=dict)
    effort: str | None = None
    color: str | None = None
    readonly: bool = False
    # None means the agent inherits every tool; a list is an allowlist.
    tools: list[str] | None = None
    skills: list[str] = field(default_factory=list)
    suggested_skills: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    # Per-tool settings blocks, keyed by tool name.
    settings: dict[str, dict[str, object]] = field(default_factory=dict)


def load_agent(path: Path, skills_root: Path) -> Agent:
    """Read one source file, check every key, and return the Agent it describes."""
    where = f"{SOURCES_DIR}/{path.name}"
    text = _read_source_text(path, where)
    data, body = parse_front_matter(text, where)

    _check_keys(data, where)
    name = _check_name(data["name"], path, where)
    description = _check_description(data["description"], where)
    _check_body(body, where)

    agent = Agent(name=name, path=where, description=description, body=body)
    agent.tier, agent.models = _read_model(data.get("model"), f"{where}: model")
    agent.effort = _read_effort(data, where)
    agent.exclude = _read_exclude(data, where)
    agent.color = _read_color(data, agent.exclude, where)
    agent.readonly, agent.tools = _read_restrictions(data, where)
    agent.skills, agent.suggested_skills = _read_skills(data, skills_root, where)
    agent.settings = {
        tool: _read_tool_settings(tool, data[tool], f"{where}: {tool}")
        for tool in TOOLS
        if tool in data
    }
    return agent


def _read_source_text(path: Path, where: str) -> str:
    """Read a source as UTF-8 text with LF line endings."""
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError(f"{where}: not valid UTF-8") from error
    # A Windows checkout with Git's core.autocrlf gives CRLF line endings.
    # Generated files always use LF, so normalize here.
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise SourceError(f"{where}: contains a carriage return outside a CRLF line ending")
    return text


def _check_keys(data: dict[str, object], where: str) -> None:
    unknown = [key for key in data if key not in TOP_LEVEL_KEYS]
    if unknown:
        raise SourceError(f"{where}: unknown key(s) {', '.join(unknown)}")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise SourceError(f"{where}: missing required key(s) {', '.join(missing)}")
    if data["schema"] != SCHEMA_VERSION:
        raise SourceError(f"{where}: schema must be {SCHEMA_VERSION}")


def _check_name(value: object, path: Path, where: str) -> str:
    name = _require_string(value, f"{where}: name")
    if not NAME_PATTERN.match(name) or len(name) > MAX_NAME_LENGTH:
        raise SourceError(f"{where}: name must be kebab-case and at most {MAX_NAME_LENGTH} characters")
    if name != path.stem:
        raise SourceError(f"{where}: name '{name}' must match the file name")
    return name


def _check_description(value: object, where: str) -> str:
    description = _require_string(value, f"{where}: description")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise SourceError(f"{where}: description exceeds {MAX_DESCRIPTION_LENGTH} characters")
    return description


def _check_body(body: str, where: str) -> None:
    _require_printable(body, f"{where}: body", allow_newlines=True)
    if not body.startswith("# "):
        raise SourceError(f"{where}: body must open with an H1 heading")
    if not body.endswith("\n") or body.endswith("\n\n"):
        raise SourceError(f"{where}: body must end with exactly one newline")
    if any(line.strip() == SKILLS_HEADING for line in body.split("\n")):
        raise SourceError(f"{where}: body must not have a '{SKILLS_HEADING}' heading; the generator adds that section")


def _read_model(value: object, where: str) -> tuple[str | None, dict[str, object]]:
    """Read `model`: either a tier, or a block with an optional tier and per-tool models."""
    if value is None:
        return None, {}

    if isinstance(value, str):
        if value not in TIERS:
            raise SourceError(
                f"{where}: '{value}' is not a tier ({', '.join(TIERS)}); "
                "name a tool's model inside a model block instead"
            )
        return value, {}

    if not isinstance(value, dict):
        raise SourceError(f"{where}: must be a tier or a mapping")

    tier = None
    models: dict[str, object] = {}
    for key, item in value.items():
        if key == "tier":
            if item not in TIERS:
                raise SourceError(f"{where}.tier: must be one of {', '.join(TIERS)}")
            tier = item
        elif key == "hermes":
            raise SourceError(f"{where}.hermes: Hermes personalities cannot set a model")
        elif key == "cai":
            # CAI takes an ordered preference list; a single model is a list of one.
            models[key] = _require_string_list(item, f"{where}.cai")
        elif key in TOOLS:
            models[key] = _require_string(item, f"{where}.{key}")
        else:
            raise SourceError(f"{where}.{key}: not 'tier' or a tool name ({', '.join(TOOLS)})")
    return tier, models


def _read_effort(data: dict[str, object], where: str) -> str | None:
    if "effort" not in data:
        return None
    effort = data["effort"]
    if effort not in EFFORT_LEVELS:
        raise SourceError(f"{where}: effort must be one of {', '.join(EFFORT_LEVELS)}")
    return effort


def _read_exclude(data: dict[str, object], where: str) -> list[str]:
    exclude = _require_string_list(data.get("exclude", []), f"{where}: exclude")
    unknown = [tool for tool in exclude if tool not in TOOLS]
    if unknown:
        raise SourceError(f"{where}: exclude names unknown tool(s) {', '.join(unknown)}")
    return exclude


def _read_color(data: dict[str, object], exclude: list[str], where: str) -> str | None:
    """Read `color`, which only Claude Code uses and which it requires."""
    if "color" not in data:
        if "claude" in exclude:
            return None
        raise SourceError(f"{where}: color is required for the Claude Code agent")
    color = data["color"]
    if color not in CLAUDE_COLORS:
        raise SourceError(f"{where}: color must be one of {', '.join(CLAUDE_COLORS)}")
    return color


def _read_restrictions(data: dict[str, object], where: str) -> tuple[bool, list[str] | None]:
    """Read `readonly` and `tools`, and check that they agree."""
    readonly = data.get("readonly", False)
    if not isinstance(readonly, bool):
        raise SourceError(f"{where}: readonly must be true or false")

    tools = None
    if "tools" in data:
        tools = _require_string_list(data["tools"], f"{where}: tools")
        unknown = [tool for tool in tools if tool not in KNOWN_TOOLS]
        if unknown:
            raise SourceError(f"{where}: unknown tool(s) {', '.join(unknown)}")

    if readonly:
        # Claude Code has no read-only flag; its tool allowlist is what makes an
        # agent read-only there, so a read-only agent must have one.
        if tools is None:
            raise SourceError(
                f"{where}: a read-only agent must list its tools, which is how Claude Code enforces it"
            )
        writers = [tool for tool in tools if tool in WRITE_TOOLS]
        if writers:
            raise SourceError(f"{where}: a read-only agent cannot list {', '.join(writers)}")
    return readonly, tools


def _read_skills(
    data: dict[str, object], skills_root: Path, where: str
) -> tuple[list[str], list[str]]:
    """Read `skills` and `suggested_skills`, which must name existing, distinct skills."""
    required = _require_skill_names(data.get("skills", []), f"{where}: skills", skills_root)
    suggested = _require_skill_names(
        data.get("suggested_skills", []), f"{where}: suggested_skills", skills_root
    )
    both = sorted(set(required) & set(suggested))
    if both:
        raise SourceError(f"{where}: skill(s) {', '.join(both)} are both required and suggested")
    return required, suggested


def _read_tool_settings(tool: str, value: object, where: str) -> dict[str, object]:
    """Check a per-tool block against the settings that tool supports."""
    if not isinstance(value, dict):
        raise SourceError(f"{where}: must be a mapping of {tool}-only settings")
    supported = TOOL_SETTINGS[tool]
    for key, item in value.items():
        rule = supported.get(key)
        if rule is None:
            known = ", ".join(supported) or "none yet"
            raise SourceError(f"{where}.{key}: not a {tool} setting (supported: {known})")
        _check_setting(item, rule, f"{where}.{key}")
    return dict(value)


def _check_setting(value: object, rule: object, where: str) -> None:
    """Check one setting's value against its rule from TOOL_SETTINGS."""
    if isinstance(rule, tuple):
        if value not in rule:
            raise SourceError(f"{where}: must be one of {', '.join(rule)}")
    elif rule is int:
        # bool is a subclass of int in Python, so exclude it explicitly.
        if not isinstance(value, int) or isinstance(value, bool):
            raise SourceError(f"{where}: must be an integer")
    elif rule is bool:
        if not isinstance(value, bool):
            raise SourceError(f"{where}: must be true or false")
    elif rule is list:
        _require_string_list(value, where)


def _require_printable(value: str, where: str, *, allow_newlines: bool = False) -> None:
    """Reject control and other non-printable characters, which no target format handles alike."""
    for char in value:
        if char == "\n" and allow_newlines:
            continue
        if not char.isprintable():
            raise SourceError(f"{where}: contains unsupported character U+{ord(char):04X}")


def _require_string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceError(f"{where}: must be a non-empty string")
    _require_printable(value, where)
    return value


def _require_string_list(value: object, where: str) -> list[str]:
    """Return a list of distinct non-empty strings; a single string counts as a list of one."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise SourceError(f"{where}: must be a list of non-empty strings")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SourceError(f"{where}: must be a list of non-empty strings")
        _require_printable(item, where)
    if len(set(value)) != len(value):
        raise SourceError(f"{where}: lists an entry more than once")
    return list(value)


def _require_skill_names(value: object, where: str, skills_root: Path) -> list[str]:
    names = _require_string_list(value, where)
    for name in names:
        if not NAME_PATTERN.match(name):
            raise SourceError(f"{where}: '{name}' is not a kebab-case skill name")
        if not (skills_root / name / "SKILL.md").is_file():
            raise SourceError(f"{where}: skill '{name}' does not exist under skills/")
    return names


def load_agents(root: Path) -> list[Agent]:
    """Load every agent source under root, reporting every invalid one together."""
    sources = root / SOURCES_DIR
    if not sources.is_dir():
        raise SourceError(f"{SOURCES_DIR}/ not found under {root}")

    agents: list[Agent] = []
    problems: list[str] = []
    for path in sorted(sources.glob("*.md")):
        if path.name == INDEX_FILENAME:
            continue
        try:
            agents.append(load_agent(path, root / "skills"))
        except SourceError as error:
            problems.append(str(error))
    if problems:
        raise SourceError("\n".join(problems))
    return agents
