#!/usr/bin/env python3
"""Bash installer tests for status line and attribution settings, and their backups."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from install_test_support import REPO, InstallerTestCase


class InstallSettingsTest(InstallerTestCase):
    """Settings changes are backed up once, with a timestamp, and never lose an earlier backup."""

    def test_one_timestamped_backup_preserves_original_before_both_updates(self) -> None:
        self.install()
        timestamps = set()
        for path, original in zip(self.paths, self.originals):
            with self.subTest(path=path.name):
                backups = self.backups(path)
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), original)
                stamp = backups[0].name[len(path.name) + 1:-4]
                self.assertRegex(stamp, r"^\d{8}T\d{6}\.\d{6}[+-]\d{4}$")
                parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%f%z")
                self.assertEqual(parsed.utcoffset(), timedelta(hours=-5))
                timestamps.add(stamp)
        self.assertEqual(len(timestamps), 1)
        claude = json.loads(self.paths[0].read_text())
        self.assertEqual(claude["keep"], "claude")
        self.assertNotEqual(claude["statusLine"]["command"], "old")
        self.assertEqual(claude["attribution"]["commit"], "")
        self.assertEqual(claude["attribution"]["pr"], "")
        self.assertFalse(claude["attribution"]["sessionUrl"])
        cursor = json.loads(self.paths[1].read_text())
        self.assertEqual(cursor["keep"], "cursor")
        self.assertNotEqual(cursor["statusLine"]["command"], "old")
        self.assertFalse(cursor["attribution"]["attributeCommitsToAgent"])
        self.assertFalse(cursor["attribution"]["attributePRsToAgent"])
        self.assertIn('model = "keep"', self.paths[2].read_text())
        self.assertIn('commit_attribution = ""', self.paths[2].read_text())

    def test_cursor_uses_xdg_config_without_touching_legacy_config(self) -> None:
        active = self.home / "xdg config/cursor/cli-config.json"
        active.parent.mkdir(parents=True)
        original = b'{"keep":"active","display":{"mode":"zen"}}\n'
        active.write_bytes(original)
        self.install(extra_env={"XDG_CONFIG_HOME": str(active.parent.parent)})
        config = json.loads(active.read_text())
        self.assertIn("statusLine", config)
        self.assertFalse(config["attribution"]["attributeCommitsToAgent"])
        self.assertFalse(config["attribution"]["attributePRsToAgent"])
        self.assertEqual(config["keep"], "active")
        self.assertEqual(config["display"], {"mode": "zen"})
        self.assertEqual(config["statusLine"]["command"], str(self.home / ".cursor/statusline-command.sh"))
        self.assertEqual(len(self.backups(active)), 1)
        self.assertEqual(self.backups(active)[0].read_bytes(), original)
        self.assertEqual(self.paths[1].read_bytes(), self.originals[1])
        self.assertEqual(self.backups(self.paths[1]), [])

    def test_cursor_custom_directory_precedes_xdg(self) -> None:
        custom = self.home / "custom config/cli-config.json"
        xdg = self.home / "xdg/cursor/cli-config.json"
        original = b'{"keep":"custom"}\n'
        for path in (custom, xdg):
            path.parent.mkdir(parents=True)
            path.write_bytes(original)
        overrides = {"CURSOR_CONFIG_DIR": str(custom.parent), "XDG_CONFIG_HOME": str(xdg.parent.parent)}
        self.install(extra_env=overrides)
        config = json.loads(custom.read_text())
        self.assertIn("statusLine", config)
        self.assertFalse(config["attribution"]["attributeCommitsToAgent"])
        self.assertEqual(xdg.read_bytes(), original)
        self.assertEqual(self.paths[1].read_bytes(), self.originals[1])
        self.assertEqual(len(self.backups(custom)), 1)
        self.assertEqual(self.backups(custom)[0].read_bytes(), original)
        self.assertEqual(self.backups(xdg), [])

    def test_cursor_missing_config_directory_is_created_only_on_real_install(self) -> None:
        active = self.home / "new config/cursor/cli-config.json"
        overrides = {"XDG_CONFIG_HOME": str(active.parent.parent)}
        result = self.install("--dry-run", extra_env=overrides)
        self.assertIn(str(active), result.stdout)
        self.assertFalse(active.parent.exists())
        self.install(extra_env=overrides)
        config = json.loads(active.read_text())
        self.assertIn("statusLine", config)
        self.assertIn("attribution", config)
        self.assertEqual(self.backups(active), [])
        self.assertEqual(self.paths[1].read_bytes(), self.originals[1])

    def test_cursor_blank_overrides_fall_back_to_default(self) -> None:
        self.install(extra_env={"CURSOR_CONFIG_DIR": " ", "XDG_CONFIG_HOME": "\t"})
        self.assertIn("statusLine", json.loads(self.paths[1].read_text()))
        self.assertEqual(self.backups(self.paths[1])[0].read_bytes(), self.originals[1])

    def test_cursor_attribution_only_respects_xdg(self) -> None:
        active = self.home / "xdg/cursor/cli-config.json"
        active.parent.mkdir(parents=True)
        original = b'{"statusLine":{"command":"keep"}}\n'
        active.write_bytes(original)
        env = {"XDG_CONFIG_HOME": str(active.parent.parent), "CURSOR_CONFIG_DIR": " "}
        self.install("--no-statusline", extra_env=env)
        config = json.loads(active.read_text())
        self.assertEqual(config["statusLine"], {"command": "keep"})
        self.assertFalse(config["attribution"]["attributePRsToAgent"])
        self.assertEqual(self.paths[1].read_bytes(), self.originals[1])
        self.assertEqual(self.backups(active)[0].read_bytes(), original)

    def test_dry_run_leaves_home_unchanged(self) -> None:
        before = {str(p.relative_to(self.home)): p.read_bytes() for p in self.paths}
        self.install("--dry-run")
        after = {
            str(p.relative_to(self.home)): p.read_bytes()
            for p in self.home.rglob("*") if p.is_file()
        }
        self.assertEqual(after, before)
        self.assertFalse(any(p.is_symlink() for p in self.home.rglob("*")))

    def test_noop_reinstall_creates_no_more_backups(self) -> None:
        self.install()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                  for path in self.paths for p in [path, *self.backups(path)]}
        self.install()
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                 for path in self.paths for p in [path, *self.backups(path)]}
        self.assertEqual(after, before)

    def test_later_changing_install_preserves_earlier_backups(self) -> None:
        self.install()
        previous = {p: p.read_bytes() for path in self.paths for p in self.backups(path)}
        for path, content in zip(self.paths, self.originals):
            path.write_bytes(content.replace(b"keep", b"later"))
        originals = {path: path.read_bytes() for path in self.paths}
        self.install()
        for path in self.paths:
            with self.subTest(path=path.name):
                backups = self.backups(path)
                self.assertEqual(len(backups), 2)
                new = [p for p in backups if p not in previous]
                self.assertEqual(len(new), 1)
                self.assertEqual(new[0].read_bytes(), originals[path])
        for path, content in previous.items():
            self.assertEqual(path.read_bytes(), content)

    def test_missing_files_are_not_backed_up_after_first_mutation(self) -> None:
        for path in self.paths:
            path.unlink()
        self.install()
        for path in self.paths:
            self.assertTrue(path.exists())
            self.assertEqual(self.backups(path), [])

    def test_existing_empty_json_objects_are_backed_up(self) -> None:
        for path in self.paths[:2]:
            path.write_bytes(b"{}\n")
        self.install()
        for path in self.paths[:2]:
            backups = self.backups(path)
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"{}\n")

    def test_legacy_backup_and_private_permissions_are_preserved(self) -> None:
        path = self.paths[0]
        path.chmod(0o600)
        legacy = Path(str(path) + ".bak")
        legacy.write_bytes(b"older backup")
        self.install()
        self.assertEqual(legacy.read_bytes(), b"older backup")
        new = [p for p in self.backups(path) if p != legacy]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(new[0].read_bytes(), self.originals[0])

    def test_statusline_only_backs_up_json_not_codex(self) -> None:
        self.install("--no-attribution")
        for path, original in zip(self.paths[:2], self.originals[:2]):
            self.assertEqual(len(self.backups(path)), 1)
            self.assertEqual(self.backups(path)[0].read_bytes(), original)
            self.assertNotIn("attribution", json.loads(path.read_text()))
        self.assertEqual(self.paths[2].read_bytes(), self.originals[2])
        self.assertEqual(self.backups(self.paths[2]), [])

    def test_attribution_only_preserves_statusline(self) -> None:
        self.install("--no-statusline")
        for path, original in zip(self.paths, self.originals):
            self.assertEqual(len(self.backups(path)), 1)
            self.assertEqual(self.backups(path)[0].read_bytes(), original)
        for path in self.paths[:2]:
            self.assertEqual(json.loads(path.read_text())["statusLine"]["command"], "old")

    def test_timestamp_collision_aborts_without_overwriting_backup_or_settings(self) -> None:
        clock = self.home / "test-clock"
        clock.mkdir()
        (clock / "datetime.py").write_text(
            "from _datetime import datetime as RealDateTime, date, time, timedelta, timezone, tzinfo\n"
            "class datetime(RealDateTime):\n"
            "    @classmethod\n"
            "    def now(cls):\n"
            "        return cls(2000, 1, 2, 12, 0, tzinfo=timezone.utc)\n",
            encoding="utf-8",
        )
        stamp = "20000102T070000.000000-0500"
        for index in (0, 2):
            with self.subTest(path=self.paths[index].name):
                for path, original in zip(self.paths, self.originals):
                    for backup in self.backups(path):
                        backup.unlink()
                    path.write_bytes(original)
                backup = Path(str(self.paths[index]) + "." + stamp + ".bak")
                backup.write_bytes(b"earlier backup")
                result = subprocess.run(
                    ["bash", str(REPO / "scripts/install.sh")],
                    env=dict(self.env, PYTHONPATH=str(clock)),
                    cwd=REPO, text=True, capture_output=True, timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FileExistsError", result.stderr)
                self.assertEqual(backup.read_bytes(), b"earlier backup")
                self.assertEqual(self.paths[index].read_bytes(), self.originals[index])

    def test_skipping_both_steps_does_not_require_python(self) -> None:
        tools = self.home / "test-bin"
        tools.mkdir()
        python = tools / "python3"
        # Agent generation still runs python3; only the settings script must not be needed.
        python.write_text(
            '#!/bin/sh\ncase "$1" in */install_settings.py) exit 99;; esac\nexec "%s" "$@"\n' % sys.executable,
            encoding="utf-8",
        )
        python.chmod(0o755)
        result = subprocess.run(
            ["bash", str(REPO / "scripts/install.sh"), "--no-statusline", "--no-attribution"],
            env=dict(self.env, PATH=str(tools) + os.pathsep + os.environ["PATH"]),
            cwd=REPO, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_skipping_both_settings_steps_creates_no_backups(self) -> None:
        self.install("--no-statusline", "--no-attribution")
        for path, original in zip(self.paths, self.originals):
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.backups(path), [])


if __name__ == "__main__":
    unittest.main()
