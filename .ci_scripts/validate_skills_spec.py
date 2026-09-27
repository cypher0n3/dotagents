#!/usr/bin/env python3
"""Validate the skills under skills/ with the Agent Skills reference validator.

Runs the validator from the skills-ref package on every skill directory. The
PyPI release installs it as `agentskills`; the source tree installs it as
`skills-ref`. Either is accepted, and `agentskills` is preferred.

The reference validator rejects every frontmatter field the specification does
not define. Fields listed in validate_skills.CLIENT_KEYS are read directly by
agent tools, so they are accepted without comment. Every other reported
problem is an error, and so is validator output this script cannot parse, so a
change in the validator's wording fails loudly rather than passing.

When the validator is not installed the check is skipped with a notice, except
under CI (the CI environment variable is set), where a missing validator is an
error so the check cannot silently stop running.

Exit status is 0 when every skill passes or the check is skipped, and 1 when
any error is reported.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from validate_skills import CLIENT_KEYS, discover_skill_dirs

VALIDATOR_COMMANDS = ("agentskills", "skills-ref")
PINNED_PACKAGE = "skills-ref==0.1.1"

VALID_PREFIX = "Valid skill"
FAILED_HEADER = re.compile(r"^Validation failed for .+:$")
PROBLEM_LINE = re.compile(r"^\s+- (.+)$")
UNEXPECTED_FIELDS = re.compile(r"^Unexpected fields in frontmatter: (.+?)\. Only \[.*\] are allowed\.$")


def validator_command() -> list[str] | None:
    """Return the command that runs the reference validator, or None when it is absent."""
    for name in VALIDATOR_COMMANDS:
        path = shutil.which(name)
        if path:
            return [path]
    return None


def running_in_ci() -> bool:
    """Report whether the CI environment variable marks this as a CI run."""
    return os.environ.get("CI", "").strip().lower() not in ("", "0", "false")


def check_skill(command: list[str], skill_dir: Path) -> list[str]:
    """Run the validator on one skill and return its errors, accepting client fields."""
    result = subprocess.run(
        [*command, "validate", str(skill_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if not result.returncode:
        if output.startswith(VALID_PREFIX):
            return []
        return [f"{skill_dir}: validator passed with unrecognized output: {output!r}"]

    lines = output.splitlines()
    if not lines or not FAILED_HEADER.match(lines[0]):
        return [f"{skill_dir}: validator exited {result.returncode} with unrecognized output: {output!r}"]
    problems = []
    for line in lines[1:]:
        match = PROBLEM_LINE.match(line)
        if not match:
            return [f"{skill_dir}: unrecognized validator output line: {line!r}"]
        problems.append(match.group(1))
    if not problems:
        return [f"{skill_dir}: validator exited {result.returncode} without reporting a problem"]

    errors = []
    for problem in problems:
        fields = UNEXPECTED_FIELDS.match(problem)
        if not fields:
            errors.append(f"{skill_dir}: {problem}")
            continue
        unexpected = [name for name in fields.group(1).split(", ") if name not in CLIENT_KEYS]
        if unexpected:
            errors.append(f"{skill_dir}: frontmatter fields outside the specification: {', '.join(unexpected)}")
    return errors


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

    command = validator_command()
    names = " or ".join(VALIDATOR_COMMANDS)
    if command is None:
        if running_in_ci():
            print(f"error: {names} not found on PATH; install {PINNED_PACKAGE}", file=sys.stderr)
            return 1
        print(f"validate_skills_spec: {names} not installed; skipping specification validation.")
        print(f"Install it with: uv tool install {PINNED_PACKAGE} (or pipx install {PINNED_PACKAGE})")
        return 0

    skill_dirs = discover_skill_dirs(skills_root)
    if not skill_dirs:
        print(f"error: no skill directories found under {skills_root}", file=sys.stderr)
        return 1

    errors = []
    for skill_dir in skill_dirs:
        errors.extend(check_skill(command, skill_dir))

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(f"\nvalidate_skills_spec: {len(errors)} error(s) in {len(skill_dirs)} skill(s)", file=sys.stderr)
        return 1
    print(f"validate_skills_spec: {len(skill_dirs)} skill(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
