"""Shared fixtures for the PowerShell installer tests, using isolated temporary homes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts" / "install.ps1"
PWSH = shutil.which("pwsh")
STAMP = r"\d{8}T\d{6}\.\d{6}[+-]\d{4}"


def make_temp_dir(test: unittest.TestCase, prefix: str | None = None) -> Path:
    """Create a temporary directory that is removed when the test ends."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


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
class PowerShellTestCase(unittest.TestCase):
    """Runs install.ps1 in pwsh against a throwaway home."""

    def setUp(self):
        temp = make_temp_dir(self, prefix="dotagents-pwsh-")
        # Resolve so expected paths match what the installer reports; Windows
        # runners hand out 8.3 short temp paths such as RUNNER~1.
        self.home = temp.resolve() / "home with spaces"
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
            [str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=self.home, env=env, text=True, capture_output=True, timeout=60, check=False,
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

    def personalities(self, path):
        return json.loads(path.read_text(encoding="utf-8-sig")).get("agent", {}).get("personalities", {})

    def generated_personality(self, name):
        text = (REPO / "generated/hermes/personalities" / (name + ".yaml")).read_text(encoding="utf-8")
        pairs = (line.split(": ", 1) for line in text.splitlines() if not line.startswith("#"))
        return {key: json.loads(value) for key, value in pairs}

    def state_path(self):
        base = self.home / ("AppData/Local" if os.name == "nt" else ".local/state")
        return base / "dotagents/install-state.json"

    def state(self):
        path = self.state_path()
        return json.loads(path.read_text()) if path.exists() else None
