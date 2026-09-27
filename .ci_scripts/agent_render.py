"""Render a validated Agent as each tool's agent file.

How each tool spells each field lives here, never in the sources: the model
tier table, each tool's key names, and the fixed comments written where a tool
cannot enforce something. Every renderer returns the file's full text.
"""

from __future__ import annotations

import json
import re

from agent_front_matter import AMBIGUOUS_WORDS, SourceError
from agent_source import Agent

# What each tier means for each tool. A tool with no entry for a tier uses its
# session's model. Hermes personalities cannot set a model, and CAI resolves
# its own from the sources.
TIER_MODELS = {
    "claude": {"frontier": "fable", "strong": "opus", "standard": "sonnet", "fast": "haiku"},
    "codex": {},
    "cursor": {},
}

# Codex has no `max` reasoning effort, so its highest level stands in.
CODEX_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}

GENERATED_HEADER = (
    "Generated from agent_sources/{name}.md by .ci_scripts/generate_agents.py; "
    "do not edit, changes are lost at the next generation."
)

# The body section added for tools that cannot preload skills.
SKILLS_HEADING = "## Skill Dependencies"
REQUIRED_SKILLS_INTRO = "This tool does not preload skills, so load each of these before starting work:"
SUGGESTED_SKILLS_INTRO = "Load each of these when the task makes it relevant:"

# Comments following a key the tool cannot enforce.
TOOLS_NOT_ENFORCED = [
    "# This agent is meant to use only the listed tools, but this tool may not",
    "# enforce that; host approvals and sandbox policy remain the only limit.",
]
SKILLS_NOT_PRELOADED = [
    "# This agent depends on the listed skills, but this tool does not preload",
    "# them; the agent is instructed to load them before starting.",
]
EFFORT_NOT_SUPPORTED = [
    "# This agent is meant to run at this reasoning effort, but this tool has no",
    "# agent setting for it.",
]


# --- Writing YAML and TOML values -------------------------------------------
#
# Each value is written on its own rather than through a serializer, which
# keeps the output byte-for-byte stable and lets fixed comments sit between
# keys. Every rule here errs toward quoting.

# A plain YAML scalar made only of these characters cannot be mistaken for
# YAML syntax, provided the extra checks in yaml_scalar also pass.
PLAIN_SCALAR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,;'()/_+=@\[\]-]*$")
NUMBER_LIKE = re.compile(r"^[-+.0-9eE]+$")


def yaml_scalar(value: object) -> str:
    """Write one YAML scalar: plain when that cannot be misread, double-quoted otherwise."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)

    text = str(value)
    looks_plain = bool(PLAIN_SCALAR.match(text))
    has_syntax = ": " in text or " #" in text or text.startswith(("[", "-"))
    reads_as_other_type = text.lower() in AMBIGUOUS_WORDS or bool(NUMBER_LIKE.match(text))
    if looks_plain and not has_syntax and not reads_as_other_type:
        return text
    # A JSON string is also a valid YAML double-quoted string.
    return json.dumps(text, ensure_ascii=False)


def yaml_entries(entries: list[tuple[str, object]]) -> list[str]:
    """Write `key: value` lines, with each list as a block list."""
    lines = []
    for key, value in entries:
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {yaml_scalar(item)}" for item in value)
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    return lines


def commented_yaml_list(key: str, values: list[str]) -> list[str]:
    """Write a block list as YAML comments, for a key the tool does not read."""
    return [f"# {key}:"] + [f"#   - {yaml_scalar(item)}" for item in values]


def _toml_escape(char: str) -> str:
    """Escape one character for a TOML basic string, leaving newlines to the caller."""
    if char in '"\\':
        return "\\" + char
    if char == "\t":
        return "\\t"
    if ord(char) < 0x20 or ord(char) == 0x7F:
        return f"\\u{ord(char):04X}"
    return char


def toml_string(value: str) -> str:
    """Write a single-line TOML basic string."""
    escaped = "".join("\\n" if char == "\n" else _toml_escape(char) for char in value)
    return f'"{escaped}"'


def toml_multiline(value: str) -> str:
    """Write a TOML multi-line basic string that reads back as `value` exactly."""
    out: list[str] = []
    quote_run = 0
    for char in value:
        if char == '"':
            # Three quotes in a row would end the string, so escape every third.
            quote_run += 1
            out.append('"' if quote_run % 3 else '\\"')
            continue
        quote_run = 0
        out.append("\n" if char == "\n" else _toml_escape(char))
    # A quote right before the closing """ would merge into it.
    if out and out[-1] == '"':
        out[-1] = '\\"'
    # TOML drops a newline immediately after the opening """.
    return '"""\n' + "".join(out) + '"""'


def toml_value(value: object) -> str:
    """Write a TOML boolean, integer, string, or list of strings."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_string(item) for item in value) + "]"
    return toml_string(str(value))


# --- Rendering each tool's file ----------------------------------------------


def resolve_model(agent: Agent, tool: str) -> str | None:
    """Return the tool's model: its own value, else its tier's mapping, else None."""
    if tool in agent.models:
        return str(agent.models[tool])
    if agent.tier:
        return TIER_MODELS.get(tool, {}).get(agent.tier)
    return None


def skills_section(required: list[str], suggested: list[str]) -> list[str]:
    """Return the `## Skill Dependencies` section as lines, ending with a blank line."""
    lines = [SKILLS_HEADING, ""]
    if required:
        lines += [REQUIRED_SKILLS_INTRO, ""]
        lines += [f"- `{name}`" for name in required]
        lines.append("")
    if suggested:
        lines += [SUGGESTED_SKILLS_INTRO, ""]
        lines += [f"- `{name}`" for name in suggested]
        lines.append("")
    return lines


def insert_skills_section(body: str, required: list[str], suggested: list[str]) -> str:
    """Add the skills section before the body's second H2, or at its end.

    The first H2 is the agent's `## Role`, which stays first. Headings inside
    fenced code blocks are not headings, so fences are tracked.
    """
    if not required and not suggested:
        return body
    lines = body.rstrip("\n").split("\n")
    if any(line.strip() == SKILLS_HEADING for line in lines):
        raise SourceError(f"body already has a '{SKILLS_HEADING}' heading")

    section = skills_section(required, suggested)
    in_fence = False
    h2_count = 0
    for index, line in enumerate(lines):
        if line.startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            h2_count += 1
            if h2_count == 2:
                return "\n".join(lines[:index] + section + lines[index:]) + "\n"

    # No second H2: append, separated by a blank line.
    return "\n".join(lines + [""] + section).rstrip("\n") + "\n"


def _header(agent: Agent) -> str:
    return "# " + GENERATED_HEADER.format(name=agent.name)


def render_claude(agent: Agent) -> str:
    """Render a Claude Code agent: Markdown with YAML front matter.

    Claude Code enforces `tools` and preloads `skills`, so both are native keys.
    It has no read-only flag; a read-only agent's tool list already excludes
    every file-writing tool. Suggested skills become a body instruction.
    """
    entries: list[tuple[str, object]] = [
        ("name", agent.name),
        ("description", agent.description),
        ("model", resolve_model(agent, "claude") or "inherit"),
    ]
    if agent.effort:
        entries.append(("effort", agent.effort))
    entries.append(("color", agent.color))
    if agent.tools is not None:
        # Claude Code's own format for tools is one comma-separated string.
        entries.append(("tools", ", ".join(agent.tools)))
    if agent.skills:
        entries.append(("skills", agent.skills))
    entries.extend(agent.settings.get("claude", {}).items())

    front_matter = ["---", _header(agent), *yaml_entries(entries), "---"]
    body = insert_skills_section(agent.body, [], agent.suggested_skills)
    return "\n".join(front_matter) + "\n" + body


def render_cursor(agent: Agent) -> str:
    """Render a Cursor agent: Markdown with YAML front matter.

    Cursor enforces `readonly`, but has no tool allowlist, no skill preloading,
    and no effort setting, so those become comments and a body section.
    """
    entries: list[tuple[str, object]] = [
        ("name", agent.name),
        ("description", agent.description),
        ("model", resolve_model(agent, "cursor") or "inherit"),
    ]
    if agent.readonly:
        entries.append(("readonly", True))
    entries.extend(agent.settings.get("cursor", {}).items())

    front_matter = ["---", _header(agent), *yaml_entries(entries)]
    if agent.effort:
        front_matter += [f"# effort: {agent.effort}", *EFFORT_NOT_SUPPORTED]
    if agent.tools is not None:
        front_matter += [*commented_yaml_list("tools", agent.tools), *TOOLS_NOT_ENFORCED]
    if agent.skills:
        front_matter += [*commented_yaml_list("skills", agent.skills), *SKILLS_NOT_PRELOADED]
    front_matter.append("---")

    body = insert_skills_section(agent.body, agent.skills, agent.suggested_skills)
    return "\n".join(front_matter) + "\n" + body


def render_codex(agent: Agent) -> str:
    """Render a Codex custom agent: one TOML file whose instructions are the body.

    Codex enforces read-only through its sandbox, and takes a reasoning effort,
    but has no tool allowlist and no skill preloading.
    """
    lines = [
        _header(agent),
        f"name = {toml_string(agent.name)}",
        f"description = {toml_string(agent.description)}",
    ]
    model = resolve_model(agent, "codex")
    if model:
        lines.append(f"model = {toml_string(model)}")
    if agent.effort:
        lines.append(f"model_reasoning_effort = {toml_string(CODEX_EFFORT[agent.effort])}")
    if agent.readonly:
        lines.append('sandbox_mode = "read-only"')
    for key, value in agent.settings.get("codex", {}).items():
        lines.append(f"{key} = {toml_value(value)}")
    if agent.tools is not None:
        lines += [f"# tools = {toml_value(agent.tools)}", *TOOLS_NOT_ENFORCED]
    if agent.skills:
        lines += [f"# skills = {toml_value(agent.skills)}", *SKILLS_NOT_PRELOADED]

    body = insert_skills_section(agent.body, agent.skills, agent.suggested_skills)
    lines.append(f"developer_instructions = {toml_multiline(body)}")
    return "\n".join(lines) + "\n"


def render_hermes(agent: Agent) -> str:
    """Render a Hermes personality: a header comment and two JSON-string lines.

    A personality has only a description and a system prompt, and applies to a
    whole session, so everything else is stated in a notes paragraph at the
    start of the prompt. Each value is a JSON string, which is also valid YAML,
    so the installers can read the file without a YAML parser.
    """
    notes = [f"Notes for this personality, generated from the `{agent.name}` agent:", ""]
    if agent.tier:
        notes.append(f"- Model: this agent is meant for the `{agent.tier}` tier; Hermes uses the session's model.")
    else:
        notes.append("- Model: Hermes uses the session's model.")
    if agent.effort:
        notes.append(f"- Effort: this agent is meant to run at `{agent.effort}` reasoning effort.")
    if agent.readonly:
        notes.append("- Read-only: do not change files, including through the shell; Hermes does not enforce this.")
    if agent.tools is not None:
        notes.append(f"- Tools: use only {', '.join(agent.tools)}; Hermes does not enforce this list.")
    if agent.skills:
        names = ", ".join(f"`{name}`" for name in agent.skills)
        notes.append(f"- Skills: load {names} before starting work.")
    if agent.suggested_skills:
        names = ", ".join(f"`{name}`" for name in agent.suggested_skills)
        notes.append(f"- Suggested skills: load {names} when the task makes them relevant.")

    prompt = "\n".join(notes) + "\n\n" + agent.body
    lines = [
        _header(agent),
        "description: " + json.dumps(agent.description, ensure_ascii=False),
        "system_prompt: " + json.dumps(prompt, ensure_ascii=False),
    ]
    return "\n".join(lines) + "\n"


RENDERERS = {
    "claude": render_claude,
    "codex": render_codex,
    "cursor": render_cursor,
    "hermes": render_hermes,
}
