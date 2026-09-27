#!/usr/bin/env python3
"""Offline tests for python_quality_gate.py."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from python_quality_gate import OWNED_PYTHON_ROOTS, uncovered_python_paths

REPO = Path(__file__).resolve().parents[1]


class PythonQualityGateTest(unittest.TestCase):
    def test_owned_roots_cover_helpers_tests_and_installer_scripts(self) -> None:
        paths = [
            ".ci_scripts/generate_agents.py",
            ".ci_scripts/test_generate_agents.py",
            "scripts/install_settings.py",
        ]
        self.assertEqual(uncovered_python_paths(paths), [])

    def test_python_outside_the_owned_roots_is_rejected(self) -> None:
        paths = ["tools/new_gate.py", "setup.py", "scripts_extra/x.py"]
        self.assertEqual(uncovered_python_paths(paths), ["scripts_extra/x.py", "setup.py", "tools/new_gate.py"])

    def test_justfile_lints_the_same_roots(self) -> None:
        justfile = (REPO / "justfile").read_text(encoding="utf-8")
        match = re.search(r'^python_roots := "([^"]*)"$', justfile, re.MULTILINE)
        self.assertIsNotNone(match, "justfile must define python_roots")
        self.assertEqual(tuple(match.group(1).split()), OWNED_PYTHON_ROOTS)


if __name__ == "__main__":
    unittest.main()
