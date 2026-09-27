#!/usr/bin/env python3
"""Bash installer tests for skill, agent, and AGENTS.md links."""

from __future__ import annotations

import shutil
import unittest

from install_test_support import HELPER_SOURCE, SKILL_TARGETS, LinkTestCase


class InstallLinksTest(LinkTestCase):
    """Skills are linked per skill, so a tool's own skills never land in the repository."""

    def test_every_target_gets_real_directory_with_one_link_per_skill(self) -> None:
        self.install()
        for target in SKILL_TARGETS:
            directory = self.home / target
            with self.subTest(target=target):
                self.assertTrue(directory.is_dir() and not directory.is_symlink())
                self.assertEqual(sorted(p.name for p in directory.iterdir()), ["alpha", "beta"])
                self.assertEqual((directory / "alpha").resolve(), (self.skills / "alpha").resolve())

    def test_entry_without_skill_file_is_never_linked(self) -> None:
        (self.skills / "synced").mkdir()
        (self.skills / "synced/manifest.json").write_text("{}\n", encoding="utf-8")
        self.install()
        for target in SKILL_TARGETS:
            self.assertFalse((self.home / target / "synced").exists(), target)

    def test_content_written_through_migrated_link_is_reported_not_removed(self) -> None:
        link = self.home / ".claude/skills"
        link.parent.mkdir()
        link.symlink_to(self.skills, target_is_directory=True)
        # What the tool synced through the old whole-directory link.
        (link / "synced").mkdir()
        (link / "synced/manifest.json").write_text("{}\n", encoding="utf-8")
        result = self.install()
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertIn("extra: synced", result.stderr)
        self.assertTrue((self.skills / "synced/manifest.json").is_file())
        self.assertNotIn("extra: alpha", result.stderr)

    def test_whole_directory_link_from_older_install_is_migrated(self) -> None:
        link = self.home / ".claude/skills"
        link.parent.mkdir()
        link.symlink_to(self.skills, target_is_directory=True)
        self.install()
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertEqual(sorted(p.name for p in link.iterdir()), ["alpha", "beta"])
        # A skill the tool writes itself stays out of the repository.
        (link / "vendored").mkdir()
        self.assertFalse((self.skills / "vendored").exists())

    def test_whole_agents_directory_link_from_older_install_is_migrated(self) -> None:
        # Older installs linked ~/.claude/agents to the repository's agents/ directory.
        (self.repo / "agents").mkdir()
        link = self.home / ".claude/agents"
        link.parent.mkdir()
        link.symlink_to(self.repo / "agents", target_is_directory=True)
        result = self.install("--dry-run")
        self.assertIn("would link each file into", result.stdout)
        self.assertTrue(link.is_symlink())
        self.install()
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertEqual(sorted(p.name for p in link.iterdir()), ["helper.md"])
        self.assertEqual((link / "helper.md").resolve(),
                         (self.repo / "generated/claude/agents/helper.md").resolve())
        # An agent the tool or user adds stays out of the repository.
        (link / "local.md").write_text("Local\n", encoding="utf-8")
        self.assertFalse((self.repo / "generated/claude/agents/local.md").exists())

    def test_agent_links_from_the_older_layout_are_relinked(self) -> None:
        agents = self.home / ".claude/agents"
        agents.mkdir(parents=True)
        (agents / "helper.md").symlink_to(self.repo / "agents/helper.md")
        result = self.install()
        self.assertIn("relink: %s" % (agents / "helper.md"), result.stdout)
        self.assertEqual((agents / "helper.md").resolve(),
                         (self.repo / "generated/claude/agents/helper.md").resolve())

    def test_foreign_directory_link_needs_force(self) -> None:
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        link = self.home / ".cursor/skills"
        link.parent.mkdir()
        link.symlink_to(elsewhere, target_is_directory=True)
        result = self.install()
        self.assertIn("use --force", result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.install("--force")
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_dry_run_leaves_whole_directory_link_alone(self) -> None:
        link = self.home / ".claude/skills"
        link.parent.mkdir()
        link.symlink_to(self.skills, target_is_directory=True)
        result = self.install("--dry-run")
        self.assertIn("would link each skill into", result.stdout)
        self.assertTrue(link.is_symlink())
        self.assertEqual(sorted(p.name for p in self.skills.iterdir()), ["alpha", "beta"])

    def test_existing_tool_skills_survive_and_stale_links_are_reported(self) -> None:
        directory = self.home / ".codex/skills"
        (directory / ".system").mkdir(parents=True)
        (directory / "gone").symlink_to(self.skills / "gone")
        result = self.install()
        self.assertTrue((directory / ".system").is_dir())
        self.assertTrue((directory / "gone").is_symlink())
        self.assertIn("stale: gone", result.stderr)

    GENERATED = (
        ("Claude agents", ".claude/agents", "generated/claude/agents", "helper.md", None),
        ("Codex agents", ".codex/agents", "generated/codex/agents", "helper.toml", "--no-codex-agents"),
        ("Cursor agents", ".cursor/agents", "generated/cursor/agents", "helper.md", "--no-cursor-agents"),
    )

    def test_install_generates_and_links_each_file(self) -> None:
        result = self.install()
        self.assertIn("generate_agents: 4 files for 1 agents", result.stdout)
        for label, target, source, name, _ in self.GENERATED:
            with self.subTest(label=label):
                directory = self.home / target
                self.assertTrue(directory.is_dir() and not directory.is_symlink())
                self.assertEqual(sorted(p.name for p in directory.iterdir()), [name])
                self.assertTrue((directory / name).is_symlink())
                self.assertEqual((directory / name).resolve(), (self.repo / source / name).resolve())
        self.assertFalse((self.home / ".config").exists())
        self.assertNotIn("CAI", result.stdout)

    def test_regeneration_keeps_links_current_and_drops_removed_agents(self) -> None:
        self.install()
        source = self.repo / "agent_sources/helper.md"
        source.write_text(HELPER_SOURCE.replace("You help.", "You help more."), encoding="utf-8")
        self.install()
        self.assertIn("You help more.", (self.home / ".claude/agents/helper.md").read_text())
        source.unlink()
        result = self.install()
        self.assertIn("stale: helper.md", result.stderr)
        self.assertTrue((self.home / ".claude/agents/helper.md").is_symlink())

    def test_generated_steps_honor_their_switches_and_dry_run(self) -> None:
        result = self.install("--dry-run")
        for _, target, _, _, _ in self.GENERATED:
            self.assertFalse((self.home / target).exists(), target)
        self.assertIn("would run: ln -sfn", result.stdout)
        result = self.install(*(switch for *_, switch in self.GENERATED if switch))
        for _, target, _, _, switch in self.GENERATED[1:]:
            self.assertIn("skipped (%s)." % switch, result.stdout)
            self.assertFalse((self.home / target).exists(), target)

    def test_invalid_source_fails_the_install(self) -> None:
        (self.repo / "agent_sources/helper.md").write_text(HELPER_SOURCE.replace("schema: 1", "schema: 9"))
        result = self.install(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema must be 1", result.stderr)

    def test_without_python_agents_are_skipped_and_skills_installed(self) -> None:
        tools = self.home / "no-python-bin"
        tools.mkdir()
        for command in ("bash", "dirname", "basename", "readlink", "mkdir", "ln", "rm", "find", "sort", "sed"):
            executable = shutil.which(command)
            if executable:
                (tools / command).symlink_to(executable)
        self.env["PATH"] = str(tools)
        result = self.install()
        self.assertIn("skip: python3 not found", result.stdout)
        self.assertFalse((self.home / ".claude/agents").exists())
        self.assertTrue((self.home / ".claude/skills/alpha").is_symlink())

    def test_generated_collisions_and_leftovers_are_reported_not_replaced(self) -> None:
        agents = self.home / ".cursor/agents"
        agents.mkdir(parents=True)
        (agents / "helper.md").write_text("Mine\n", encoding="utf-8")
        (agents / "retired.md").symlink_to(self.repo / "generated/cursor/agents/retired.md")
        (agents / "local.md").write_text("Local\n", encoding="utf-8")
        result = self.install()
        self.assertIn("exists and is not a symlink", result.stderr)
        self.assertEqual((agents / "helper.md").read_text(), "Mine\n")
        self.assertIn("stale: retired.md", result.stderr)
        self.assertIn("local: local.md", result.stderr)
        self.assertTrue((agents / "retired.md").is_symlink())

    def test_whole_generated_directory_link_is_migrated(self) -> None:
        link = self.home / ".codex/agents"
        link.parent.mkdir()
        (self.repo / "generated/codex/agents").mkdir(parents=True)
        link.symlink_to(self.repo / "generated/codex/agents", target_is_directory=True)
        result = self.install("--dry-run")
        self.assertIn("would link each file into", result.stdout)
        self.assertTrue(link.is_symlink())
        self.install()
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertEqual(sorted(p.name for p in link.iterdir()), ["helper.toml"])

    def test_missing_agent_sources_skip_agent_steps(self) -> None:
        shutil.rmtree(self.repo / "agent_sources")
        result = self.install()
        self.assertIn("skip: no agent sources", result.stdout)
        self.assertFalse((self.home / ".codex/agents").exists())

    def test_reinstall_reports_already_linked(self) -> None:
        self.install()
        result = self.install()
        self.assertIn("already linked", result.stdout)
        self.assertNotIn("linked: ", result.stdout.replace("already linked", ""))


if __name__ == "__main__":
    unittest.main()
