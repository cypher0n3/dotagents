#!/usr/bin/env python3
"""Validate the Claude Code subagent definitions under agents/.

Checks that every agent file carries well-formed YAML frontmatter, that the
declared name matches the filename that Claude Code uses to address the agent,
that the fields Claude Code reads carry values it accepts, that every preloaded
skill exists under skills/, that the body opens with an H1 and carries no HTML
comments, and that the index README links every agent.

Field names and allowed values follow the Claude Code subagent documentation at
https://code.claude.com/docs/en/sub-agents.

Exit status is 0 when every agent is valid and 1 when any error is reported.
Warnings never change the exit status.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from validate_skills import (
    KEY_PATTERN,
    NAME_PATTERN,
    Report,
    comment_lines,
    first_body_heading,
    split_frontmatter,
)

INDEX_FILENAME = "README.md"
SKILL_FILENAME = "SKILL.md"

REQUIRED_KEYS = ("name", "description")
REPO_REQUIRED_KEYS = ("model", "color")
KNOWN_KEYS = (
    "name",
    "description",
    "model",
    "tools",
    "disallowedTools",
    "skills",
    "permissionMode",
    "memory",
    "isolation",
    "maxTurns",
    "mcpServers",
    "hooks",
    "color",
    "background",
    "effort",
    "initialPrompt",
    "experimental",
)
LIST_KEYS = ("skills", "mcpServers")
NESTED_KEYS = ("hooks", "experimental")

MODEL_ALIASES = ("sonnet", "opus", "haiku", "fable", "inherit")
MODEL_ID_PATTERN = re.compile(r"^claude-[a-z0-9-]+$")
PERMISSION_MODES = (
    "default",
    "manual",
    "acceptEdits",
    "plan",
    "auto",
    "bypassPermissions",
    "dontAsk",
)
MEMORY_SCOPES = ("user", "project", "local")
ISOLATION_MODES = ("worktree",)
COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
BOOLEANS = ("true", "false")

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")


def parse_frontmatter(lines: list[str]) -> dict[str, object]:
    """Parse the frontmatter shape Claude Code agents use.

    Scalar keys map to their string value. Keys listed in LIST_KEYS map to a
    list of strings, accepting either an inline ``[a, b]`` form or one ``- item``
    per indented line. Keys in NESTED_KEYS map to the raw indented block, which
    is kept only so the key is recognized rather than reported as unknown.
    """
    values: dict[str, object] = {}
    current_key: str | None = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() and current_key is not None:
            _append_continuation(values, current_key, line)
            continue
        match = KEY_PATTERN.match(line)
        if not match:
            continue
        current_key = match.group(1)
        raw = match.group(2).strip()
        if current_key in LIST_KEYS:
            values[current_key] = _parse_inline_list(raw)
        elif current_key in NESTED_KEYS:
            values[current_key] = []
        else:
            values[current_key] = "" if raw in ("|", ">", "|-", ">-") else raw
    return values


def _append_continuation(values: dict[str, object], key: str, line: str) -> None:
    """Fold an indented continuation line into the value already parsed for key."""
    stripped = line.strip()
    existing = values.get(key)
    if isinstance(existing, list):
        if stripped.startswith("- "):
            existing.append(stripped[2:].strip().strip("'\""))
        elif key in NESTED_KEYS:
            existing.append(stripped)
        return
    values[key] = f"{existing} {stripped}".strip()


def _parse_inline_list(raw: str) -> list[str]:
    """Return the items of an inline YAML list, or an empty list for a block list."""
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        return [item.strip().strip("'\"") for item in raw[1:-1].split(",") if item.strip()]
    return [raw.strip().strip("'\"")]


def parse_tool_list(raw: str) -> list[str]:
    """Return the entries of a comma-separated tools value, keeping Agent(...) groups intact."""
    entries: list[str] = []
    depth = 0
    current: list[str] = []
    for char in raw:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        if char == "," and depth == 0:
            entries.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    entries.append("".join(current).strip())
    return entries


def validate_model(value: str, location: str, report: Report) -> None:
    """Accept a documented alias or a full Claude model identifier."""
    if value in MODEL_ALIASES or MODEL_ID_PATTERN.match(value):
        return
    report.error(
        location,
        f"model '{value}' must be one of {', '.join(MODEL_ALIASES)} or a full claude-* model identifier",
    )


def validate_enum(key: str, value: str, allowed: tuple[str, ...], location: str, report: Report) -> None:
    """Report a value that is not in the documented set for its key."""
    if value not in allowed:
        report.error(location, f"{key} '{value}' must be one of {', '.join(allowed)}")


def validate_effort(value: str, location: str, report: Report) -> None:
    """Accept a documented effort level or a positive integer budget."""
    if value in EFFORT_LEVELS or (value.isdigit() and int(value) > 0):
        return
    report.error(
        location,
        f"effort '{value}' must be one of {', '.join(EFFORT_LEVELS)} or a positive integer",
    )


def validate_tools(key: str, raw: str, location: str, report: Report) -> None:
    """Report an empty entry in a comma-separated tool list."""
    if any(not entry for entry in parse_tool_list(raw)):
        report.error(location, f"{key} contains an empty entry; write a comma-separated list of tool names")


def validate_skills_exist(skills: list[str], skills_root: Path, location: str, report: Report) -> None:
    """Report a preloaded skill that has no SKILL.md under the skills root."""
    for skill in skills:
        if not (skills_root / skill / SKILL_FILENAME).is_file():
            report.error(location, f"preloaded skill '{skill}' has no {SKILL_FILENAME} under {skills_root}")


def validate_agent(agent_file: Path, skills_root: Path, report: Report) -> str | None:
    """Validate one agent file, record findings, and return its declared name."""
    location = str(agent_file)
    parsed = split_frontmatter(agent_file.read_text(encoding="utf-8"))
    if parsed is None:
        report.error(location, "missing or unterminated YAML frontmatter")
        return None
    frontmatter_lines, body_lines = parsed
    frontmatter = parse_frontmatter(frontmatter_lines)

    for key in REQUIRED_KEYS:
        if not frontmatter.get(key):
            report.error(location, f"frontmatter is missing required key '{key}'")
    for key in REPO_REQUIRED_KEYS:
        if not frontmatter.get(key):
            report.error(
                location,
                f"frontmatter is missing '{key}'; Claude Code treats it as optional "
                "but this repository requires it",
            )

    name = str(frontmatter.get("name", ""))
    if name and name != agent_file.stem:
        report.error(location, f"frontmatter name '{name}' does not match filename '{agent_file.stem}'")
    if name and not NAME_PATTERN.match(name):
        report.error(
            location,
            f"frontmatter name '{name}' must be lowercase alphanumeric and hyphens, "
            "without leading, trailing, or consecutive hyphens",
        )
    if len(name) > MAX_NAME_LENGTH:
        report.error(location, f"name is {len(name)} characters; the limit is {MAX_NAME_LENGTH}")

    description = str(frontmatter.get("description", ""))
    if len(description) > MAX_DESCRIPTION_LENGTH:
        report.error(
            location,
            f"description is {len(description)} characters; the limit is {MAX_DESCRIPTION_LENGTH}",
        )

    if "model" in frontmatter:
        validate_model(str(frontmatter["model"]), location, report)
    if "permissionMode" in frontmatter:
        validate_enum("permissionMode", str(frontmatter["permissionMode"]), PERMISSION_MODES, location, report)
    if "memory" in frontmatter:
        validate_enum("memory", str(frontmatter["memory"]), MEMORY_SCOPES, location, report)
    if "isolation" in frontmatter:
        validate_enum("isolation", str(frontmatter["isolation"]), ISOLATION_MODES, location, report)
    if "color" in frontmatter:
        validate_enum("color", str(frontmatter["color"]), COLORS, location, report)
    if "background" in frontmatter:
        validate_enum("background", str(frontmatter["background"]), BOOLEANS, location, report)
    if "effort" in frontmatter:
        validate_effort(str(frontmatter["effort"]), location, report)
    if "maxTurns" in frontmatter:
        max_turns = str(frontmatter["maxTurns"])
        if not max_turns.isdigit() or int(max_turns) < 1:
            report.error(location, f"maxTurns '{max_turns}' must be a positive integer")
    for key in ("tools", "disallowedTools"):
        if key in frontmatter:
            validate_tools(key, str(frontmatter[key]), location, report)

    skills = frontmatter.get("skills", [])
    if isinstance(skills, list):
        validate_skills_exist(skills, skills_root, location, report)

    for key in frontmatter:
        if key not in KNOWN_KEYS:
            report.warn(location, f"unrecognized frontmatter key '{key}'")

    heading = first_body_heading(body_lines)
    if not heading.startswith("# "):
        report.error(location, "body must open with a single H1 heading")
    if not any(line.strip() and not line.startswith("# ") for line in body_lines):
        report.error(location, "body carries no instructions after the H1 heading")

    for number in comment_lines(body_lines):
        report.error(
            location,
            f"HTML comment on body line {number}; an agent file is loaded as raw text, "
            "so notes belong in docs/ instead",
        )
    return name or None


def validate_index(index: Path, names: list[str], report: Report) -> None:
    """Report an agent that the index README does not link."""
    if not index.is_file():
        report.error(str(index), "agent index is missing")
        return
    linked = set(LINK_PATTERN.findall(index.read_text(encoding="utf-8")))
    for name in names:
        if f"{name}.md" not in linked:
            report.error(str(index), f"agent '{name}' is not linked from the index")


def discover_agent_files(agents_root: Path) -> list[Path]:
    """Return every agent definition under the agents root, sorted by name."""
    return sorted(path for path in agents_root.glob("*.md") if path.name != INDEX_FILENAME)


def main(argv: list[str] | None = None) -> int:
    """Validate every agent under the requested root and report the outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "agents_root",
        nargs="?",
        default="agents",
        help="directory holding one Markdown file per agent (default: agents)",
    )
    parser.add_argument(
        "skills_root",
        nargs="?",
        default="skills",
        help="directory holding one subdirectory per skill, for preload checks (default: skills)",
    )
    parser.add_argument(
        "--index",
        help="agent index that must link every agent (default: README.md in the agents directory)",
    )
    args = parser.parse_args(argv)

    agents_root = Path(args.agents_root)
    skills_root = Path(args.skills_root)
    for root in (agents_root, skills_root):
        if not root.is_dir():
            print(f"error: {root} is not a directory", file=sys.stderr)
            return 1

    report = Report()
    agent_files = discover_agent_files(agents_root)
    if not agent_files:
        print(f"error: no agent files found under {agents_root}", file=sys.stderr)
        return 1
    names = [validate_agent(agent_file, skills_root, report) for agent_file in agent_files]
    index = Path(args.index) if args.index else agents_root / INDEX_FILENAME
    validate_index(index, [name for name in names if name], report)

    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)

    if report.errors:
        print(f"\nvalidate_agents: {len(report.errors)} error(s) in {len(agent_files)} agent(s)", file=sys.stderr)
        return 1
    print(f"validate_agents: {len(agent_files)} agent(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
