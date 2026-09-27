#!/usr/bin/env python3
"""Offline tests for agent_render.py."""

from __future__ import annotations

import json
import tomllib
import unittest

from agent_front_matter import SourceError
from agent_render import RENDERERS, insert_skills_section, skills_section
from agent_test_support import BODY, DESCRIPTION_LINE, GENERATED_HEADER, SOURCE, TreeTestCase


class RenderTest(TreeTestCase):
    """Each renderer writes its tool's format, and comments what the tool cannot enforce."""

    def render(self, tool: str, text: str = SOURCE) -> str:
        self.write(text)
        return RENDERERS[tool](self.load())

    def test_claude(self) -> None:
        text = self.render("claude")
        expected_start = "\n".join(
            [
                "---",
                GENERATED_HEADER,
                "name: sample",
                DESCRIPTION_LINE,
                "model: opus",
                "color: red",
                "tools: Read, Grep, Bash",
                "skills:",
                "  - alpha",
                "---",
                "# Sample",
                "",
            ]
        )
        self.assertTrue(text.startswith(expected_start), text)
        # Claude Code preloads required skills, so only suggested ones reach the body.
        self.assertIn(
            "## Skill Dependencies\n\nLoad each of these when the task makes it relevant:\n\n- `beta`\n",
            text,
        )
        self.assertNotIn("does not preload", text)

    def test_claude_model_rules(self) -> None:
        cases = (
            ("model: strong\n", "", "model: inherit\n"),
            ("model: strong", "model: frontier", "model: fable\n"),
            ("model: strong", "model:\n  tier: strong\n  claude: haiku", "model: haiku\n"),
            ("model: strong", "model: strong\neffort: max", "effort: max\n"),
        )
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, self.render("claude", SOURCE.replace(old, new)))

    def test_codex(self) -> None:
        source = SOURCE.replace("model: strong", "model:\n  tier: strong\n  codex: gpt-x\neffort: max")
        data = tomllib.loads(self.render("codex", source))
        self.assertEqual(data["model"], "gpt-x")
        self.assertEqual(data["model_reasoning_effort"], "xhigh")
        self.assertEqual(data["sandbox_mode"], "read-only")
        instructions = data["developer_instructions"]
        self.assertIn("## Skill Dependencies", instructions)
        self.assertIn("load each of these before starting work:\n\n- `alpha`", instructions)

        # The Codex tier map is empty, so a tier alone sets no model.
        self.assertNotIn("model", tomllib.loads(self.render("codex")))

    def test_codex_multiline_edge_cases(self) -> None:
        bodies = (
            '# T\n\nQuote " and """ and \\ backslash.\n',
            '# T\n\nEnds with a quote"\n',
        )
        for body in bodies:
            with self.subTest(body=body):
                data = tomllib.loads(self.render("codex", SOURCE.replace(BODY, body)))
                self.assertTrue(data["developer_instructions"].startswith(body.rstrip("\n")))

    def test_cursor(self) -> None:
        text = self.render("cursor", SOURCE.replace("model: strong", "model: strong\neffort: high"))
        front = text.split("---\n")[1]
        self.assertIn("model: inherit\nreadonly: true\n", front)
        self.assertIn("# effort: high\n", front)
        self.assertIn("# tools:\n#   - Read\n#   - Grep\n#   - Bash\n", front)
        self.assertIn("# skills:\n#   - alpha\n", front)
        self.assertNotIn("[", front, "lists are written as block lists")
        self.assertNotIn("color", text)
        self.assertIn("## Role\n\nYou are a sample agent.\n\n## Skill Dependencies\n", text)

    def test_hermes(self) -> None:
        lines = self.render("hermes").splitlines()
        self.assertTrue(lines[0].startswith("# Generated from"))
        data = {}
        for line in lines[1:]:
            key, value = line.split(": ", 1)
            data[key] = json.loads(value)
        self.assertEqual(set(data), {"description", "system_prompt"})
        prompt = data["system_prompt"]
        self.assertIn("- Read-only: do not change files", prompt)
        self.assertIn("- Skills: load `alpha` before starting work.", prompt)
        self.assertTrue(prompt.endswith(BODY))

    def test_skills_section_passes_markdown_lint(self) -> None:
        section = skills_section(["alpha"], ["beta"])
        self.assertEqual(section[0], "## Skill Dependencies")
        for index, line in enumerate(section):
            # A heading or list must be followed by a blank line or another item.
            following = section[index + 1] if index + 1 < len(section) else ""
            if line.startswith(("#", "- ")):
                self.assertTrue(following == "" or following.startswith("- "), line)
            # The repository puts one sentence on each line.
            self.assertNotIn(". ", line)

    def test_skills_section_placement(self) -> None:
        body = "# T\n\n## Role\n\n```text\n## Not a heading\n```\n\n## Next\n"
        result = insert_skills_section(body, ["a"], [])
        # A heading inside a code fence does not count as the second H2.
        self.assertLess(result.index("## Not a heading"), result.index("## Skill Dependencies"))
        self.assertLess(result.index("## Skill Dependencies"), result.index("## Next"))

        # With no second H2, the section goes at the end.
        appended = insert_skills_section("# T\n\n## Role\n", [], ["b"])
        self.assertTrue(appended.endswith("- `b`\n"))

        with self.assertRaises(SourceError):
            insert_skills_section("# T\n\n## Skill Dependencies\n", ["a"], [])

    def test_hostile_description_stays_one_scalar(self) -> None:
        source = SOURCE.replace(DESCRIPTION_LINE, 'description: "x: y # z --- [a]"')
        self.assertIn('description: "x: y # z --- [a]"\n', self.render("cursor", source))


if __name__ == "__main__":
    unittest.main()
