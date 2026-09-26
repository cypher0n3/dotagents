#!/usr/bin/env python3
"""Generate every tool's agent files from the sources in agent_sources/.

Each agent is one Markdown file, agent_sources/<name>.md, whose YAML front
matter holds everything about the agent and whose body holds its instructions.
This script renders that one source into Claude Code, Codex, and Cursor agents
and a Hermes personality under generated/, which is ignored by Git and rebuilt
from scratch on every run. CAI reads agent_sources/ directly and gets nothing
here.

How each tool spells each field lives in this file, not in the sources: the
model tier table, the key names, and the comments written where a tool cannot
enforce a restriction. The front matter is read with a small parser for the
documented YAML subset below, so this script needs only the standard library.

Exit status is 0 when every agent generated and 1 when any source is invalid,
in which case the existing generated/ directory is left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SOURCES_DIR = "agent_sources"
OUTPUT_DIR = "generated"
INDEX_FILENAME = "README.md"
SCHEMA_VERSION = 1

TOOLS = ("claude", "codex", "cursor", "hermes", "cai")
GENERATED_TOOLS = ("claude", "codex", "cursor", "hermes")
OUTPUT_PATHS = {
    "claude": "claude/agents/{name}.md",
    "codex": "codex/agents/{name}.toml",
    "cursor": "cursor/agents/{name}.md",
    "hermes": "hermes/personalities/{name}.yaml",
}

# What each model tier means for each tool. A tool missing from a tier falls
# back to its session's model. Hermes personalities cannot set a model, and CAI
# resolves its own models from agent_sources/.
TIERS = ("frontier", "strong", "standard", "fast")
TIER_MODELS = {
    "claude": {"frontier": "fable", "strong": "opus", "standard": "sonnet", "fast": "haiku"},
    "codex": {},
    "cursor": {},
}

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
CODEX_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}
CLAUDE_COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")
KNOWN_TOOLS = (
    "Agent", "Bash", "Edit", "Glob", "Grep", "NotebookEdit", "Read", "Skill", "Task", "TodoWrite",
    "WebFetch", "WebSearch", "Write",
)
WRITE_TOOLS = ("Edit", "NotebookEdit", "Write")

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

TOP_KEYS = (
    "schema", "name", "description", "model", "effort", "color", "readonly", "tools", "skills",
    "suggested_skills", "exclude", *TOOLS,
)
REQUIRED_KEYS = ("schema", "name", "description")

# Settings a per-tool block may carry, with the type each value must have.
# A tuple lists the allowed values of a string setting.
TOOL_BLOCKS: dict[str, dict[str, object]] = {
    "claude": {
        "permissionMode": ("default", "manual", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk"),
        "maxTurns": int,
        "background": bool,
        "isolation": ("worktree",),
        "memory": ("user", "project", "local"),
    },
    "codex": {},
    "cursor": {"is_background": bool},
    "hermes": {},
    # Read by CAI itself; validated here so a typo fails `just ci`.
    "cai": {
        "selection": ("auto", "lock"),
        "max_steps": int,
        "max_turns": int,
        "ingest_personas": list,
        "mcp_servers": list,
    },
}

SKILLS_HEADING = "## Skill Dependencies"
HEADER = "Generated from agent_sources/{name}.md by .ci_scripts/generate_agents.py; do not edit, changes are lost at the next generation."


class SourceError(Exception):
    """A problem with one source file."""


# --- front matter subset -----------------------------------------------------
#
# The supported subset is block mappings and block sequences nested by
# indentation, inline sequences ([a, b]), plain, single-quoted, and
# double-quoted scalars, integers, true and false, and full-line or trailing
# comments. Anchors, aliases, tags, block scalars, flow mappings, and multiple
# documents are rejected rather than guessed at.


@dataclass
class _Line:
    number: int
    indent: int
    text: str


def _strip_comment(text: str) -> str:
    """Remove a trailing comment that is not inside quotes."""
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote and not (quote == '"' and index and text[index - 1] == "\\"):
                quote = None
        elif char in "'\"" and (index == 0 or text[index - 1] in " [,:"):
            quote = char
        elif char == "#" and (index == 0 or text[index - 1] == " "):
            return text[:index].rstrip()
    return text.rstrip()


def _scalar(raw: str, where: str) -> object:
    raw = raw.strip()
    if not raw:
        raise SourceError(f"{where}: empty value")
    if raw[0] in "&*!|>{" or raw.startswith("%"):
        raise SourceError(f"{where}: unsupported YAML syntax {raw[:12]!r}")
    if raw[0] == '"':
        try:
            value = json.loads(raw)
        except ValueError as error:
            raise SourceError(f"{where}: invalid double-quoted string") from error
        if not isinstance(value, str):
            raise SourceError(f"{where}: invalid double-quoted string")
        return value
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise SourceError(f"{where}: unterminated single-quoted string")
        return raw[1:-1].replace("''", "'")
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.lower() in ("null", "~", "yes", "no", "on", "off", "y", "n", "true", "false"):
        raise SourceError(f"{where}: ambiguous value {raw!r}; quote it or use true or false")
    if re.fullmatch(r"-?[0-9]+", raw):
        return int(raw)
    return raw


def _inline_list(raw: str, where: str) -> list[object]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    items, current, quote = [], "", None
    for char in inner:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            current += char
        elif char == ",":
            items.append(current)
            current = ""
        elif char in "[]{}":
            raise SourceError(f"{where}: nested collections are not supported in an inline list")
        else:
            current += char
    items.append(current)
    return [_scalar(item, where) for item in items]


def _value(raw: str, where: str) -> object:
    raw = raw.strip()
    if raw.startswith("["):
        if not raw.endswith("]"):
            raise SourceError(f"{where}: unterminated inline list")
        return _inline_list(raw, where)
    return _scalar(raw, where)


def _parse_block(lines: list[_Line], start: int, indent: int, where: str) -> tuple[object, int]:
    """Parse the mapping or sequence whose lines sit at exactly this indent."""
    first = lines[start]
    if first.text.startswith("- ") or first.text == "-":
        items: list[object] = []
        index = start
        while index < len(lines) and lines[index].indent == indent:
            line = lines[index]
            if not (line.text.startswith("- ") or line.text == "-"):
                raise SourceError(f"{where}:{line.number}: expected a list item")
            rest = line.text[2:].strip()
            if not rest:
                raise SourceError(f"{where}:{line.number}: nested blocks inside a list are not supported")
            items.append(_value(rest, f"{where}:{line.number}"))
            index += 1
        return items, index
    mapping: dict[str, object] = {}
    index = start
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        key, colon, rest = line.text.partition(":")
        if not colon or not KEY_PATTERN.match(key) or (rest and not rest.startswith(" ")):
            raise SourceError(f"{where}:{line.number}: expected 'key: value'")
        if key in mapping:
            raise SourceError(f"{where}:{line.number}: duplicate key '{key}'")
        rest = rest.strip()
        index += 1
        if rest:
            mapping[key] = _value(rest, f"{where}:{line.number}")
            continue
        if index < len(lines) and lines[index].indent > indent:
            mapping[key], index = _parse_block(lines, index, lines[index].indent, where)
        elif index < len(lines) and lines[index].indent == indent and lines[index].text.startswith("- "):
            # A sequence may sit at the same indent as its key.
            mapping[key], index = _parse_block(lines, index, indent, where)
        else:
            raise SourceError(f"{where}:{line.number}: '{key}' has no value")
    if index < len(lines) and lines[index].indent > indent:
        raise SourceError(f"{where}:{lines[index].number}: unexpected indentation")
    return mapping, index


def parse_front_matter(text: str, where: str) -> tuple[dict[str, object], str]:
    """Split a source file into its front matter mapping and its body."""
    if not text.startswith("---\n"):
        raise SourceError(f"{where}: must open with '---' front matter")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise SourceError(f"{where}: front matter is not closed with '---'")
    lines: list[_Line] = []
    for number, raw in enumerate(text[4:end].split("\n"), start=2):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise SourceError(f"{where}:{number}: indent with spaces, not tabs")
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        lines.append(_Line(number, len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))
    if not lines:
        raise SourceError(f"{where}: front matter is empty")
    if lines[0].indent:
        raise SourceError(f"{where}:{lines[0].number}: top-level keys must not be indented")
    data, index = _parse_block(lines, 0, 0, where)
    if index != len(lines) or not isinstance(data, dict):
        raise SourceError(f"{where}: front matter must be a mapping")
    return data, text[end + 5 :]


# --- validation --------------------------------------------------------------


@dataclass
class Agent:
    """One validated agent source."""

    name: str
    path: str
    description: str
    body: str
    tier: str | None = None
    models: dict[str, object] = field(default_factory=dict)
    effort: str | None = None
    color: str | None = None
    readonly: bool = False
    tools: list[str] | None = None
    skills: list[str] = field(default_factory=list)
    suggested_skills: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    blocks: dict[str, dict[str, object]] = field(default_factory=dict)


def _check_text(value: str, where: str, *, multiline: bool = False) -> None:
    for char in value:
        if char == "\n" and multiline:
            continue
        if not char.isprintable():
            raise SourceError(f"{where}: contains unsupported character U+{ord(char):04X}")


def _string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceError(f"{where}: must be a non-empty string")
    _check_text(value, where)
    return value


def _string_list(value: object, where: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SourceError(f"{where}: must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise SourceError(f"{where}: lists an entry more than once")
    for item in value:
        _check_text(item, where)
    return list(value)


def _skills(value: object, where: str, skills_root: Path) -> list[str]:
    names = _string_list(value, where)
    for name in names:
        if not NAME_PATTERN.match(name):
            raise SourceError(f"{where}: '{name}' is not a kebab-case skill name")
        if not (skills_root / name / "SKILL.md").is_file():
            raise SourceError(f"{where}: skill '{name}' does not exist under skills/")
    return names


def _block(tool: str, value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SourceError(f"{where}: must be a mapping of {tool}-only settings")
    allowed = TOOL_BLOCKS[tool]
    for key, item in value.items():
        spec = allowed.get(key)
        if spec is None:
            known = ", ".join(allowed) or "none yet"
            raise SourceError(f"{where}.{key}: not a {tool} setting (supported: {known})")
        if isinstance(spec, tuple):
            if item not in spec:
                raise SourceError(f"{where}.{key}: must be one of {', '.join(spec)}")
        elif spec is int:
            if not isinstance(item, int) or isinstance(item, bool):
                raise SourceError(f"{where}.{key}: must be an integer")
        elif spec is bool:
            if not isinstance(item, bool):
                raise SourceError(f"{where}.{key}: must be true or false")
        elif spec is list:
            _string_list(item, f"{where}.{key}")
    return dict(value)


def _model(value: object, where: str) -> tuple[str | None, dict[str, object]]:
    if value is None:
        return None, {}
    if isinstance(value, str):
        if value not in TIERS:
            raise SourceError(f"{where}: '{value}' is not a tier ({', '.join(TIERS)}); "
                              "name a tool's model inside a model block instead")
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
        elif key in TOOLS:
            if key == "hermes":
                raise SourceError(f"{where}.hermes: Hermes personalities cannot set a model")
            if key == "cai":
                models[key] = _string_list(item, f"{where}.cai")
            else:
                models[key] = _string(item, f"{where}.{key}")
        else:
            raise SourceError(f"{where}.{key}: not 'tier' or a tool name ({', '.join(TOOLS)})")
    return tier, models


def load_agent(path: Path, skills_root: Path) -> Agent:
    """Read and validate one agent source file."""
    where = f"{SOURCES_DIR}/{path.name}"
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError(f"{where}: not valid UTF-8") from error
    if "\r" in text:
        raise SourceError(f"{where}: uses CR line endings; use LF only")
    data, body = parse_front_matter(text, where)
    unknown = [key for key in data if key not in TOP_KEYS]
    if unknown:
        raise SourceError(f"{where}: unknown key(s) {', '.join(unknown)}")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise SourceError(f"{where}: missing required key(s) {', '.join(missing)}")
    if data["schema"] != SCHEMA_VERSION:
        raise SourceError(f"{where}: schema must be {SCHEMA_VERSION}")
    name = _string(data["name"], f"{where}: name")
    if not NAME_PATTERN.match(name) or len(name) > MAX_NAME_LENGTH:
        raise SourceError(f"{where}: name must be kebab-case and at most {MAX_NAME_LENGTH} characters")
    if name != path.stem:
        raise SourceError(f"{where}: name '{name}' must match the file name")
    description = _string(data["description"], f"{where}: description")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise SourceError(f"{where}: description exceeds {MAX_DESCRIPTION_LENGTH} characters")
    _check_text(body, f"{where}: body", multiline=True)
    if not body.startswith("# "):
        raise SourceError(f"{where}: body must open with an H1 heading")
    if not body.endswith("\n") or body.endswith("\n\n"):
        raise SourceError(f"{where}: body must end with exactly one newline")

    agent = Agent(name=name, path=where, description=description, body=body)
    agent.tier, agent.models = _model(data.get("model"), f"{where}: model")
    if "effort" in data:
        if data["effort"] not in EFFORT_LEVELS:
            raise SourceError(f"{where}: effort must be one of {', '.join(EFFORT_LEVELS)}")
        agent.effort = data["effort"]
    agent.exclude = _string_list(data.get("exclude", []), f"{where}: exclude")
    bad = [tool for tool in agent.exclude if tool not in TOOLS]
    if bad:
        raise SourceError(f"{where}: exclude names unknown tool(s) {', '.join(bad)}")
    if "color" in data:
        if data["color"] not in CLAUDE_COLORS:
            raise SourceError(f"{where}: color must be one of {', '.join(CLAUDE_COLORS)}")
        agent.color = data["color"]
    elif "claude" not in agent.exclude:
        raise SourceError(f"{where}: color is required for the Claude Code agent")
    if "readonly" in data:
        if not isinstance(data["readonly"], bool):
            raise SourceError(f"{where}: readonly must be true or false")
        agent.readonly = data["readonly"]
    if "tools" in data:
        agent.tools = _string_list(data["tools"], f"{where}: tools")
        unknown_tools = [tool for tool in agent.tools if tool not in KNOWN_TOOLS]
        if unknown_tools:
            raise SourceError(f"{where}: unknown tool(s) {', '.join(unknown_tools)}")
    if agent.readonly:
        if agent.tools is None:
            raise SourceError(f"{where}: a read-only agent must list its tools, which is how Claude Code enforces it")
        writers = [tool for tool in agent.tools if tool in WRITE_TOOLS]
        if writers:
            raise SourceError(f"{where}: a read-only agent cannot list {', '.join(writers)}")
    agent.skills = _skills(data.get("skills", []), f"{where}: skills", skills_root)
    agent.suggested_skills = _skills(data.get("suggested_skills", []), f"{where}: suggested_skills", skills_root)
    both = sorted(set(agent.skills) & set(agent.suggested_skills))
    if both:
        raise SourceError(f"{where}: skill(s) {', '.join(both)} are both required and suggested")
    for tool in TOOLS:
        if tool in data:
            agent.blocks[tool] = _block(tool, data[tool], f"{where}: {tool}")
    return agent


# --- emitters ----------------------------------------------------------------

_PLAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,;'()/_+=@\[\]-]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def yaml_scalar(value: object) -> str:
    """Emit one YAML scalar, plain when that is unambiguous, else double-quoted."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if (_PLAIN.match(text) and ": " not in text and " #" not in text and text.lower() not in _RESERVED
            and not re.fullmatch(r"[-+.0-9eE]+", text) and not text.startswith(("[", "-"))):
        return text
    return json.dumps(text, ensure_ascii=False)


def yaml_flow(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(item) if re.search(r"[,\[\]{}#:'\"]", item) else yaml_scalar(item)
                           for item in values) + "]"


def toml_string(value: str) -> str:
    escaped = []
    for char in value:
        if char in '"\\':
            escaped.append("\\" + char)
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\t":
            escaped.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            escaped.append(f"\\u{ord(char):04X}")
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


def toml_multiline(value: str) -> str:
    """Emit a multi-line basic string that reads back as value exactly."""
    out: list[str] = []
    quotes = 0
    for char in value:
        if char == '"':
            quotes += 1
            out.append('\\"' if quotes % 3 == 0 else '"')
            continue
        quotes = 0
        if char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\n")
        elif char == "\t":
            out.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    if out and out[-1] == '"':
        out[-1] = '\\"'
    return '"""\n' + "".join(out) + '"""'


def toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_string(item) for item in value) + "]"
    return toml_string(str(value))


# --- rendering ---------------------------------------------------------------


def resolve_model(agent: Agent, tool: str) -> str | None:
    """Return the tool's model: its own value, else its tier's, else None."""
    if tool in agent.models:
        return str(agent.models[tool])
    if agent.tier:
        return TIER_MODELS.get(tool, {}).get(agent.tier)
    return None


def _not_enforced(noun: str, what: str) -> list[str]:
    return [
        f"# This {noun} is meant to {what}, but this tool may not",
        "# enforce that; host approvals and sandbox policy remain the only limit.",
    ]


def skills_section(required: list[str], suggested: list[str]) -> list[str]:
    lines = [SKILLS_HEADING, ""]
    if required:
        lines += ["This tool does not preload skills, so load each of these before starting work:", ""]
        lines += [f"- `{name}`" for name in required] + [""]
    if suggested:
        lines += ["Load each of these when the task makes it relevant:", ""]
        lines += [f"- `{name}`" for name in suggested] + [""]
    return lines


def insert_skills_section(body: str, required: list[str], suggested: list[str]) -> str:
    """Put the skills section before the body's second H2, or at its end."""
    if not required and not suggested:
        return body
    lines = body.rstrip("\n").split("\n")
    if any(line.strip() == SKILLS_HEADING for line in lines):
        raise SourceError(f"body already has a '{SKILLS_HEADING}' heading")
    fenced, seen = False, 0
    for index, line in enumerate(lines):
        if line.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            seen += 1
            if seen == 2:
                section = skills_section(required, suggested)
                return "\n".join(lines[:index] + section + lines[index:]) + "\n"
    return "\n".join(lines + [""] + skills_section(required, suggested)).rstrip("\n") + "\n"


def _yaml_lines(entries: list[tuple[str, object]]) -> list[str]:
    lines = []
    for key, value in entries:
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines += [f"  - {yaml_scalar(item)}" for item in value]
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    return lines


def render_claude(agent: Agent) -> str:
    entries: list[tuple[str, object]] = [("name", agent.name), ("description", agent.description),
                                         ("model", resolve_model(agent, "claude") or "inherit")]
    if agent.effort:
        entries.append(("effort", agent.effort))
    entries.append(("color", agent.color))
    if agent.tools is not None:
        entries.append(("tools", ", ".join(agent.tools)))
    if agent.skills:
        entries.append(("skills", agent.skills))
    entries += list(agent.blocks.get("claude", {}).items())
    body = insert_skills_section(agent.body, [], agent.suggested_skills)
    header = "# " + HEADER.format(name=agent.name)
    return "\n".join(["---", header, *_yaml_lines(entries), "---"]) + "\n" + body


def render_cursor(agent: Agent) -> str:
    entries: list[tuple[str, object]] = [("name", agent.name), ("description", agent.description),
                                         ("model", resolve_model(agent, "cursor") or "inherit")]
    if agent.readonly:
        entries.append(("readonly", True))
    entries += list(agent.blocks.get("cursor", {}).items())
    lines = ["---", "# " + HEADER.format(name=agent.name), *_yaml_lines(entries)]
    if agent.effort:
        lines += [f"# effort: {agent.effort}",
                  "# This agent is meant to run at this reasoning effort, but this tool has no",
                  "# agent setting for it."]
    if agent.tools is not None:
        lines += [f"# tools: {yaml_flow(agent.tools)}", *_not_enforced("agent", "use only the listed tools")]
    if agent.skills:
        lines += [f"# skills: {yaml_flow(agent.skills)}",
                  "# This agent depends on the listed skills, but this tool does not preload",
                  "# them; the agent is instructed to load them before starting."]
    lines.append("---")
    body = insert_skills_section(agent.body, agent.skills, agent.suggested_skills)
    return "\n".join(lines) + "\n" + body


def render_codex(agent: Agent) -> str:
    lines = ["# " + HEADER.format(name=agent.name), f"name = {toml_string(agent.name)}",
             f"description = {toml_string(agent.description)}"]
    model = resolve_model(agent, "codex")
    if model:
        lines.append(f"model = {toml_string(model)}")
    if agent.effort:
        lines.append(f"model_reasoning_effort = {toml_string(CODEX_EFFORT[agent.effort])}")
    if agent.readonly:
        lines.append('sandbox_mode = "read-only"')
    for key, value in agent.blocks.get("codex", {}).items():
        lines.append(f"{key} = {toml_value(value)}")
    if agent.tools is not None:
        lines += [f"# tools = {toml_value(agent.tools)}", *_not_enforced("agent", "use only the listed tools")]
    if agent.skills:
        lines += [f"# skills = {toml_value(agent.skills)}",
                  "# This agent depends on the listed skills, but this tool does not preload",
                  "# them; the agent is instructed to load them before starting."]
    body = insert_skills_section(agent.body, agent.skills, agent.suggested_skills)
    lines.append(f"developer_instructions = {toml_multiline(body)}")
    return "\n".join(lines) + "\n"


def render_hermes(agent: Agent) -> str:
    notes = [f"Notes for this personality, generated from the `{agent.name}` agent:", ""]
    wanted = agent.tier or None
    if wanted:
        notes.append(f"- Model: this agent is meant for the `{wanted}` tier; Hermes uses the session's model.")
    else:
        notes.append("- Model: Hermes uses the session's model.")
    if agent.effort:
        notes.append(f"- Effort: this agent is meant to run at `{agent.effort}` reasoning effort.")
    if agent.readonly:
        notes.append("- Read-only: do not change files, including through the shell; Hermes does not enforce this.")
    if agent.tools is not None:
        notes.append("- Tools: use only " + ", ".join(agent.tools) + "; Hermes does not enforce this list.")
    if agent.skills:
        notes.append("- Skills: load " + ", ".join(f"`{name}`" for name in agent.skills) + " before starting work.")
    if agent.suggested_skills:
        notes.append("- Suggested skills: load " + ", ".join(f"`{name}`" for name in agent.suggested_skills)
                     + " when the task makes them relevant.")
    prompt = "\n".join(notes) + "\n\n" + agent.body
    return "\n".join([
        "# " + HEADER.format(name=agent.name),
        "description: " + json.dumps(agent.description, ensure_ascii=False),
        "system_prompt: " + json.dumps(prompt, ensure_ascii=False),
    ]) + "\n"


RENDERERS = {"claude": render_claude, "codex": render_codex, "cursor": render_cursor, "hermes": render_hermes}


def load_agents(root: Path) -> list[Agent]:
    """Load every agent source, collecting all problems before failing."""
    sources = root / SOURCES_DIR
    if not sources.is_dir():
        raise SourceError(f"{SOURCES_DIR}/ not found under {root}")
    agents, problems = [], []
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


def render_all(agents: list[Agent]) -> dict[str, str]:
    """Return every output path, relative to generated/, and its content."""
    outputs = {}
    for agent in agents:
        for tool in GENERATED_TOOLS:
            if tool in agent.exclude:
                continue
            try:
                outputs[OUTPUT_PATHS[tool].format(name=agent.name)] = RENDERERS[tool](agent)
            except SourceError as error:
                raise SourceError(f"{agent.path}: {error}") from error
    return outputs


def write_outputs(output: Path, outputs: dict[str, str]) -> None:
    """Build the whole output tree beside the old one, then swap it into place."""
    output = output.absolute()
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise SourceError(f"{output} must be a directory, not a link or file")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for relative, content in outputs.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        retired = None
        if output.exists():
            retired = output.with_name(f".{output.name}.old-{os.getpid()}")
            output.rename(retired)
        staging.rename(output)
        if retired is not None:
            shutil.rmtree(retired)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root (default: this script's repository)")
    parser.add_argument("--output", type=Path, help="output directory (default: <root>/generated)")
    args = parser.parse_args(argv)
    root = args.root
    output = args.output or root / OUTPUT_DIR
    try:
        agents = load_agents(root)
        outputs = render_all(agents)
        write_outputs(output, outputs)
    except SourceError as error:
        print("generate_agents: nothing was generated:", file=sys.stderr)
        for line in str(error).splitlines():
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"generate_agents: {len(outputs)} files for {len(agents)} agents in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
