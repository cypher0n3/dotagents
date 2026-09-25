"""Build throwaway repositories for generator tests."""

from __future__ import annotations

import io
import shutil
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agentgen.cli import main

REPO_ROOT = Path(__file__).resolve().parents[3]

BODY = textwrap.dedent(
    """\
    # Sample

    ## Role

    You are a sample role.

    ## Working Rules

    - Follow the rules.
    """
)


def role_yaml(name: str = "sample", **overrides: str) -> str:
    """Return a valid role source, with any top-level key replaced by raw YAML text."""
    fields = {
        "schema": "1",
        "name": name,
        "description": "Does sample work. Use this agent when a sample is needed.",
        "body": f"prompts/{name}.md",
        "targets": "[claude, codex, cursor, hermes, cai]",
        "model": "\n  alias: strong",
        "skills": "\n  required: [alpha]\n  suggested: [beta]",
        "restrictions": "\n  readonly: true\n  tools: [Read, Grep, Bash]",
        "presentation": "\n  claude:\n    color: red",
    }
    fields.update(overrides)
    return "".join(f"{key}: {value}\n" for key, value in fields.items() if value is not None)


class RepoTestCase(unittest.TestCase):
    """A test case with a temporary repository holding the real profiles and templates."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for part in ("targets", "templates"):
            shutil.copytree(REPO_ROOT / "agent_sources" / part, self.root / "agent_sources" / part)
        for part in ("roles", "prompts"):
            (self.root / "agent_sources" / part).mkdir(parents=True)
        for skill in ("alpha", "beta", "gamma"):
            (self.root / "skills" / skill).mkdir(parents=True)
            (self.root / "skills" / skill / "SKILL.md").write_text(f"---\nname: {skill}\n---\n# {skill}\n")
        (self.root / "agents").mkdir()
        (self.root / "agents" / "README.md").write_text("# Agent Index\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_role(self, name: str = "sample", body_text: str = BODY, **overrides: str) -> None:
        (self.root / "agent_sources" / "roles" / f"{name}.yaml").write_text(role_yaml(name, **overrides))
        (self.root / "agent_sources" / "prompts" / f"{name}.md").write_text(body_text)

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["generate", "--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text()
