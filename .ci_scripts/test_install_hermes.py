#!/usr/bin/env python3
"""Bash installer tests for registering skills and personalities with Hermes."""

from __future__ import annotations

import json
import os
import shutil
import unittest

from install_test_support import REPO, InstallerTestCase


class HermesSkillsTest(InstallerTestCase):
    """Hermes gains the skills directory through its own CLI, never by a direct write."""

    def test_hermes_appends_skills_preserving_config_and_original_backup(self):
        config = self.seed_hermes(["~/team-skills"])
        original = config.read_bytes()
        self.install()
        data = json.loads(config.read_text())
        self.assertEqual(data["skills"]["external_dirs"], ["~/team-skills", str(REPO / "skills")])
        self.assertEqual(data["skills"]["config"], {"keep": True})
        self.assertEqual(data["model"], {"default": "keep"})
        backups = self.backups(config)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].name[len(config.name):],
                         self.backups(self.paths[0])[0].name[len(self.paths[0].name):])
        self.assertEqual((config.parent / "SOUL.md").read_text(), "User identity\n")
        self.assertEqual((config.parent / "skills/local-skill/SKILL.md").read_text(), "Local skill\n")
        self.assertFalse((config.parent / "AGENTS.md").exists())
        after = config.read_bytes()
        self.install()
        self.assertEqual(config.read_bytes(), after)
        self.assertEqual(self.backups(config), backups)

    def test_hermes_dry_run_does_not_invoke_cli_or_change_config(self):
        config = self.seed_hermes()
        before = {str(p.relative_to(config.parent)): p.read_bytes()
                  for p in config.parent.rglob("*") if p.is_file()}
        result = self.install("--dry-run")
        self.assertIn("would append", result.stdout)
        self.assertIn(str(config), result.stdout)
        after = {str(p.relative_to(config.parent)): p.read_bytes()
                 for p in config.parent.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.home / "hermes-calls").exists())

    def test_no_hermes_skips_config_even_when_installed(self):
        config = self.seed_hermes()
        original = config.read_bytes()
        self.install("--no-hermes")
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(self.backups(config), [])
        self.assertFalse((self.home / "hermes-calls").exists())

    def test_hermes_custom_home_and_independent_settings_step(self):
        config = self.seed_hermes(config_home=self.home / "custom profile")
        default = self.home / ".hermes/config.yaml"
        default.parent.mkdir()
        default.write_text("untouched default\n", encoding="utf-8")
        self.install("--no-statusline", "--no-attribution")
        self.assertEqual(json.loads(config.read_text())["skills"]["external_dirs"], [str(REPO / "skills")])
        self.assertEqual(default.read_text(), "untouched default\n")
        self.assertEqual(self.backups(default), [])
        for path, original in zip(self.paths, self.originals):
            self.assertEqual(path.read_bytes(), original)

    def test_hermes_equivalent_path_is_noop(self):
        config = self.seed_hermes()
        for value in (str(REPO / "skills"), str(REPO / "skills/../skills"),
                      "${DOTAGENTS_TEST_REPO}/skills", "~/shared-skills"):
            with self.subTest(path=value):
                link = self.home / "shared-skills"
                if not link.exists():
                    link.symlink_to(REPO / "skills", target_is_directory=True)
                config.write_text(json.dumps({"skills": {"external_dirs": [value]}}))
                original = (config.read_bytes(), config.stat().st_mtime_ns)
                self.install(extra_env={"DOTAGENTS_TEST_REPO": str(REPO)})
                self.assertEqual((config.read_bytes(), config.stat().st_mtime_ns), original)
                self.assertEqual(self.backups(config), [])

    def test_hermes_append_preserves_cli_resolved_directories(self):
        config = self.seed_hermes(["${DOTAGENTS_TEAM}/skills"])
        original = config.read_bytes()
        team = str(self.home / "team")
        env = {"DOTAGENTS_TEAM": team, "DOTAGENTS_HERMES_TEST_MODE": "expand-env"}
        self.install(extra_env=env)
        self.assertEqual(json.loads(config.read_text())["skills"]["external_dirs"],
                         [team + "/skills", str(REPO / "skills")])
        backups = self.backups(config)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        installed = config.read_bytes()
        self.install(extra_env=env)
        self.assertEqual(config.read_bytes(), installed)
        self.assertEqual(self.backups(config), backups)

    def test_hermes_relative_paths_are_based_on_hermes_home(self):
        config = self.seed_hermes(["skills"])
        self.install()
        self.assertEqual(json.loads(config.read_text())["skills"]["external_dirs"],
                         ["skills", str(REPO / "skills")])
        # ".." follows the physical path, so relate to the resolved home
        # (macOS temp dirs sit under the /var -> /private/var symlink).
        relative = os.path.relpath(REPO / "skills", config.parent.resolve())
        config.write_text(json.dumps({"skills": {"external_dirs": [" " + relative + " "]}}))
        before = config.read_bytes()
        backups = self.backups(config)
        self.install()
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(self.backups(config), backups)

    def test_hermes_blank_home_uses_default(self):
        config = self.seed_hermes()
        self.install(extra_env={"HERMES_HOME": "  "})
        self.assertEqual(json.loads(config.read_text())["skills"]["external_dirs"], [str(REPO / "skills")])

    def test_hermes_missing_config_does_not_invoke_cli(self):
        config = self.seed_hermes()
        config.unlink()
        self.install()
        self.assertFalse(config.exists())
        self.assertFalse((self.home / "hermes-calls").exists())
        self.assertEqual(self.backups(config), [])

    def test_hermes_missing_cli_preserves_config(self):
        config = self.seed_hermes()
        original = config.read_bytes()
        tools = self.home / "without-hermes"
        tools.mkdir()
        for command in ("bash", "dirname", "basename", "readlink", "mkdir", "ln", "python3"):
            executable = shutil.which(command)
            if executable:
                (tools / command).symlink_to(executable)
        result = self.install(extra_env={"PATH": str(tools)})
        self.assertIn("hermes command not found", result.stdout)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(self.backups(config), [])

    def test_hermes_bad_reads_fail_before_backup_or_write(self):
        config = self.seed_hermes()
        original = config.read_bytes()
        for mode in ("wrong-path", "read-fail", "bad-json"):
            with self.subTest(mode=mode):
                result = self.install(extra_env={"DOTAGENTS_HERMES_TEST_MODE": mode}, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(self.backups(config), [])
        for value in ("not-a-list", {"bad": "mapping"}, [3]):
            with self.subTest(value=value):
                config.write_text(json.dumps({"skills": {"external_dirs": value}}))
                original = config.read_bytes()
                result = self.install(check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(self.backups(config), [])

    def test_hermes_failed_or_ineffective_writes_keep_original_backup(self):
        config = self.seed_hermes()
        original = config.read_bytes()
        for mode in ("write-fail", "no-write"):
            with self.subTest(mode=mode):
                previous = set(self.backups(config))
                result = self.install(extra_env={"DOTAGENTS_HERMES_TEST_MODE": mode}, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(config.read_bytes(), original)
                new = set(self.backups(config)) - previous
                self.assertEqual(len(new), 1)
                self.assertEqual(new.pop().read_bytes(), original)


class HermesPersonalitiesTest(InstallerTestCase):
    """Personalities are added, updated only when owned, and replaced only with --force."""

    def test_hermes_personalities_are_added_with_one_shared_backup(self):
        config = self.seed_hermes()
        original = config.read_bytes()
        result = self.install(personalities=True)
        names = sorted(p.stem for p in (REPO / "generated/hermes/personalities").glob("*.yaml"))
        self.assertEqual(sorted(self.personalities(config)), names)
        self.assertEqual(self.personalities(config)["reviewer"], self.generated_personality("reviewer"))
        self.assertIn("added: personality reviewer", result.stdout)
        backups = self.backups(config)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        owned = self.state()["hermes_personalities"][str(config.resolve())]
        self.assertEqual(sorted(owned), names)
        after = config.read_bytes()
        result = self.install(personalities=True)
        self.assertIn("ok: personality reviewer is current", result.stdout)
        self.assertEqual(config.read_bytes(), after)
        self.assertEqual(self.backups(config), backups)

    def test_hermes_owned_personality_is_updated_without_force(self):
        config = self.seed_hermes()
        self.install(personalities=True)
        # An older render this installer set, and recorded as its own.
        older = {"description": "old", "system_prompt": "old prompt"}
        data = json.loads(config.read_text())
        data["agent"]["personalities"]["reviewer"] = older
        config.write_text(json.dumps(data))
        state_path = self.home / ".local/state/dotagents/install-state.json"
        state = self.state()
        digest = "sha256:" + __import__("hashlib").sha256(b"old\0old prompt").hexdigest()
        state["hermes_personalities"][str(config.resolve())]["reviewer"] = digest
        state_path.write_text(json.dumps(state))
        result = self.install(personalities=True)
        self.assertIn("updated: personality reviewer", result.stdout)
        self.assertEqual(self.personalities(config)["reviewer"], self.generated_personality("reviewer"))

    def test_hermes_foreign_or_edited_personality_needs_force(self):
        config = self.seed_hermes()
        mine = {"description": "mine", "system_prompt": "my own reviewer"}
        data = json.loads(config.read_text())
        data["agent"] = {"personalities": {"reviewer": mine, "pirate": "Talk like a pirate."}}
        config.write_text(json.dumps(data))
        result = self.install(personalities=True)
        self.assertIn("skip: personality reviewer exists and was not set by this installer", result.stdout)
        self.assertEqual(self.personalities(config)["reviewer"], mine)
        self.assertEqual(self.personalities(config)["pirate"], "Talk like a pirate.")
        self.assertNotIn("reviewer", self.state()["hermes_personalities"][str(config.resolve())])
        # A personality this installer set and the user then edited is theirs too.
        edited = dict(self.personalities(config)["coder"], tone="terse")
        data = json.loads(config.read_text())
        data["agent"]["personalities"]["coder"] = edited
        config.write_text(json.dumps(data))
        result = self.install(personalities=True)
        self.assertIn("skip: personality coder exists", result.stdout)
        self.assertEqual(self.personalities(config)["coder"], edited)
        result = self.install("--force", personalities=True)
        self.assertIn("replaced (--force", result.stdout)
        self.assertEqual(self.personalities(config)["reviewer"], self.generated_personality("reviewer"))
        self.assertEqual(self.personalities(config)["coder"], self.generated_personality("coder"))
        self.assertEqual(self.personalities(config)["pirate"], "Talk like a pirate.")
        self.assertTrue(any(b"my own reviewer" in backup.read_bytes() for backup in self.backups(config)))

    def test_hermes_personality_for_removed_role_is_reported_not_removed(self):
        config = self.seed_hermes()
        self.install(personalities=True)
        state_path = self.home / ".local/state/dotagents/install-state.json"
        state = self.state()
        state["hermes_personalities"][str(config.resolve())]["retired"] = "sha256:0"
        state_path.write_text(json.dumps(state))
        data = json.loads(config.read_text())
        data["agent"]["personalities"]["retired"] = {"description": "x", "system_prompt": "y"}
        config.write_text(json.dumps(data))
        result = self.install(personalities=True)
        self.assertIn("note: personality retired was set by this installer, but its role no longer exists",
                      result.stdout)
        self.assertIn("retired", self.personalities(config))

    def test_hermes_personalities_dry_run_and_switches_never_write(self):
        config = self.seed_hermes()
        original = config.read_bytes()
        result = self.install("--dry-run", personalities=True)
        self.assertIn("would set agent.personalities.reviewer", result.stdout)
        self.assertFalse((self.home / "hermes-calls").exists())
        self.assertEqual(config.read_bytes(), original)
        result = self.install("--no-hermes-personalities", personalities=True)
        self.assertIn("skipped (--no-hermes-personalities).", result.stdout)
        self.assertEqual(self.personalities(config), {})
        result = self.install("--no-hermes", personalities=True)
        self.assertEqual(result.stdout.count("skipped (--no-hermes)."), 2)
        self.assertEqual(self.personalities(config), {})
        self.assertIsNone(self.state())

    def test_hermes_personality_failures_keep_config_and_state(self):
        config = self.seed_hermes()
        for mode in ("personalities-bad", "personality-no-write"):
            with self.subTest(mode=mode):
                result = self.install(extra_env={"DOTAGENTS_HERMES_TEST_MODE": mode}, check=False,
                                      personalities=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.personalities(config), {})
                self.assertIsNone(self.state())


if __name__ == "__main__":
    unittest.main()
