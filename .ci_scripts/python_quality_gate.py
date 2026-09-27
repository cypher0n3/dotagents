#!/usr/bin/env python3
"""Reject tracked Python files outside the roots that `just lint-python` checks.

A Python file anywhere else would silently skip every lint gate, so adding a
new root means adding it here and to the lint-python recipe together.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

# Keep in sync with python_roots in the justfile.
OWNED_PYTHON_ROOTS = (".ci_scripts", "scripts")


def uncovered_python_paths(paths: list[str]) -> list[str]:
    """Return the sorted paths that no owned root contains."""
    uncovered = []
    for path in paths:
        normalized = PurePosixPath(path).as_posix()
        if not any(normalized.startswith(root + "/") for root in OWNED_PYTHON_ROOTS):
            uncovered.append(normalized)
    return sorted(uncovered)


def tracked_python_paths(repository_root: Path) -> list[str]:
    """Return the Python files Git tracks, ignoring untracked and ignored files."""
    result = subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    uncovered = uncovered_python_paths(tracked_python_paths(repository_root))
    if uncovered:
        print("Python quality gate does not own these tracked paths:", file=sys.stderr)
        for path in uncovered:
            print(f"  {path}", file=sys.stderr)
        print("Move them under an owned root, or add their root here and in the justfile.", file=sys.stderr)
        return 1
    print("Python quality roots: " + ", ".join(OWNED_PYTHON_ROOTS) + " (all tracked Python files covered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
