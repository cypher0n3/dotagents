"""Shared fixtures for the agent generator tests: a sample source and a throwaway repository."""

from __future__ import annotations

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from agent_front_matter import SourceError
from agent_source import Agent, load_agent
from generate_agents import main

REPO = Path(__file__).resolve().parents[1]


def make_temp_dir(test: unittest.TestCase, prefix: str | None = None) -> Path:
    """Create a temporary directory that is removed when the test ends."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


BODY = textwrap.dedent(
    """\
    # Sample

    ## Role

    You are a sample agent.

    ## Working Rules

    - Follow the rules.
    """
)

# A valid source that exercises most keys. Tests make it invalid, or change
# what it renders, by replacing one piece of it.
SOURCE = textwrap.dedent(
    """\
    ---
    schema: 1
    name: sample
    description: Does sample work. Use this agent when a sample is needed.
    model: strong
    color: red
    readonly: true
    tools:
      - Read
      - Grep
      - Bash
    skills:
      - alpha
    suggested_skills:
      - beta
    ---
    """
) + BODY

DESCRIPTION_LINE = "description: Does sample work. Use this agent when a sample is needed."

GENERATED_HEADER = (
    "# Generated from agent_sources/sample.md by .ci_scripts/generate_agents.py; "
    "do not edit, changes are lost at the next generation."
)


class TreeTestCase(unittest.TestCase):
    """A throwaway repository with agent_sources/ and two skills, alpha and beta."""

    def setUp(self) -> None:
        self.root = make_temp_dir(self)
        (self.root / "agent_sources").mkdir()
        (self.root / "agent_sources/README.md").write_text("# Agent Index\n")
        for skill in ("alpha", "beta"):
            (self.root / "skills" / skill).mkdir(parents=True)
            (self.root / "skills" / skill / "SKILL.md").write_text("---\nname: x\n---\n# X\n")

    def write(self, text: str = SOURCE, name: str = "sample") -> Path:
        """Write a source file for the named agent."""
        path = self.root / "agent_sources" / f"{name}.md"
        path.write_text(text)
        return path

    def replace(self, old: str, new: str, name: str = "sample") -> None:
        """Write SOURCE with one piece replaced, failing if that piece is missing."""
        self.assertIn(old, SOURCE)
        self.write(SOURCE.replace(old, new), name)

    def load(self) -> Agent:
        return load_agent(self.root / "agent_sources/sample.md", self.root / "skills")

    def assert_invalid(self, fragment: str) -> None:
        """Assert that loading the sample fails with a message containing fragment."""
        with self.assertRaises(SourceError) as caught:
            self.load()
        self.assertIn(fragment, str(caught.exception))

    def generate(self) -> tuple[int, Path]:
        """Run the generator over the throwaway repository; return its exit code and output dir."""
        output = self.root / "generated"
        return main(["--root", str(self.root)]), output


def files_under(directory: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
