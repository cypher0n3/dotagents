#!/usr/bin/env python3
"""PowerShell installer tests for registering skills and personalities with Hermes."""

import json
import os
import unittest

from powershell_test_support import FAKE_HERMES, REPO, PowerShellTestCase


class PowerShellHermesSkillsTest(PowerShellTestCase):
    """Hermes gains the skills directory through its own CLI, never by a direct write."""

    def test_hermes_appends_preserving_settings_with_original_shared_backup(self):
        self.seed_settings()
        path = self.seed_hermes(["~/my skills", "relative/skills"])
        original = path.read_bytes()
        self.run_installer(setup=FAKE_HERMES)
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(config["skills"]["external_dirs"],
                         ["~/my skills", "relative/skills", str(REPO / "skills")])
        self.assertEqual(config["skills"]["keep"], "skills option")
        self.assertEqual(config["keep"], {"model": "untouched"})
        self.assertEqual(len(self.backups(path)), 1)
        self.assertEqual(self.backups(path)[0].read_bytes(), original)
        stamps = {self.backups(p)[0].name[len(p.name) + 1:-4] for p in [*self.paths, path]}
        self.assertEqual(len(stamps), 1)
        self.assertEqual([call["args"][:2] for call in self.hermes_calls()],
                         [["config", "path"], ["config", "get"], ["config", "set"], ["config", "get"]])
        for call in self.hermes_calls():
            self.assertEqual(call["home"], str(path.parent))
        self.assertEqual(set(p.name for p in path.parent.iterdir()),
                         {path.name, self.backups(path)[0].name})

    def test_hermes_repeat_install_is_noop_even_with_other_features_disabled(self):
        path = self.seed_hermes(["~/team skills"])
        self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES)
        snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in [path, *self.backups(path)]}
        self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES)
        self.assertEqual(snapshot, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                    for p in [path, *self.backups(path)]})
        self.assertEqual(sum(c["args"][1] == "set" for c in self.hermes_calls()), 1)

    def test_hermes_equivalent_paths_preserve_original_list_without_backup(self):
        equivalents = [str(REPO / "skills"), str(REPO / "skills") + "/../skills/",
                       "$DOTAGENTS_REPO/skills", "${DOTAGENTS_REPO}/skills",
                       " \t" + str(REPO / "skills") + " \t"]
        # No relative path spans two Windows drives, such as a checkout on D:
        # and a temporary home on C:.
        if REPO.drive == self.home.drive:
            equivalents += [os.path.relpath(REPO / "skills", self.home / ".hermes"),
                            "~/" + os.path.relpath(REPO / "skills", self.home)]
        if os.name == "nt":
            equivalents.append("%DOTAGENTS_REPO%/skills")
        for equivalent in equivalents:
            with self.subTest(path=equivalent):
                path = self.seed_hermes(["~/keep", equivalent, "~/keep"])
                original = (path.read_bytes(), path.stat().st_mtime_ns)
                self.run_installer("-NoStatusline", "-NoAttribution",
                                   setup=FAKE_HERMES + "; Set-Location (Join-Path $HOME '.claude/skills')",
                                   extra_env={"DOTAGENTS_REPO": str(REPO)})
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), original)
                self.assertEqual(self.backups(path), [])
        self.assertFalse(any(c["args"][1] == "set" for c in self.hermes_calls()))

    def test_hermes_custom_home_is_trimmed_pinned_and_restored(self):
        default = self.seed_hermes(["default"])
        custom = self.seed_hermes(["custom"], self.home / "custom hermes")
        profile = self.seed_hermes(["profile"], default.parent / "profiles/sticky")
        (default.parent / "active_profile").write_text("sticky\n")
        untouched = {p: p.read_bytes() for p in (default, profile)}
        inherited = " \t" + str(custom.parent) + " \t"
        self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES,
                           extra_env={"HERMES_HOME": inherited})
        self.assertEqual(json.loads(custom.read_text(encoding="utf-8-sig"))["skills"]["external_dirs"],
                         ["custom", str(REPO / "skills")])
        self.assertTrue(self.hermes_calls())
        self.assertTrue(all(c["home"] == str(custom.parent) for c in self.hermes_calls()))
        for path, original in untouched.items():
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.backups(path), [])

    def test_hermes_default_home_is_pinned_without_following_active_profile(self):
        # Exercise both platform branches, without claiming Windows filesystem coverage.
        cases = [(False, "", self.home / ".hermes"),
                 (True, str(self.home / "local app data"), self.home / "local app data/hermes"),
                 (True, "", self.home / "AppData/Local/hermes")]
        for windows, local_appdata, expected in cases:
            with self.subTest(windows=windows, local_appdata=local_appdata):
                path = self.seed_hermes([], expected)
                for inherited in (" \t", "", None):
                    setup = FAKE_HERMES + "; Set-Variable IsWindows -Force -Value $" + str(windows).lower()
                    if inherited is None:
                        setup += "; Remove-Item Env:HERMES_HOME -ErrorAction SilentlyContinue"
                    self.run_installer("-NoStatusline", "-NoAttribution", setup=setup,
                                       extra_env={"HERMES_HOME": inherited or "", "LOCALAPPDATA": local_appdata})
                    self.assertEqual(json.loads(path.read_text(encoding="utf-8-sig"))["skills"]["external_dirs"],
                                     [str(REPO / "skills")])
                    self.assertEqual(self.hermes_calls()[-1]["home"], str(expected))

    def test_hermes_dry_run_and_no_hermes_never_invoke_cli(self):
        path = self.seed_hermes([])
        original = path.read_bytes()
        for flag in ("-DryRun", "-NoHermes"):
            with self.subTest(flag=flag):
                result = self.run_installer(flag, setup=FAKE_HERMES)
                self.assertIn("would append" if flag == "-DryRun" else "skipped (-NoHermes)", result.stdout)
                self.assertEqual(self.hermes_calls(), [])
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.backups(path), [])

    def test_hermes_missing_config_or_cli_skips_without_creating_state(self):
        missing = self.home / "not installed"
        for flags in ((), ("-DryRun",)):
            result = self.run_installer(*flags, setup=FAKE_HERMES, extra_env={"HERMES_HOME": str(missing)})
            self.assertIn("skip: Hermes config", result.stdout)
            self.assertEqual(self.hermes_calls(), [])
            self.assertFalse(missing.exists())
        path = self.seed_hermes([])
        original = path.read_bytes()
        for flags in ((), ("-DryRun",)):
            result = self.run_installer(*flags, setup="$env:PATH = ''")
            self.assertIn("skip: Hermes CLI", result.stdout)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.backups(path), [])

    def test_hermes_rejects_invalid_reads_before_backup_or_set(self):
        cases = [{"FAKE_HERMES_JSON": raw} for raw in
                 ('"scalar"', '{}', '42', 'false', '[1]', '[null]', '[["nested"]]',
                  json.dumps([str(REPO / "skills"), 1]), '{broken', ' ')]
        cases += [{"FAKE_HERMES_MODE": "read-failure"},
                  {"FAKE_HERMES_PATH": str(self.home / "wrong/config.yaml")}]
        for index, overrides in enumerate(cases):
            with self.subTest(overrides=overrides):
                path = self.seed_hermes(["original"], self.home / f"bad-read-{index}")
                original = path.read_bytes()
                result = self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES,
                                            extra_env={**overrides, "HERMES_HOME": str(path.parent)}, check=False)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("home not restored", result.stderr)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.backups(path), [])
        self.assertFalse(any(c["args"][1] == "set" for c in self.hermes_calls()))

    def test_hermes_null_and_empty_lists_append_one_string(self):
        for directories in (None, []):
            with self.subTest(directories=directories):
                path = self.seed_hermes(directories)
                self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES)
                self.assertEqual(json.loads(path.read_text())["skills"]["external_dirs"],
                                 [str(REPO / "skills")])

    def test_hermes_set_failure_or_silent_no_write_fails_and_restores_home(self):
        for mode, message in (("set-failure", "failed"), ("no-write", "verification failed")):
            with self.subTest(mode=mode):
                path = self.seed_hermes(["keep"], self.home / mode)
                original = path.read_bytes()
                inherited = str(path.parent)
                result = self.run_installer(
                    "-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, check=False,
                    extra_env={"HERMES_HOME": inherited, "FAKE_HERMES_MODE": mode})
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(message, result.stderr)
                self.assertNotIn("home not restored", result.stderr)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(len(self.backups(path)), 1)
                self.assertEqual(self.backups(path)[0].read_bytes(), original)

    def test_hermes_backup_collision_aborts_before_set(self):
        path = self.seed_hermes([])
        original = path.read_bytes()
        setup = FAKE_HERMES + '''
            function Get-Date { [datetime]::new(2026, 1, 2, 3, 4, 5) }
            $stamp = (Get-Date).ToString("yyyyMMdd'T'HHmmss.ffffffzzz",
                [System.Globalization.CultureInfo]::InvariantCulture).Replace(':', '')
            $collision = (Join-Path $env:HERMES_HOME 'config.yaml') + '.' + $stamp + '.bak'
            [IO.File]::WriteAllText($collision, 'older snapshot')
        '''
        result = self.run_installer("-NoStatusline", "-NoAttribution", setup=setup, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual([p.read_bytes() for p in self.backups(path)], [b"older snapshot"])
        self.assertFalse(any(c["args"][1] == "set" for c in self.hermes_calls()))

    def test_hermes_windows_config_path_comparison_is_case_insensitive(self):
        path = self.seed_hermes(["%DOTAGENTS_REPO%/skills"])
        original = path.read_bytes()
        self.run_installer("-NoStatusline", "-NoAttribution",
                           setup=FAKE_HERMES + "; Set-Variable IsWindows -Force -Value $true",
                           extra_env={"FAKE_HERMES_PATH": str(path).upper(),
                                      "DOTAGENTS_REPO": str(REPO)})
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.backups(path), [])
        self.assertFalse(any(c["args"][1] == "set" for c in self.hermes_calls()))


class PowerShellHermesPersonalitiesTest(PowerShellTestCase):
    """Personalities are added, updated only when owned, and replaced only with -Force."""

    def test_hermes_personalities_added_then_current(self):
        path = self.seed_hermes([])
        original = path.read_bytes()
        result = self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, personalities=True)
        self.assertIn("added: personality reviewer", result.stdout)
        names = sorted(p.stem for p in (REPO / "generated/hermes/personalities").glob("*.yaml"))
        self.assertEqual(sorted(self.personalities(path)), names)
        self.assertEqual(self.personalities(path)["reviewer"], self.generated_personality("reviewer"))
        self.assertEqual([b.read_bytes() for b in self.backups(path)], [original])
        owned = self.state()["hermes_personalities"][str(path)]
        self.assertEqual(sorted(owned), names)
        after = path.read_bytes()
        result = self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, personalities=True)
        self.assertIn("ok: personality reviewer is current", result.stdout)
        self.assertEqual(path.read_bytes(), after)

    def test_hermes_personality_ownership_matches_bash_digest(self):
        path = self.seed_hermes([])
        self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, personalities=True)
        value = self.generated_personality("coder")
        digest = "sha256:" + __import__("hashlib").sha256(
            (value["description"] + "\0" + value["system_prompt"]).encode()).hexdigest()
        self.assertEqual(self.state()["hermes_personalities"][str(path)]["coder"], digest)

    def test_hermes_foreign_personality_needs_force(self):
        path = self.seed_hermes([])
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        mine = {"description": "mine", "system_prompt": "my reviewer"}
        data["agent"] = {"personalities": {"reviewer": mine}}
        path.write_text(json.dumps(data))
        result = self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, personalities=True)
        self.assertIn("skip: personality reviewer exists and was not set by this installer", result.stdout)
        self.assertEqual(self.personalities(path)["reviewer"], mine)
        result = self.run_installer("-NoStatusline", "-NoAttribution", "-Force", setup=FAKE_HERMES,
                                    personalities=True)
        self.assertIn("replaced (-Force", result.stdout)
        self.assertEqual(self.personalities(path)["reviewer"], self.generated_personality("reviewer"))

    def test_hermes_owned_personality_updates_and_removed_role_is_reported(self):
        path = self.seed_hermes([])
        self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, personalities=True)
        older = {"description": "old", "system_prompt": "old prompt"}
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        data["agent"]["personalities"]["reviewer"] = older
        data["agent"]["personalities"]["retired"] = older
        path.write_text(json.dumps(data))
        state = self.state()
        digest = "sha256:" + __import__("hashlib").sha256(b"old\0old prompt").hexdigest()
        state["hermes_personalities"][str(path)].update(reviewer=digest, retired=digest)
        self.state_path().write_text(json.dumps(state))
        result = self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, personalities=True)
        self.assertIn("updated: personality reviewer", result.stdout)
        self.assertIn("note: personality retired was set by this installer", result.stdout)
        self.assertEqual(self.personalities(path)["retired"], older)

    def test_hermes_personality_dry_run_switch_and_failed_write(self):
        path = self.seed_hermes([])
        original = path.read_bytes()
        result = self.run_installer("-DryRun", setup=FAKE_HERMES, personalities=True)
        self.assertIn("would set agent.personalities.reviewer", result.stdout)
        self.assertEqual(self.hermes_calls(), [])
        self.assertEqual(path.read_bytes(), original)
        result = self.run_installer("-NoHermes", setup=FAKE_HERMES, personalities=True)
        self.assertIn("Hermes personalities: skipped (-NoHermes).", result.stdout)
        result = self.run_installer("-NoHermesPersonalities", setup=FAKE_HERMES, personalities=True)
        self.assertIn("Hermes personalities: skipped (-NoHermesPersonalities).", result.stdout)
        self.assertEqual(self.personalities(path), {})
        failing = self.seed_hermes([], self.home / "failing")
        result = self.run_installer("-NoStatusline", "-NoAttribution", setup=FAKE_HERMES, check=False,
                                    personalities=True,
                                    extra_env={"HERMES_HOME": str(failing.parent), "FAKE_HERMES_MODE": "no-write"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("verification failed", result.stderr)
        self.assertEqual(self.personalities(failing), {})


if __name__ == "__main__":
    unittest.main()
