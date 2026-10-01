#!/usr/bin/env python3
"""Bash installer tests for exposing a clone outside ~/.agents to CAI."""

from __future__ import annotations

import os
import unittest

from install_test_support import LinkTestCase


class InstallCaiTest(LinkTestCase):
    """CAI reads ~/.agents only, so a clone elsewhere is linked there when CAI is installed."""

    def setUp(self) -> None:
        super().setUp()
        self.agents_home = self.home / ".agents"
        # This repository's own rules, which CAI must never load as global instructions.
        (self.repo / "AGENTS.override.md").write_text("Repository rules\n", encoding="utf-8")

    def install_cai(self) -> None:
        (self.home / ".config/cai").mkdir(parents=True, exist_ok=True)

    def test_clone_elsewhere_is_linked_into_agents_home(self) -> None:
        self.install_cai()
        self.install()
        self.assertEqual((self.agents_home / "AGENTS.md").resolve(), (self.repo / "AGENTS.md").resolve())
        skills = self.agents_home / "skills"
        self.assertTrue(skills.is_dir() and not skills.is_symlink())
        for name in ("alpha", "beta"):
            self.assertEqual((skills / name).resolve(), (self.skills / name).resolve())
        # agent_sources/ is one directory link, so CAI's /model writes land in the clone.
        sources = self.agents_home / "agent_sources"
        self.assertTrue(sources.is_symlink())
        self.assertEqual(sources.resolve(), (self.repo / "agent_sources").resolve())
        self.assertFalse((self.agents_home / "AGENTS.override.md").exists())

        result = self.install()
        self.assertNotIn("linked: ", result.stdout.replace("already linked", ""))

    def test_xdg_config_home_locates_cai(self) -> None:
        config = self.home / "xdg"
        (config / "cai").mkdir(parents=True)
        self.env["XDG_CONFIG_HOME"] = str(config)
        self.install()
        self.assertTrue((self.agents_home / "agent_sources").is_symlink())

    def test_without_cai_nothing_is_created(self) -> None:
        result = self.install()
        self.assertIn("skip: CAI configuration not found", result.stdout)
        self.assertFalse(self.agents_home.exists())

    def test_clone_at_agents_home_needs_nothing(self) -> None:
        self.install_cai()
        self.agents_home.symlink_to(self.repo)
        result = self.install()
        self.assertIn("ok: CAI reads this clone", result.stdout)
        self.assertFalse((self.repo / "agent_sources/agent_sources").exists())

    def test_switch_dry_run_and_blocked_home_change_nothing(self) -> None:
        self.install_cai()
        self.assertIn("skipped (--no-cai)", self.install("--no-cai").stdout)
        self.install("--dry-run")
        self.assertFalse(self.agents_home.exists())

        self.agents_home.write_text("not a directory\n", encoding="utf-8")
        result = self.install()
        self.assertIn("is not a directory", result.stderr)
        self.assertEqual(self.agents_home.read_text(encoding="utf-8"), "not a directory\n")

    def test_existing_entries_are_not_replaced_without_force(self) -> None:
        self.install_cai()
        own_sources = self.home / "my-agents"
        own_sources.mkdir()
        self.agents_home.mkdir()
        (self.agents_home / "agent_sources").symlink_to(own_sources)
        (self.agents_home / "AGENTS.md").write_text("Mine\n", encoding="utf-8")
        result = self.install()
        self.assertIn("(use --force to replace)", result.stderr)
        self.assertEqual(os.readlink(self.agents_home / "agent_sources"), str(own_sources))
        self.assertEqual((self.agents_home / "AGENTS.md").read_text(encoding="utf-8"), "Mine\n")


if __name__ == "__main__":
    unittest.main()
