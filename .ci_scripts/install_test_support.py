"""Shared fixtures for the Bash installer tests, isolated from the real home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The agent generator and the modules it imports, which a fake repository needs.
GENERATOR_MODULES = ("generate_agents.py", "agent_front_matter.py", "agent_source.py", "agent_render.py")

REQUIRES_BASH = unittest.skipUnless(shutil.which("bash") and os.name != "nt", "requires Unix Bash")


def make_temp_dir(test: unittest.TestCase, prefix: str | None = None) -> Path:
    """Create a temporary directory that is removed when the test ends."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


@REQUIRES_BASH
class InstallerTestCase(unittest.TestCase):
    """Runs the real installer against a throwaway home seeded with settings files."""

    def setUp(self) -> None:
        self.home = make_temp_dir(self)
        self.env = dict(os.environ, HOME=str(self.home), TZ="EST5",
                        HERMES_HOME=str(self.home / ".hermes"))
        for key in ("CURSOR_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
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

    def install(self, *args: str, extra_env=None, check=True, personalities=False) -> subprocess.CompletedProcess:
        env = dict(self.env, **(extra_env or {}))
        # Settings and skill-registration tests leave personalities to the tests below.
        flags = [] if personalities else ["--no-hermes-personalities"]
        result = subprocess.run(
            ["bash", str(REPO / "scripts/install.sh"), *flags, *args],
            check=False,
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
elif args == ['config', 'get', 'agent.personalities', '--json']:
    if mode == 'personalities-bad':
        print('["not", "a", "mapping"]')
    else:
        print(json.dumps(json.loads(config.read_text()).get('agent', {}).get('personalities')))
elif args[:2] == ['config', 'get'] and args[2].startswith('agent.personalities.') and args[3:] == ['--json']:
    name = args[2].split('.', 2)[2]
    personalities = json.loads(config.read_text()).get('agent', {}).get('personalities') or {}
    print(json.dumps(personalities.get(name)))
elif args[:2] == ['config', 'set'] and args[2].startswith('agent.personalities.') and len(args) == 4:
    if mode != 'personality-no-write':
        value = json.loads(config.read_text())
        name = args[2].split('.', 2)[2]
        value.setdefault('agent', {}).setdefault('personalities', {})[name] = json.loads(args[3])
        config.write_text(json.dumps(value) + '\n')
else:
    sys.exit(7)
""", encoding="utf-8")
        executable.chmod(0o755)
        self.env["PATH"] = str(tools) + os.pathsep + self.env["PATH"]
        self.env["HERMES_HOME"] = str(root)
        return config

    def personalities(self, config):
        return json.loads(config.read_text()).get("agent", {}).get("personalities", {})

    def generated_personality(self, name):
        path = REPO / "generated/hermes/personalities" / (name + ".yaml")
        lines = path.read_text(encoding="utf-8").splitlines()
        pairs = (line.split(": ", 1) for line in lines if not line.startswith("#"))
        return {key: json.loads(value) for key, value in pairs}

    def state(self):
        path = self.home / ".local/state/dotagents/install-state.json"
        return json.loads(path.read_text()) if path.exists() else None


HELPER_SOURCE = """---
schema: 1
name: helper
description: Helps with sample work.
model: standard
color: blue
skills:
  - alpha
---
# Helper

## Role

You help.
"""

SKILL_TARGETS = (".claude/skills", ".cursor/skills", ".gemini/config/skills",
                 ".copilot/skills", ".codex/skills", ".grok/skills")


@REQUIRES_BASH
class LinkTestCase(unittest.TestCase):
    """Runs a copy of the installer in a fake repository, so the real skills/ stays untouched."""

    def setUp(self) -> None:
        root = make_temp_dir(self)
        self.home = root / "home"
        self.home.mkdir()
        # A fake repository keeps the real skills/ untouched.
        self.repo = root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        for script in ("install.sh", "install_settings.py"):
            shutil.copy(REPO / "scripts" / script, self.repo / "scripts" / script)
        (self.repo / ".ci_scripts").mkdir()
        for module in GENERATOR_MODULES:
            shutil.copy(REPO / ".ci_scripts" / module, self.repo / ".ci_scripts" / module)
        (self.repo / "agent_sources").mkdir()
        (self.repo / "agent_sources/README.md").write_text("# Agent Index\n", encoding="utf-8")
        (self.repo / "agent_sources/helper.md").write_text(HELPER_SOURCE, encoding="utf-8")
        (self.repo / "AGENTS.md").write_text("Global\n", encoding="utf-8")
        for name in ("alpha", "beta"):
            (self.repo / "skills" / name).mkdir(parents=True)
            (self.repo / "skills" / name / "SKILL.md").write_text("Skill\n", encoding="utf-8")
        self.skills = self.repo / "skills"
        self.env = dict(os.environ, HOME=str(self.home))
        for key in ("CURSOR_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
            self.env.pop(key, None)

    def install(self, *args: str, check=True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["bash", str(self.repo / "scripts/install.sh"), "--no-statusline",
             "--no-attribution", "--no-hermes", *args],
            check=False,
            env=self.env, cwd=self.repo, text=True, capture_output=True, timeout=30,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result
