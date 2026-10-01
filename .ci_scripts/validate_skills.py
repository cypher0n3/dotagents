#!/usr/bin/env python3
"""Validate the skill definitions under skills/.

Checks that every skill directory holds a SKILL.md with well-formed YAML
frontmatter, that the declared name matches the directory that agents use to
address the skill, that the body carries no HTML comments, and that optional
agent manifests carry the keys the OpenAI skill interface expects.

Field names, length limits, and the advisory size guidance follow the Agent
Skills specification at https://agentskills.io/specification.

Exit status is 0 when every skill is valid and 1 when any error is reported.
Warnings never change the exit status.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

FRONTMATTER_DELIMITER = "---"
SKILL_FILENAME = "SKILL.md"
AGENT_MANIFEST = "agents/openai.yaml"

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KEY_PATTERN = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")

REQUIRED_KEYS = ("name", "description")

# Fields defined by the Agent Skills specification.
SPEC_KEYS = (
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
)
# Client extensions the specification does not define; it reserves `metadata`
# for arbitrary extras, but these are read directly by agent tools today.
CLIENT_KEYS = (
    "user-invocable",
    "disable-model-invocation",
    "model",
)
KNOWN_KEYS = SPEC_KEYS + CLIENT_KEYS
BOOLEAN_KEYS = ("user-invocable", "disable-model-invocation")
MANIFEST_REQUIRED_KEYS = ("display_name", "short_description", "default_prompt")

# Limits from the Agent Skills specification.
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500

# Advisory size guidance from the specification: keep SKILL.md under 500 lines
# and its body under roughly 5000 tokens. Tokens are estimated from character
# count, so both are reported as warnings rather than errors.
MAX_BODY_LINES = 500
MAX_BODY_TOKENS = 5000
CHARS_PER_TOKEN = 4


@dataclass
class Report:
    """Collected findings for a single validation run."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")

    def warn(self, location: str, message: str) -> None:
        self.warnings.append(f"{location}: {message}")


def split_frontmatter(text: str) -> tuple[list[str], list[str]] | None:
    """Return the frontmatter and body lines, or None when frontmatter is absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            return lines[1:index], lines[index + 1:]
    return None


def parse_frontmatter(lines: list[str]) -> dict[str, str]:
    """Parse the flat key/value frontmatter used by skill definitions.

    Block scalars (``key: |`` or ``key: >``) and their indented continuations are
    folded into a single space-separated value, which is all the checks below need.
    """
    values: dict[str, str] = {}
    current_key: str | None = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() and current_key is not None:
            values[current_key] = f"{values[current_key]} {line.strip()}".strip()
            continue
        match = KEY_PATTERN.match(line)
        if not match:
            continue
        current_key = match.group(1)
        value = match.group(2).strip()
        values[current_key] = "" if value in ("|", ">", "|-", ">-") else value
    return values


def comment_lines(body_lines: list[str]) -> list[int]:
    """Return the 1-based body line numbers that open an HTML comment.

    A SKILL.md is injected into the model's context as raw text, comments
    included, so a comment costs context without hiding anything. Comments
    inside fenced code blocks are sample content and are not reported.
    """
    found: list[int] = []
    in_fence = False
    in_comment = False
    for number, line in enumerate(body_lines, start=1):
        stripped = line.strip()
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            found.append(number)
            if "-->" not in stripped:
                in_comment = True
    return found


def first_body_heading(body_lines: list[str]) -> str:
    """Return the first body line that is not blank."""
    for line in body_lines:
        if line.strip():
            return line.strip()
    return ""


def validate_manifest(manifest_path: Path, location: str, report: Report) -> None:
    """Check that an agent manifest declares the keys the OpenAI interface needs."""
    text = manifest_path.read_text(encoding="utf-8")
    declared = {
        match.group(1)
        for match in (KEY_PATTERN.match(line.strip()) for line in text.splitlines())
        if match
    }
    for key in MANIFEST_REQUIRED_KEYS:
        if key not in declared:
            report.error(location, f"agent manifest is missing required key '{key}'")


def validate_name(name: str, skill_dir: Path, location: str, report: Report) -> None:
    """Report a name that does not match its directory, is not kebab-case, or is too long."""
    if name and name != skill_dir.name:
        report.error(location, f"frontmatter name '{name}' does not match directory '{skill_dir.name}'")
    if name and not NAME_PATTERN.match(name):
        report.error(
            location,
            f"frontmatter name '{name}' must be lowercase alphanumeric and hyphens, "
            "without leading, trailing, or consecutive hyphens",
        )
    if len(name) > MAX_NAME_LENGTH:
        report.error(location, f"name is {len(name)} characters; the limit is {MAX_NAME_LENGTH}")


def validate_frontmatter(frontmatter: dict, skill_dir: Path, location: str, report: Report) -> None:
    """Check required keys, the name, length limits, boolean values, and unknown keys."""
    for key in REQUIRED_KEYS:
        if not frontmatter.get(key):
            report.error(location, f"frontmatter is missing required key '{key}'")
    validate_name(frontmatter.get("name", ""), skill_dir, location, report)

    for key, limit in (("description", MAX_DESCRIPTION_LENGTH), ("compatibility", MAX_COMPATIBILITY_LENGTH)):
        length = len(frontmatter.get(key, ""))
        if length > limit:
            report.error(location, f"{key} is {length} characters; the limit is {limit}")

    for key in BOOLEAN_KEYS:
        value = frontmatter.get(key)
        if value is not None and value not in ("true", "false"):
            report.error(location, f"frontmatter key '{key}' must be true or false, found '{value}'")

    for key in frontmatter:
        if key not in KNOWN_KEYS:
            report.warn(location, f"unrecognized frontmatter key '{key}'")


def validate_body(body_lines: list[str], location: str, report: Report) -> None:
    """Check the body's heading, its size against the specification, and HTML comments."""
    heading = first_body_heading(body_lines)
    if not heading.startswith("# "):
        report.error(location, "body must open with a single H1 heading")

    body_line_count = len(body_lines)
    if body_line_count > MAX_BODY_LINES:
        report.warn(
            location,
            f"body is {body_line_count} lines; the specification recommends under {MAX_BODY_LINES}, "
            "so consider moving detail into references/",
        )
    estimated_tokens = sum(len(line) + 1 for line in body_lines) // CHARS_PER_TOKEN
    if estimated_tokens > MAX_BODY_TOKENS:
        report.warn(
            location,
            f"body is roughly {estimated_tokens} tokens; the specification recommends under "
            f"{MAX_BODY_TOKENS}, so consider moving detail into references/",
        )

    for number in comment_lines(body_lines):
        report.error(
            location,
            f"HTML comment on body line {number}; a SKILL.md is loaded as raw text, "
            "so notes belong in references/ or docs/ instead",
        )


def validate_skill(skill_dir: Path, report: Report) -> None:
    """Validate one skill directory and record findings on the report."""
    skill_file = skill_dir / SKILL_FILENAME
    location = str(skill_file)
    if not skill_file.is_file():
        report.error(str(skill_dir), f"missing {SKILL_FILENAME}")
        return

    parsed = split_frontmatter(skill_file.read_text(encoding="utf-8"))
    if parsed is None:
        report.error(location, "missing or unterminated YAML frontmatter")
        return
    frontmatter_lines, body_lines = parsed
    frontmatter = parse_frontmatter(frontmatter_lines)

    validate_frontmatter(frontmatter, skill_dir, location, report)
    validate_body(body_lines, location, report)

    manifest_path = skill_dir / AGENT_MANIFEST
    if manifest_path.is_file():
        validate_manifest(manifest_path, str(manifest_path), report)


def discover_skill_dirs(skills_root: Path) -> list[Path]:
    """Return every candidate skill directory under the skills root, sorted by name."""
    return sorted(path for path in skills_root.iterdir() if path.is_dir())


def main(argv: list[str] | None = None) -> int:
    """Validate every skill under the requested root and report the outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "skills_root",
        nargs="?",
        default="skills",
        help="directory holding one subdirectory per skill (default: skills)",
    )
    args = parser.parse_args(argv)

    skills_root = Path(args.skills_root)
    if not skills_root.is_dir():
        print(f"error: {skills_root} is not a directory", file=sys.stderr)
        return 1

    report = Report()
    skill_dirs = discover_skill_dirs(skills_root)
    if not skill_dirs:
        print(f"error: no skill directories found under {skills_root}", file=sys.stderr)
        return 1
    for skill_dir in skill_dirs:
        validate_skill(skill_dir, report)

    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)

    if report.errors:
        print(f"\nvalidate_skills: {len(report.errors)} error(s) in {len(skill_dirs)} skill(s)", file=sys.stderr)
        return 1
    print(f"validate_skills: {len(skill_dirs)} skill(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
