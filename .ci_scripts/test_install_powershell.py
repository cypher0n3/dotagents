"""Behavioral tests for the PowerShell installer, using isolated temporary homes."""

import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import warnings


REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts" / "install.ps1"
PWSH = shutil.which("pwsh")
STAMP = r"\d{8}T\d{6}\.\d{6}[+-]\d{4}"

# A PowerShell function shadows any installed Hermes executable. JSON fixtures
# are valid YAML; only this offline CLI double writes them, never the installer.
FAKE_HERMES = r'''
function hermes {
    $call = @{ args = @($args); home = $env:HERMES_HOME } | ConvertTo-Json -Compress
    [IO.File]::AppendAllText((Join-Path $HOME 'hermes-calls.jsonl'), $call + "`n")
    $global:LASTEXITCODE = 0
    $config = Join-Path $env:HERMES_HOME 'config.yaml'
    if ($args.Count -eq 2 -and $args[0] -eq 'config' -and $args[1] -eq 'path') {
        if ($env:FAKE_HERMES_PATH) { return $env:FAKE_HERMES_PATH }
        return $config
    }
    if ($args.Count -eq 4 -and $args[0] -eq 'config' -and
        $args[1] -eq 'get' -and $args[2] -eq 'skills.external_dirs' -and $args[3] -eq '--json') {
        if ($env:FAKE_HERMES_MODE -eq 'read-failure') { $global:LASTEXITCODE = 17; return '[]' }
        if ($env:FAKE_HERMES_JSON) { return $env:FAKE_HERMES_JSON }
        $data = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
        return ConvertTo-Json -InputObject $data.skills.external_dirs -Depth 100 -Compress
    }
    if ($args.Count -eq 4 -and $args[0] -eq 'config' -and
        $args[1] -eq 'set' -and $args[2] -eq 'skills.external_dirs') {
        if ($env:FAKE_HERMES_MODE -eq 'set-failure') { $global:LASTEXITCODE = 19; return }
        if ($env:FAKE_HERMES_MODE -eq 'no-write') { return }
        $data = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
        $data.skills.external_dirs = ConvertFrom-Json -InputObject $args[3] -NoEnumerate
        [IO.File]::WriteAllText($config, (ConvertTo-Json -InputObject $data -Depth 100))
        return
    }
    if ($args.Count -eq 4 -and $args[0] -eq 'config' -and $args[1] -eq 'get' -and
        $args[2] -like 'agent.personalities*' -and $args[3] -eq '--json') {
        $data = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json -AsHashtable
        $all = if ($data.Contains('agent')) { $data.agent.personalities } else { $null }
        if ($args[2] -eq 'agent.personalities') { return ConvertTo-Json -InputObject $all -Depth 100 -Compress }
        $name = $args[2].Substring('agent.personalities.'.Length)
        $one = if ($null -ne $all -and $all.Contains($name)) { $all[$name] } else { $null }
        return ConvertTo-Json -InputObject $one -Depth 100 -Compress
    }
    if ($args.Count -eq 4 -and $args[0] -eq 'config' -and $args[1] -eq 'set' -and
        $args[2] -like 'agent.personalities.*') {
        if ($env:FAKE_HERMES_MODE -eq 'no-write') { return }
        $data = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json -AsHashtable
        if (-not $data.Contains('agent')) { $data.agent = @{} }
        if (-not $data.agent.Contains('personalities')) { $data.agent.personalities = @{} }
        $data.agent.personalities[$args[2].Substring('agent.personalities.'.Length)] =
            ConvertFrom-Json -InputObject $args[3] -AsHashtable
        [IO.File]::WriteAllText($config, (ConvertTo-Json -InputObject $data -Depth 100))
        return
    }
    throw "Unexpected Hermes invocation: $args"
}
'''


@unittest.skipUnless(PWSH, "PowerShell 7 (pwsh) is not installed")
class PowerShellInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dotagents-pwsh-")
        self.addCleanup(self.temp.cleanup)
        # Resolve so expected paths match what the installer reports; Windows
        # runners hand out 8.3 short temp paths such as RUNNER~1.
        self.home = Path(self.temp.name).resolve() / "home with spaces"
        self.home.mkdir()
        # Junction creation is Windows-only. Existing real directories are
        # deliberately skipped, so the full installer also runs safely on Unix.
        for tool in (".claude", ".cursor", ".gemini/config", ".copilot", ".codex", ".grok"):
            for skill in (REPO / "skills").iterdir():
                if (skill / "SKILL.md").is_file():
                    (self.home / tool / "skills" / skill.name).mkdir(parents=True)
        self.paths = [self.home / ".claude/settings.json",
                      self.home / ".cursor/cli-config.json",
                      self.home / ".codex/config.toml"]

    def run_installer(self, *flags, setup="", check=True, extra_env=None, personalities=False, copy=True):
        assert PWSH is not None
        # Settings and skill-registration tests leave personalities to their own tests.
        if not personalities:
            flags = ("-NoHermesPersonalities", *flags)
        env = os.environ.copy()
        for key in ("CURSOR_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
            env.pop(key, None)
        # The install record lives under LOCALAPPDATA on Windows; keep it in the temporary home.
        env.update(LOCALAPPDATA=str(self.home / "AppData/Local"))
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   HERMES_HOME=str(self.home / ".hermes"),
                   DOTAGENTS_TEST_HOME=str(self.home),
                   DOTAGENTS_TEST_INSTALLER=str(INSTALLER),
                   POWERSHELL_TELEMETRY_OPTOUT="1")
        if extra_env:
            env.update(extra_env)
        # PowerShell's automatic HOME does not necessarily follow env:HOME.
        command = (
            "$ErrorActionPreference = 'Stop'; "
            "Set-Variable -Name HOME -Value $env:DOTAGENTS_TEST_HOME -Force; "
            + setup + "; $originalHermesHome = $env:HERMES_HOME; "
            "try { & $env:DOTAGENTS_TEST_INSTALLER " + ("-Copy " if copy else "") + " ".join(flags)
            + " } finally { if ($env:HERMES_HOME -cne $originalHermesHome) { throw 'home not restored' } }"
        )
        result = subprocess.run(
            [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=self.home, env=env, text=True, capture_output=True, timeout=60,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def seed_settings(self):
        originals = [b'\xef\xbb\xbf{\r\n "keep": "claude", "attribution": {"commit":"old"}\r\n}\r\n',
                     b'{ "keep": "cursor", "attribution": {"attributeCommitsToAgent":true} }\n',
                     b'# retain this comment\r\nmodel = "example"\r\ncommit_attribution = "old"\r\n']
        for path, content in zip(self.paths, originals):
            path.write_bytes(content)
        return originals

    def backups(self, path):
        return sorted(path.parent.glob(path.name + "*.bak"))

    def seed_hermes(self, directories, home=None):
        path = (home or self.home / ".hermes") / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xef\xbb\xbf' + json.dumps({
            "skills": {"external_dirs": directories, "keep": "skills option"},
            "keep": {"model": "untouched"},
        }, indent=2).replace("\n", "\r\n").encode() + b"\r\n")
        return path

    def hermes_calls(self):
        path = self.home / "hermes-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

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
            result = self.run_installer(*flags, setup=FAKE_HERMES,
                                       extra_env={"HERMES_HOME": str(missing)})
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

    def personalities(self, path):
        return json.loads(path.read_text(encoding="utf-8-sig")).get("agent", {}).get("personalities", {})

    def generated_personality(self, name):
        text = (REPO / "generated/hermes/personalities" / (name + ".yaml")).read_text(encoding="utf-8")
        return {key: json.loads(value) for key, value in (line.split(": ", 1) for line in text.splitlines()
                                                         if not line.startswith("#"))}

    def state_path(self):
        base = self.home / ("AppData/Local" if os.name == "nt" else ".local/state")
        return base / "dotagents/install-state.json"

    def state(self):
        path = self.state_path()
        return json.loads(path.read_text()) if path.exists() else None

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
        self.run_installer("-NoStatusline", extra_env={"XDG_CONFIG_HOME": str(active.parent.parent),
                                                     "CURSOR_CONFIG_DIR": " "})
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
        self.assertEqual(snapshot, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                   for path in self.paths
                                   for p in [path, *self.backups(path)]})

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
