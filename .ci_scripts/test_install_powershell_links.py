#!/usr/bin/env python3
"""PowerShell installer tests for generated agents and skill links."""

import json
import os
import shutil
import subprocess
import unittest
import warnings

from powershell_test_support import FAKE_HERMES, REPO, PowerShellTestCase


class PowerShellLinksTest(PowerShellTestCase):
    """Agents and skills are linked per file, preferring symbolic links."""

    # Each installed agent directory, the generated directory it mirrors, and its files.
    GENERATED = ((".claude/agents", "generated/claude/agents", "*.md"),
                 (".codex/agents", "generated/codex/agents", "*.toml"),
                 (".cursor/agents", "generated/cursor/agents", "*.md"))

    def test_install_generates_and_installs_agents_per_file(self):
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes")
        self.assertIn("generate_agents: ", result.stdout)
        for target, source, pattern in self.GENERATED:
            with self.subTest(target=target):
                expected = sorted(p.name for p in (REPO / source).glob(pattern))
                self.assertTrue(expected)
                self.assertEqual(sorted(p.name for p in (self.home / target).iterdir()), expected)
                for name in expected:
                    self.assertEqual((self.home / target / name).read_bytes(), (REPO / source / name).read_bytes())
        self.assertNotIn("CAI", result.stdout)

    def test_symbolic_links_are_used_when_available(self):
        if os.name == "nt":
            self.skipTest("the Windows runner's symbolic link rights are not controlled here")
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes", copy=False)
        self.assertIn("agent files are installed as symbolic links", result.stdout)
        link = self.home / ".claude/agents/reviewer.md"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (REPO / "generated/claude/agents/reviewer.md").resolve())
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes", copy=False)
        self.assertIn("ok: " + str(link) + " (already linked)", result.stdout)

    def test_older_layout_links_and_owned_copies_become_symbolic_links(self):
        if os.name == "nt":
            self.skipTest("the Windows runner's symbolic link rights are not controlled here")
        self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes")
        copied = self.home / ".claude/agents/coder.md"
        self.assertFalse(copied.is_symlink())
        old = self.home / ".claude/agents/reviewer.md"
        old.unlink()
        old.symlink_to(REPO / "agents/reviewer.md")
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes", copy=False)
        self.assertIn("relink: " + str(old), result.stdout)
        self.assertEqual(old.resolve(), (REPO / "generated/claude/agents/reviewer.md").resolve())
        self.assertTrue(copied.is_symlink())

    def test_generated_agent_switches(self):
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes",
                                    "-NoCodexAgents", "-NoCursorAgents")
        self.assertIn("skipped (-NoCodexAgents).", result.stdout)
        self.assertIn("skipped (-NoCursorAgents).", result.stdout)
        self.assertFalse((self.home / ".codex/agents").exists())
        self.assertFalse((self.home / ".cursor/agents").exists())
        self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes", "-DryRun")
        self.assertFalse((self.home / ".codex/agents").exists())

    def test_without_python_agent_steps_are_skipped(self):
        path = self.seed_hermes([])
        result = self.run_installer("-NoStatusline", "-NoAttribution",
                                    setup=FAKE_HERMES + "; $env:PATH = ''", personalities=True)
        self.assertIn("Python 3.9 or newer not found", result.stdout)
        self.assertFalse((self.home / ".claude/agents").exists())
        self.assertEqual(self.personalities(path), {})

    def test_stale_installed_file_is_refreshed_but_user_edit_needs_force(self):
        self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes")
        installed = self.home / ".claude/agents/reviewer.md"
        source = REPO / "generated/claude/agents/reviewer.md"
        # What regeneration leaves behind: the old content this installer placed.
        # Write bytes, since text mode would add a carriage return on Windows.
        installed.write_bytes(b"older generation\n")
        state_path = self.state_path()
        state = json.loads(state_path.read_text())
        keys = [key for key in state["file_links"] if os.path.normcase(key) == os.path.normcase(str(installed))]
        self.assertEqual(len(keys), 1, sorted(state["file_links"]))
        state["file_links"][keys[0]] = __import__("hashlib").sha256(b"older generation\n").hexdigest()
        state_path.write_text(json.dumps(state))
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes")
        self.assertIn("refresh: " + str(installed), result.stdout)
        self.assertEqual(installed.read_bytes(), source.read_bytes())
        # A user's edit does not match the record, so it stays unless -Force.
        installed.write_bytes(b"my edit\n")
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes")
        self.assertIn("skip: " + str(installed) + " differs from source", result.stdout)
        self.assertEqual(installed.read_bytes(), b"my edit\n")

    def test_whole_directory_junction_from_older_install_is_migrated(self):
        if os.name != "nt":
            reason = "junctions exist only on Windows"
            warnings.warn("Junction migration is NOT tested on this system: " + reason,
                          stacklevel=1)
            self.skipTest(reason)
        skills = REPO / "skills"
        link = self.home / ".claude/skills"
        shutil.rmtree(link)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(skills)],
                       check=True, capture_output=True)
        self.run_installer("-NoStatusline", "-NoAttribution", "-NoHermes")
        expected = sorted(p.name for p in skills.iterdir() if (p / "SKILL.md").is_file())
        self.assertTrue(link.is_dir() and not link.is_junction())
        self.assertEqual(sorted(p.name for p in link.iterdir()), expected)
        for name in expected:
            self.assertTrue((skills / name / "SKILL.md").is_file(), name)


if __name__ == "__main__":
    unittest.main()
