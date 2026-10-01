#!/usr/bin/env python3
"""Offline tests for agent_front_matter.py."""

from __future__ import annotations

import textwrap
import unittest

from agent_front_matter import SourceError, parse_front_matter


class ParserTest(unittest.TestCase):
    """The front matter parser reads its YAML subset and rejects everything else."""

    def parse(self, front: str) -> dict:
        text = "---\n" + textwrap.dedent(front) + "---\n# T\n"
        return parse_front_matter(text, "test")[0]

    def test_scalars_lists_and_comments(self) -> None:
        data = self.parse(
            """\
            # a comment
            a: plain text, with commas  # trailing comment
            b: "quoted: # not a comment"
            c: 'it''s'
            d: 42
            e: true
            f: [x, "y, z", 'w']
            g:
              - one
              - two
            """
        )
        expected = {
            "a": "plain text, with commas",
            "b": "quoted: # not a comment",
            "c": "it's",
            "d": 42,
            "e": True,
            "f": ["x", "y, z", "w"],
            "g": ["one", "two"],
        }
        self.assertEqual(data, expected)

    def test_nested_model_block_at_any_indent(self) -> None:
        for step in ("  ", "    "):
            with self.subTest(indent=len(step)):
                front = (
                    "model:\n"
                    f"{step}claude: opus\n"
                    f"{step}cai:\n"
                    f"{step * 2}- ollama-local/a:1b\n"
                    f"{step * 2}- ollama-local/b:2b\n"
                    f"{step}tier: strong\n"
                )
                expected = {
                    "claude": "opus",
                    "cai": ["ollama-local/a:1b", "ollama-local/b:2b"],
                    "tier": "strong",
                }
                self.assertEqual(self.parse(front)["model"], expected)

    def test_list_may_sit_at_its_keys_indent(self) -> None:
        data = self.parse("model:\n  cai:\n  - a\n  - b\n")
        self.assertEqual(data["model"], {"cai": ["a", "b"]})

    def test_rejects_unsupported_syntax(self) -> None:
        unsupported = (
            "a: &anchor x\n",
            "a: *alias\n",
            "a: !tag x\n",
            "a: |\n  text\n",
            "a: {b: c}\n",
            "a: 1\na: 2\n",  # duplicate key
            "a: yes\n",  # a YAML 1.1 boolean
            "a:\n",  # no value
            "a:\n\t- x\n",  # tab indentation
        )
        for front in unsupported:
            with self.subTest(front=front), self.assertRaises(SourceError):
                parse_front_matter("---\n" + front + "---\n# T\n", "test")

    def test_requires_front_matter(self) -> None:
        with self.assertRaises(SourceError):
            parse_front_matter("# No front matter\n", "test")


if __name__ == "__main__":
    unittest.main()
