#!/usr/bin/env python3
"""PowerShell installer tests for status line and attribution settings, and their backups."""

import datetime
import json
import os
import re
import unittest

from powershell_test_support import INSTALLER, STAMP, PowerShellTestCase


class PowerShellSettingsTest(PowerShellTestCase):
    """Settings changes are backed up once, with a shared timestamp, and never lose an earlier backup."""

    def test_requires_powershell_7(self):
        self.assertRegex(INSTALLER.read_text(encoding="utf-8"),
                         r"(?im)^#requires -Version 7\.0$")

    def test_existing_settings_have_one_original_backup_with_shared_timestamp(self):
        originals = self.seed_settings()
        before = datetime.datetime.now(datetime.timezone.utc)
        self.run_installer()
        after = datetime.datetime.now(datetime.timezone.utc)
        stamps = set()
        for path, original in zip(self.paths, originals):
            with self.subTest(path=path.name):
                backups = self.backups(path)
                self.assertEqual(len(backups), 1)
                match = re.fullmatch(re.escape(path.name) + r"\.(" + STAMP + r")\.bak", backups[0].name)
                if match is None:
                    self.fail(backups[0].name)
                stamps.add(match.group(1))
                self.assertEqual(backups[0].read_bytes(), original)
                self.assertNotEqual(path.read_bytes(), original)
        self.assertEqual(len(stamps), 1)
        timestamp = datetime.datetime.strptime(stamps.pop(), "%Y%m%dT%H%M%S.%f%z")
        self.assertLessEqual(before, timestamp)
        self.assertLessEqual(timestamp, after)
        self.assertEqual(timestamp.utcoffset(), datetime.datetime.now().astimezone().utcoffset())
        claude = json.loads(self.paths[0].read_text(encoding="utf-8-sig"))
        self.assertEqual(claude["keep"], "claude")
        self.assertIn("statusLine", claude)
        self.assertEqual(claude["attribution"]["commit"], "")

    def test_cursor_uses_xdg_config_without_touching_legacy_config(self):
        originals = self.seed_settings()
        active = self.home / "xdg config/cursor/cli-config.json"
        active.parent.mkdir(parents=True)
        original = b'{"keep":"active","display":{"mode":"zen"}}\n'
        active.write_bytes(original)
        self.run_installer(extra_env={"XDG_CONFIG_HOME": str(active.parent.parent)})
        config = json.loads(active.read_text(encoding="utf-8-sig"))
        self.assertIn("statusLine", config)
        self.assertFalse(config["attribution"]["attributeCommitsToAgent"])
        self.assertFalse(config["attribution"]["attributePRsToAgent"])
        self.assertEqual(config["display"], {"mode": "zen"})
        self.assertEqual(config["keep"], "active")
        self.assertEqual(len(self.backups(active)), 1)
        self.assertEqual(self.backups(active)[0].read_bytes(), original)
        self.assertEqual(self.paths[1].read_bytes(), originals[1])
        self.assertEqual(self.backups(self.paths[1]), [])

    def test_cursor_custom_directory_precedes_xdg(self):
        originals = self.seed_settings()
        custom = self.home / "custom config/cli-config.json"
        xdg = self.home / "xdg/cursor/cli-config.json"
        original = b'{"keep":"custom"}\n'
        for path in (custom, xdg):
            path.parent.mkdir(parents=True)
            path.write_bytes(original)
        self.run_installer(extra_env={"CURSOR_CONFIG_DIR": str(custom.parent),
                                      "XDG_CONFIG_HOME": str(xdg.parent.parent)})
        config = json.loads(custom.read_text(encoding="utf-8-sig"))
        self.assertIn("statusLine", config)
        self.assertFalse(config["attribution"]["attributeCommitsToAgent"])
        self.assertEqual(xdg.read_bytes(), original)
        self.assertEqual(self.paths[1].read_bytes(), originals[1])
        self.assertEqual(len(self.backups(custom)), 1)
        self.assertEqual(self.backups(custom)[0].read_bytes(), original)
        self.assertEqual(self.backups(xdg), [])

    def test_cursor_missing_config_directory_is_created_only_on_real_install(self):
        originals = self.seed_settings()
        active = self.home / "new config/cursor/cli-config.json"
        overrides = {"XDG_CONFIG_HOME": str(active.parent.parent)}
        result = self.run_installer("-DryRun", extra_env=overrides)
        self.assertIn(str(active), result.stdout)
        self.assertFalse(active.parent.exists())
        self.run_installer(extra_env=overrides)
        config = json.loads(active.read_text(encoding="utf-8-sig"))
        self.assertIn("statusLine", config)
        self.assertIn("attribution", config)
        self.assertEqual(self.backups(active), [])
        self.assertEqual(self.paths[1].read_bytes(), originals[1])

    def test_cursor_blank_overrides_fall_back_to_default(self):
        originals = self.seed_settings()
        self.run_installer(extra_env={"CURSOR_CONFIG_DIR": " ", "XDG_CONFIG_HOME": "\t"})
        self.assertIn("statusLine", json.loads(self.paths[1].read_text(encoding="utf-8-sig")))
        self.assertEqual(self.backups(self.paths[1])[0].read_bytes(), originals[1])

    def test_cursor_attribution_only_respects_xdg(self):
        originals = self.seed_settings()
        active = self.home / "xdg/cursor/cli-config.json"
        active.parent.mkdir(parents=True)
        original = b'{"statusLine":{"command":"keep"}}\n'
        active.write_bytes(original)
        env = {"XDG_CONFIG_HOME": str(active.parent.parent), "CURSOR_CONFIG_DIR": " "}
        self.run_installer("-NoStatusline", extra_env=env)
        config = json.loads(active.read_text(encoding="utf-8-sig"))
        self.assertEqual(config["statusLine"], {"command": "keep"})
        self.assertFalse(config["attribution"]["attributePRsToAgent"])
        self.assertEqual(self.paths[1].read_bytes(), originals[1])
        self.assertEqual(self.backups(active)[0].read_bytes(), original)

    def test_missing_settings_do_not_back_up_partial_first_mutation(self):
        self.run_installer()
        for path in self.paths:
            self.assertTrue(path.is_file())
            self.assertEqual(self.backups(path), [])
        for path in self.paths[:2]:
            settings = json.loads(path.read_text(encoding="utf-8-sig"))
            self.assertIn("statusLine", settings)
            self.assertIn("attribution", settings)

    @unittest.skipIf(os.name == "nt", "TZ environment override is Unix-specific")
    def test_timestamp_uses_local_offset_with_invariant_calendar(self):
        self.seed_settings()
        before = datetime.datetime.now(datetime.timezone.utc)
        self.run_installer(
            extra_env={"TZ": "Asia/Kathmandu"},
            setup="[System.Threading.Thread]::CurrentThread.CurrentCulture = 'ar-SA'",
        )
        after = datetime.datetime.now(datetime.timezone.utc)
        for path in self.paths:
            backup = self.backups(path)[0]
            stamp = backup.name[len(path.name) + 1:-4]
            self.assertRegex(stamp, r"^" + STAMP + r"$")
            timestamp = datetime.datetime.strptime(stamp, "%Y%m%dT%H%M%S.%f%z")
            self.assertEqual(timestamp.utcoffset(), datetime.timedelta(hours=5, minutes=45))
            self.assertLessEqual(before, timestamp)
            self.assertLessEqual(timestamp, after)

    def test_unchanged_second_install_preserves_settings_and_backups(self):
        self.seed_settings()
        self.run_installer()
        snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                    for path in self.paths for p in [path, *self.backups(path)]}
        self.run_installer()
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                 for path in self.paths for p in [path, *self.backups(path)]}
        self.assertEqual(snapshot, after)

    def test_dry_run_preserves_settings_and_creates_no_backups(self):
        originals = self.seed_settings()
        self.run_installer("-DryRun")
        for path, original in zip(self.paths, originals):
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.backups(path), [])

    def test_empty_existing_json_files_get_original_byte_backups(self):
        originals = [b"", b" \r\n\t"]
        for path, original in zip(self.paths[:2], originals):
            path.write_bytes(original)
        self.run_installer()
        for path, original in zip(self.paths[:2], originals):
            backups = self.backups(path)
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertIn("attribution", json.loads(path.read_text(encoding="utf-8-sig")))

    def test_dry_run_does_not_create_missing_settings(self):
        self.run_installer("-DryRun")
        for path in self.paths:
            self.assertFalse(path.exists())
            self.assertEqual(self.backups(path), [])

    def test_distinct_changing_runs_retain_original_snapshots(self):
        originals = self.seed_settings()
        self.run_installer()
        first = {path: self.backups(path)[0] for path in self.paths}
        second_originals = [b'{"keep":"second claude"}\n',
                            b'{"keep":"second cursor"}\n',
                            b'model = "second codex"\n']
        for path, content in zip(self.paths, second_originals):
            path.write_bytes(content)
        self.run_installer()
        for path, original, second_original in zip(self.paths, originals, second_originals):
            self.assertEqual(len(self.backups(path)), 2)
            self.assertEqual(first[path].read_bytes(), original)
            second = next(p for p in self.backups(path) if p != first[path])
            self.assertEqual(second.read_bytes(), second_original)

    def test_legacy_backup_is_not_overwritten(self):
        self.seed_settings()
        legacy = [path.with_name(path.name + ".bak") for path in self.paths]
        for path in legacy:
            path.write_bytes(b"legacy snapshot")
        self.run_installer()
        for path in legacy:
            self.assertEqual(path.read_bytes(), b"legacy snapshot")
        for path in self.paths:
            self.assertEqual(len(self.backups(path)), 2)

    def test_disabled_features_create_no_backups(self):
        originals = self.seed_settings()
        self.run_installer("-NoStatusline", "-NoAttribution")
        for path, original in zip(self.paths, originals):
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.backups(path), [])

    def test_attribution_only_backs_up_original_settings(self):
        originals = self.seed_settings()
        self.run_installer("-NoStatusline")
        for path, original in zip(self.paths, originals):
            backups = self.backups(path)
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
        for path in self.paths[:2]:
            self.assertNotIn("statusLine", json.loads(path.read_text(encoding="utf-8-sig")))

    def test_statusline_only_does_not_back_up_codex(self):
        originals = self.seed_settings()
        self.run_installer("-NoAttribution")
        for path, original in zip(self.paths[:2], originals[:2]):
            backups = self.backups(path)
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(self.paths[2].read_bytes(), originals[2])
        self.assertEqual(self.backups(self.paths[2]), [])

    def test_collision_refuses_to_overwrite_backup_or_source(self):
        # Freeze only the clock, not the backup implementation. The full script
        # must fail before editing the colliding source, for JSON and TOML alike.
        for index, relative in ((0, ".claude/settings.json"), (2, ".codex/config.toml")):
            with self.subTest(path=relative):
                # Keep each collision case independent, even if a prior assertion fails.
                for target in self.paths:
                    for backup in self.backups(target):
                        backup.unlink()
                originals = self.seed_settings()
                setup = '''
                    function Get-Date { [datetime]::new(2026, 1, 2, 3, 4, 5) }
                    $stamp = (Get-Date).ToString("yyyyMMdd'T'HHmmss.ffffffzzz",
                        [System.Globalization.CultureInfo]::InvariantCulture).Replace(':', '')
                    $collision = (Join-Path $HOME 'RELATIVE') + '.' + $stamp + '.bak'
                    [System.IO.File]::WriteAllText($collision, 'older snapshot')
                '''.replace("RELATIVE", relative)
                result = self.run_installer(setup=setup, check=False)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("Copy", result.stderr)
                path = self.paths[index]
                self.assertEqual(path.read_bytes(), originals[index])
                collided = [p for p in self.backups(path) if p.read_bytes() == b"older snapshot"]
                self.assertEqual(len(collided), 1)


if __name__ == "__main__":
    unittest.main()
