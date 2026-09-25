"""Checks against this repository's own sources and committed outputs."""

from __future__ import annotations

import unittest

from agentgen import manifest
from agentgen.render import render_all
from agentgen.sources import load_sources

from tests.helpers import REPO_ROOT


class RepositoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = load_sources(REPO_ROOT)
        cls.rendered = render_all(REPO_ROOT, cls.sources.profiles, cls.sources.roles)

    def test_every_agent_file_is_generated(self) -> None:
        agents = {path.name for path in (REPO_ROOT / "agents").glob("*.md")} - {"README.md"}
        claude = {item.path.split("/")[-1] for item in self.rendered if item.target == "claude"}
        self.assertEqual(claude, agents)

    def test_claude_output_matches_committed_agents(self) -> None:
        for item in self.rendered:
            if item.target == "claude":
                with self.subTest(role=item.role):
                    self.assertEqual(item.content, (REPO_ROOT / item.path).read_bytes())

    def test_committed_outputs_and_manifest_are_current(self) -> None:
        for item in self.rendered:
            with self.subTest(path=item.path):
                self.assertEqual(item.content, (REPO_ROOT / item.path).read_bytes())
        built = manifest.build(REPO_ROOT, self.sources, self.rendered)
        self.assertEqual(built, (REPO_ROOT / manifest.MANIFEST_PATH).read_bytes())

    def test_every_role_targets_every_profile(self) -> None:
        for role in self.sources.roles.values():
            with self.subTest(role=role.name):
                self.assertEqual(set(role.targets), set(self.sources.profiles))


if __name__ == "__main__":
    unittest.main()
