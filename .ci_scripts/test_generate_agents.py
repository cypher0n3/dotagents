#!/usr/bin/env python3
"""Offline tests for generate_agents.py."""

from __future__ import annotations

import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

import generate_agents as gen
from agent_test_support import REPO, SOURCE, TreeTestCase, files_under


class OutputTest(TreeTestCase):
    """The generator replaces generated/ as a whole, or leaves it untouched."""

    def test_generates_every_tool_and_rebuilds_from_scratch(self) -> None:
        self.write()
        code, output = self.generate()
        self.assertEqual(code, 0)
        written = {path.relative_to(output).as_posix() for path in files_under(output)}
        expected = {
            "claude/agents/sample.md",
            "codex/agents/sample.toml",
            "cursor/agents/sample.md",
            "hermes/personalities/sample.yaml",
        }
        self.assertEqual(written, expected)

        # A file no source produces is gone after the next run, and no staging
        # directory is left behind.
        (output / "codex/agents/stale.toml").write_text("old\n")
        self.generate()
        self.assertFalse((output / "codex/agents/stale.toml").exists())
        leftovers = [path.name for path in self.root.iterdir() if path.name.startswith(".generated")]
        self.assertEqual(leftovers, [])

    def test_exclude_skips_tools(self) -> None:
        self.replace("color: red", "color: red\nexclude: [hermes, cai]")
        _, output = self.generate()
        self.assertFalse((output / "hermes").exists())
        self.assertTrue((output / "claude/agents/sample.md").is_file())

    def test_invalid_source_leaves_previous_output(self) -> None:
        self.write()
        _, output = self.generate()
        before = files_under(output)
        self.write(SOURCE.replace("schema: 1", "schema: 2"))
        code, _ = self.generate()
        self.assertEqual(code, 1)
        self.assertEqual(files_under(output), before)

    def test_output_that_is_a_symlink_is_refused(self) -> None:
        self.write()
        (self.root / "elsewhere").mkdir()
        (self.root / "generated").symlink_to(self.root / "elsewhere")
        code, _ = self.generate()
        self.assertEqual(code, 1)
        self.assertEqual(list((self.root / "elsewhere").iterdir()), [])


class RepositoryTest(unittest.TestCase):
    """The repository's own sources generate cleanly."""

    def test_repository_sources_generate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "generated"
            self.assertEqual(gen.main(["--root", str(REPO), "--output", str(output)]), 0)
            sources = {path.stem for path in (REPO / "agent_sources").glob("*.md")} - {"README"}
            generated = {path.stem for path in (output / "claude/agents").glob("*.md")}
            self.assertEqual(generated, sources)
            for path in (output / "codex/agents").glob("*.toml"):
                tomllib.loads(path.read_text())
            shutil.rmtree(output)


if __name__ == "__main__":
    unittest.main()
