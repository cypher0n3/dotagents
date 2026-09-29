#!/usr/bin/env python3
"""Offline tests for agent_source.py."""

from __future__ import annotations

import unittest

from agent_front_matter import SourceError
from agent_render import render_claude
from agent_source import load_agents
from agent_test_support import BODY, SOURCE, TreeTestCase


class ValidationTest(TreeTestCase):
    """load_agent accepts valid sources and names the problem in invalid ones."""

    def test_valid_source(self) -> None:
        self.write()
        agent = self.load()
        self.assertEqual(agent.tier, "strong")
        self.assertTrue(agent.readonly)
        self.assertEqual(agent.skills, ["alpha"])
        self.assertEqual(agent.suggested_skills, ["beta"])

    def test_errors(self) -> None:
        # Each case: the SOURCE text to replace, its replacement, and a
        # fragment of the expected error.
        cases = [
            ("schema: 1", "schema: 2", "schema must be 1"),
            ("name: sample", "name: other", "must match the file name"),
            ("model: strong", "model: opus", "is not a tier"),
            ("model: strong", "model:\n  hermes: x", "cannot set a model"),
            ("model: strong", "model:\n  codex: [a, b]", "non-empty string"),
            ("model: strong", "model:\n  gemini: x", "not 'tier' or a tool name"),
            ("model: strong", "model: strong\neffort: extreme", "effort must be one of"),
            ("color: red", "color: teal", "color must be one of"),
            ("color: red\n", "", "color is required"),
            ("  - Grep\n  - Bash\n", "  - Write\n", "cannot list Write"),
            ("tools:\n  - Read\n  - Grep\n  - Bash\n", "", "must list its tools"),
            ("  - Grep\n", "  - Teleport\n", "unknown tool(s) Teleport"),
            ("skills:\n  - alpha", "skills:\n  - gamma", "does not exist under skills/"),
            ("skills:\n  - alpha", "skills:\n  - beta", "both required and suggested"),
            ("color: red", "color: red\nexclude: [gemini]", "unknown tool(s) gemini"),
            ("color: red", "color: red\ncai:\n  max_turns: many", "must be an integer"),
            ("color: red", "color: red\ncai:\n  selection: always", "must be one of auto, lock"),
            ("color: red", "color: red\ncodex:\n  sandbox_mode: danger", "not a codex setting"),
            ("color: red", "color: red\ncolour: red", "unknown key(s) colour"),
        ]
        for old, new, fragment in cases:
            with self.subTest(fragment=fragment):
                self.replace(old, new)
                self.assert_invalid(fragment)

    def test_crlf_sources_read_as_lf(self) -> None:
        # A Windows checkout with core.autocrlf gives CRLF sources.
        self.write(SOURCE.replace("\n", "\r\n"))
        agent = self.load()
        self.assertEqual(agent.body, BODY)
        self.assertNotIn("\r", render_claude(agent))

    def test_stray_carriage_return_is_rejected(self) -> None:
        self.write(SOURCE.replace("You are a sample agent.", "You are\ra sample agent."))
        self.assert_invalid("carriage return")

    def test_body_rules(self) -> None:
        cases = (
            ("No heading\n", "must open with an H1"),
            ("# T\n\n", "exactly one newline"),
            ("# T\n\n## Skill Dependencies\n\nMine.\n", "generator adds that section"),
        )
        for body, fragment in cases:
            with self.subTest(fragment=fragment):
                self.write(SOURCE.replace(BODY, body))
                self.assert_invalid(fragment)

    def test_cai_block_and_model_are_accepted(self) -> None:
        self.replace(
            "color: red",
            "color: red\ncai:\n  selection: lock\n  max_turns: 15\n  mcp_servers: [a]",
        )
        expected = {"selection": "lock", "max_turns": 15, "mcp_servers": ["a"]}
        self.assertEqual(self.load().settings["cai"], expected)

        # A single CAI model is read as a preference list of one.
        self.replace("model: strong", "model:\n  tier: strong\n  cai: ollama-local/q:1b")
        self.assertEqual(self.load().models, {"cai": ["ollama-local/q:1b"]})

    def test_all_problems_are_reported_together(self) -> None:
        self.write(SOURCE.replace("schema: 1", "schema: 2"), "one")
        self.write(SOURCE.replace("name: sample", "name: two").replace("color: red", "color: teal"), "two")
        with self.assertRaises(SourceError) as caught:
            load_agents(self.root)
        self.assertEqual(len(str(caught.exception).splitlines()), 2)

    def test_skill_dependencies_heading_fails_without_skills_in_every_file(self) -> None:
        # The heading is rejected even for an agent with no skills, and every
        # offending file is reported, not just the first.
        body = BODY + "\n## Skill Dependencies\n\nMine.\n"
        without_skills = SOURCE.replace(BODY, body)
        for key in ("skills:\n  - alpha\n", "suggested_skills:\n  - beta\n"):
            without_skills = without_skills.replace(key, "")
        self.write(without_skills.replace("name: sample", "name: one"), "one")
        self.write(without_skills.replace("name: sample", "name: two"), "two")
        with self.assertRaises(SourceError) as caught:
            load_agents(self.root)
        problems = str(caught.exception).splitlines()
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("Skill Dependencies" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
