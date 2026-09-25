#!/usr/bin/env python3
"""Behavioral tests for the Bash installer, isolated from the real home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("bash") and os.name != "nt", "requires Unix Bash")
class InstallBackupTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.env = dict(os.environ, HOME=str(self.home), TZ="EST5",
                        HERMES_HOME=str(self.home / ".hermes"))
        for key in ("CURSOR_CONFIG_DIR", "XDG_CONFIG_HOME"):
            self.env.pop(key, None)
        self.paths = [
            self.home / ".claude/settings.json",
            self.home / ".cursor/cli-config.json",
            self.home / ".codex/config.toml",
        ]
        self.originals = [
            b'{"keep": "claude", "statusLine": {"command": "old"}}\n',
            b'{"keep": "cursor", "statusLine": {"command": "old"}}\n',
            b'commit_attribution = "old"\nmodel = "keep"\n',
        ]
        for path, content in zip(self.paths, self.originals):
            path.parent.mkdir()
            path.write_bytes(content)

    def install(self, *args: str, extra_env=None, check=True) -> subprocess.CompletedProcess:
        env = dict(self.env, **(extra_env or {}))
        result = subprocess.run(
            ["bash", str(REPO / "scripts/install.sh"), *args],
            env=env,
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def backups(self, path: Path) -> list[Path]:
        return sorted(path.parent.glob(path.name + "*.bak"))

    def seed_hermes(self, external_dirs=None, config_home=None):
        root = config_home or self.home / ".hermes"
        root.mkdir(parents=True)
        config = root / "config.yaml"
        config.write_text(json.dumps({"model": {"default": "keep"}, "skills": {
            "external_dirs": external_dirs if external_dirs is not None else [],
            "config": {"keep": True}}}) + "\n", encoding="utf-8")
        (root / "SOUL.md").write_text("User identity\n", encoding="utf-8")
        (root / "skills/local-skill").mkdir(parents=True)
        (root / "skills/local-skill/SKILL.md").write_text("Local skill\n", encoding="utf-8")
        tools = self.home / "hermes-bin"
        tools.mkdir(exist_ok=True)
        executable = tools / "hermes"
        # Offline CLI double. Its JSON config is valid YAML; production writes
        # must go through config set, never through the fixture's storage format.
        executable.write_text("#!" + sys.executable + "\n" + r"""
import json, os, sys
from pathlib import Path
root = Path(os.environ['HERMES_HOME'])
config = root / 'config.yaml'
with (Path.home() / 'hermes-calls').open('a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\n')
args = sys.argv[1:]
mode = os.environ.get('DOTAGENTS_HERMES_TEST_MODE', '')
if args == ['config', 'path']:
    print(config if mode != 'wrong-path' else root / 'other/config.yaml')
elif args == ['config', 'get', 'skills.external_dirs', '--json']:
    if mode == 'read-fail':
        sys.exit(5)
    if mode == 'bad-json':
        print('not JSON')
    else:
        directories = json.loads(config.read_text())['skills']['external_dirs']
        if mode == 'expand-env':
            directories = [os.path.expandvars(p) for p in directories]
        print(json.dumps(directories))
elif args[:3] == ['config', 'set', 'skills.external_dirs']:
    if mode == 'write-fail':
        sys.exit(6)
    if mode != 'no-write':
        value = json.loads(config.read_text())
        value['skills']['external_dirs'] = json.loads(args[3])
        config.write_text(json.dumps(value) + '\n')
else:
    sys.exit(7)
""", encoding="utf-8")
        executable.chmod(0o755)
        self.env["PATH"] = str(tools) + os.pathsep + self.env["PATH"]
        self.env["HERMES_HOME"] = str(root)
        return config

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
        self.assertEqual(before, {str(p.relative_to(config.parent)): p.read_bytes()
                                 for p in config.parent.rglob("*") if p.is_file()})
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
        self.install("--no-statusline", extra_env={"XDG_CONFIG_HOME": str(active.parent.parent),
                                                  "CURSOR_CONFIG_DIR": " "})
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
        python.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
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


SKILL_TARGETS = (".claude/skills", ".cursor/skills", ".gemini/config/skills",
                 ".copilot/skills", ".codex/skills", ".grok/skills")


@unittest.skipUnless(shutil.which("bash") and os.name != "nt", "requires Unix Bash")
class InstallSkillLinksTest(unittest.TestCase):
    """Skills are linked per skill, so a tool's own skills never land in the repository."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.home = root / "home"
        self.home.mkdir()
        # A fake repository keeps the real skills/ untouched.
        self.repo = root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(REPO / "scripts/install.sh", self.repo / "scripts/install.sh")
        (self.repo / "agents").mkdir()
        (self.repo / "agents/helper.md").write_text("Agent\n", encoding="utf-8")
        (self.repo / "AGENTS.md").write_text("Global\n", encoding="utf-8")
        for name in ("alpha", "beta"):
            (self.repo / "skills" / name).mkdir(parents=True)
            (self.repo / "skills" / name / "SKILL.md").write_text("Skill\n", encoding="utf-8")
        self.skills = self.repo / "skills"
        self.env = dict(os.environ, HOME=str(self.home))

    def install(self, *args: str, check=True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["bash", str(self.repo / "scripts/install.sh"), "--no-statusline",
             "--no-attribution", "--no-hermes", *args],
            env=self.env, cwd=self.repo, text=True, capture_output=True, timeout=30,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

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
        link = self.home / ".claude/agents"
        link.parent.mkdir()
        link.symlink_to(self.repo / "agents", target_is_directory=True)
        result = self.install("--dry-run")
        self.assertIn("would link each agent into", result.stdout)
        self.assertTrue(link.is_symlink())
        self.install()
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertEqual(sorted(p.name for p in link.iterdir()), ["helper.md"])
        self.assertEqual((link / "helper.md").resolve(), (self.repo / "agents/helper.md").resolve())
        # An agent the tool or user adds stays out of the repository.
        (link / "local.md").write_text("Local\n", encoding="utf-8")
        self.assertFalse((self.repo / "agents/local.md").exists())

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

    def test_reinstall_reports_already_linked(self) -> None:
        self.install()
        result = self.install()
        self.assertIn("already linked", result.stdout)
        self.assertNotIn("linked: ", result.stdout.replace("already linked", ""))


if __name__ == "__main__":
    unittest.main()
