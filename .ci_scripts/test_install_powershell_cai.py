#!/usr/bin/env python3
"""PowerShell installer tests for exposing a clone outside ~/.agents to CAI."""

import os
import subprocess
import unittest

from powershell_test_support import REPO, PowerShellTestCase

QUIET = ("-NoStatusline", "-NoAttribution", "-NoHermes")


class PowerShellCaiTest(PowerShellTestCase):
    """CAI reads ~/.agents only, so a clone elsewhere is linked there when CAI is installed."""

    def setUp(self):
        super().setUp()
        self.agents_home = self.home / ".agents"

    def test_clone_elsewhere_is_linked_into_agents_home(self):
        (self.home / ".config/cai").mkdir(parents=True)
        self.run_installer(*QUIET)
        installed = self.agents_home / "AGENTS.md"
        self.assertEqual(installed.read_bytes(), (REPO / "AGENTS.md").read_bytes())
        skills = self.agents_home / "skills"
        linked = sorted(p.name for p in skills.iterdir())
        expected = sorted(p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").is_file())
        self.assertEqual(linked, expected)
        self.assertEqual((skills / expected[0]).resolve(), (REPO / "skills" / expected[0]).resolve())
        self.assertEqual((self.agents_home / "agent_sources").resolve(), (REPO / "agent_sources").resolve())
        self.assertFalse((self.agents_home / "AGENTS.override.md").exists())

        result = self.run_installer(*QUIET)
        self.assertIn("ok: " + str(self.agents_home / "agent_sources"), result.stdout.replace("/", os.sep))

    def test_without_cai_or_with_the_switch_nothing_is_created(self):
        result = self.run_installer(*QUIET)
        self.assertIn("skip: CAI configuration not found", result.stdout)
        (self.home / ".config/cai").mkdir(parents=True)
        result = self.run_installer(*QUIET, "-NoCai")
        self.assertIn("skipped (-NoCai)", result.stdout)
        self.assertFalse(self.agents_home.exists())

    def test_clone_at_agents_home_needs_nothing(self):
        (self.home / ".config/cai").mkdir(parents=True)
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(self.agents_home), str(REPO)],
                           check=True, capture_output=True)
        else:
            self.agents_home.symlink_to(REPO)
        result = self.run_installer(*QUIET)
        self.assertIn("ok: CAI reads this clone", result.stdout)
        self.assertFalse((REPO / "agent_sources/agent_sources").exists())


if __name__ == "__main__":
    unittest.main()
