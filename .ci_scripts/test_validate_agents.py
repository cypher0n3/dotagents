#!/usr/bin/env python3
"""Offline unit tests for validate_agents.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import validate_agents

VALID_AGENT = """---
name: sample-agent
description: A sample agent used by the validator tests.
model: sonnet
color: blue
tools: Read, Grep, Bash
skills:
  - sample-skill
---
# Sample Agent

## Role

Do the sample thing.
"""

INDEX = """# Agent Index

## Agents

- [`sample-agent`](sample-agent.md) - a sample agent.
"""


class ValidateAgentsTest(unittest.TestCase):
    """Behavioral tests for the agent validator."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)
        self.agents = root / "agents"
        self.skills = root / "skills"
        self.agents.mkdir()
        (self.skills / "sample-skill").mkdir(parents=True)
        (self.skills / "sample-skill" / "SKILL.md").write_text("---\nname: sample-skill\n---\n# S\n", encoding="utf-8")
        (self.agents / "README.md").write_text(INDEX, encoding="utf-8")

    def validate(self, filename: str, text: str) -> validate_agents.Report:
        """Validate a single generated agent file and return the report."""
        agent_file = self.agents / filename
        agent_file.write_text(text, encoding="utf-8")
        report = validate_agents.Report()
        validate_agents.validate_agent(agent_file, self.skills, report)
        return report

    def test_valid_agent_reports_nothing(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_name_must_match_filename(self) -> None:
        report = self.validate("other-name.md", VALID_AGENT)
        self.assertTrue(any("does not match filename" in error for error in report.errors))

    def test_missing_frontmatter_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", "# Sample Agent\n\nNo frontmatter here.\n")
        self.assertTrue(any("frontmatter" in error for error in report.errors))

    def test_missing_description_is_an_error(self) -> None:
        text = VALID_AGENT.replace("description: A sample agent used by the validator tests.\n", "")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("missing required key 'description'" in error for error in report.errors))

    def test_unknown_model_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("model: sonnet", "model: gpt-5"))
        self.assertTrue(any("model 'gpt-5'" in error for error in report.errors))

    def test_full_model_identifier_is_accepted(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("model: sonnet", "model: claude-sonnet-5"))
        self.assertEqual(report.errors, [])

    def test_unknown_permission_mode_is_an_error(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\npermissionMode: yolo\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("permissionMode 'yolo'" in error for error in report.errors))

    def test_unknown_memory_scope_is_an_error(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\nmemory: global\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("memory 'global'" in error for error in report.errors))

    def test_max_turns_must_be_positive_integer(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\nmaxTurns: many\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("maxTurns 'many'" in error for error in report.errors))

    def test_missing_color_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("color: blue\n", ""))
        self.assertTrue(any("missing 'color'" in error for error in report.errors))

    def test_missing_model_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("model: sonnet\n", ""))
        self.assertTrue(any("missing 'model'" in error for error in report.errors))

    def test_fable_alias_is_accepted(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("model: sonnet", "model: fable"))
        self.assertEqual(report.errors, [])

    def test_manual_permission_mode_is_accepted(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\npermissionMode: manual\n")
        report = self.validate("sample-agent.md", text)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_documented_color_is_accepted(self) -> None:
        text = VALID_AGENT.replace("color: blue\n", "color: purple\n")
        report = self.validate("sample-agent.md", text)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_unknown_color_is_an_error(self) -> None:
        text = VALID_AGENT.replace("color: blue\n", "color: chartreuse\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("color 'chartreuse'" in error for error in report.errors))

    def test_background_must_be_a_boolean(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\nbackground: sometimes\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("background 'sometimes'" in error for error in report.errors))

    def test_effort_accepts_a_level_or_an_integer(self) -> None:
        for value in ("xhigh", "12"):
            text = VALID_AGENT.replace("model: sonnet\n", f"model: sonnet\neffort: {value}\n")
            report = self.validate("sample-agent.md", text)
            self.assertEqual(report.errors, [], value)
            self.assertEqual(report.warnings, [], value)

    def test_unknown_effort_is_an_error(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\neffort: extreme\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("effort 'extreme'" in error for error in report.errors))

    def test_experimental_block_is_recognized(self) -> None:
        text = VALID_AGENT.replace("model: sonnet\n", "model: sonnet\nexperimental:\n  cacheTtl: 1h\n")
        report = self.validate("sample-agent.md", text)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_empty_tool_entry_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("tools: Read, Grep, Bash", "tools: Read,, Bash"))
        self.assertTrue(any("tools contains an empty entry" in error for error in report.errors))

    def test_agent_group_in_tools_is_one_entry(self) -> None:
        text = VALID_AGENT.replace("tools: Read, Grep, Bash", "tools: Agent(worker, helper), Read")
        report = self.validate("sample-agent.md", text)
        self.assertEqual(report.errors, [])
        self.assertEqual(validate_agents.parse_tool_list("Agent(worker, helper), Read"), ["Agent(worker, helper)", "Read"])

    def test_missing_preloaded_skill_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("- sample-skill", "- no-such-skill"))
        self.assertTrue(any("preloaded skill 'no-such-skill'" in error for error in report.errors))

    def test_inline_skill_list_is_parsed(self) -> None:
        text = VALID_AGENT.replace("skills:\n  - sample-skill\n", "skills: [sample-skill, no-such-skill]\n")
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("preloaded skill 'no-such-skill'" in error for error in report.errors))
        self.assertFalse(any("'sample-skill'" in error for error in report.errors))

    def test_hooks_block_is_recognized(self) -> None:
        text = VALID_AGENT.replace(
            "model: sonnet\n",
            "model: sonnet\nhooks:\n  PostToolUse:\n    - matcher: Edit\n      hooks:\n        - type: command\n          command: ./lint.sh\n",
        )
        report = self.validate("sample-agent.md", text)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_unknown_key_is_a_warning(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("model: sonnet\n", "model: sonnet\ncolour: red\n"))
        self.assertEqual(report.errors, [])
        self.assertTrue(any("unrecognized frontmatter key 'colour'" in warning for warning in report.warnings))

    def test_body_must_open_with_h1(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT.replace("# Sample Agent", "## Sample Agent"))
        self.assertTrue(any("single H1 heading" in error for error in report.errors))

    def test_body_needs_instructions(self) -> None:
        text = VALID_AGENT.split("# Sample Agent")[0] + "# Sample Agent\n"
        report = self.validate("sample-agent.md", text)
        self.assertTrue(any("no instructions" in error for error in report.errors))

    def test_html_comment_is_an_error(self) -> None:
        report = self.validate("sample-agent.md", VALID_AGENT + "\n<!-- hidden note -->\n")
        self.assertTrue(any("HTML comment" in error for error in report.errors))

    def test_index_must_link_every_agent(self) -> None:
        (self.agents / "sample-agent.md").write_text(VALID_AGENT, encoding="utf-8")
        report = validate_agents.Report()
        validate_agents.validate_index(self.agents / "README.md", ["sample-agent", "unlisted"], report)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("'unlisted' is not linked", report.errors[0])

    def test_main_validates_a_whole_tree(self) -> None:
        (self.agents / "sample-agent.md").write_text(VALID_AGENT, encoding="utf-8")
        self.assertEqual(validate_agents.main([str(self.agents), str(self.skills)]), 0)
        (self.agents / "sample-agent.md").write_text(VALID_AGENT.replace("model: sonnet", "model: bogus"), encoding="utf-8")
        self.assertEqual(validate_agents.main([str(self.agents), str(self.skills)]), 1)

    def test_main_rejects_missing_roots(self) -> None:
        self.assertEqual(validate_agents.main([str(self.agents / "missing"), str(self.skills)]), 1)


if __name__ == "__main__":
    unittest.main()
