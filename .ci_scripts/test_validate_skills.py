#!/usr/bin/env python3
"""Offline unit tests for validate_skills.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import validate_skills

VALID_SKILL = """---
name: sample-skill
description: A sample skill used by the validator tests.
user-invocable: true
---

# Sample Skill

Do the sample thing.
"""


def write_skill(root: Path, name: str, text: str) -> Path:
    """Create a skill directory containing the given SKILL.md text."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


class ValidateSkillsTest(unittest.TestCase):
    """Behavioral tests for the skill validator."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def validate(self, name: str, text: str) -> validate_skills.Report:
        """Validate a single generated skill and return the report."""
        skill_dir = write_skill(self.root, name, text)
        report = validate_skills.Report()
        validate_skills.validate_skill(skill_dir, report)
        return report

    def test_valid_skill_reports_nothing(self) -> None:
        report = self.validate("sample-skill", VALID_SKILL)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_name_must_match_directory(self) -> None:
        report = self.validate("other-name", VALID_SKILL)
        self.assertTrue(any("does not match directory" in error for error in report.errors))

    def test_missing_frontmatter_is_an_error(self) -> None:
        report = self.validate("sample-skill", "# Sample Skill\n\nNo frontmatter here.\n")
        self.assertTrue(any("frontmatter" in error for error in report.errors))

    def test_missing_description_is_an_error(self) -> None:
        report = self.validate("sample-skill", "---\nname: sample-skill\n---\n\n# Sample Skill\n\nBody.\n")
        self.assertTrue(any("'description'" in error for error in report.errors))

    def test_non_boolean_user_invocable_is_an_error(self) -> None:
        text = VALID_SKILL.replace("user-invocable: true", "user-invocable: yes")
        report = self.validate("sample-skill", text)
        self.assertTrue(any("must be true or false" in error for error in report.errors))

    def test_unknown_key_is_a_warning_only(self) -> None:
        text = VALID_SKILL.replace("user-invocable: true", "user-invokable: true")
        report = self.validate("sample-skill", text)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("unrecognized frontmatter key" in warning for warning in report.warnings))

    def test_body_must_open_with_an_h1(self) -> None:
        text = VALID_SKILL.replace("\n# Sample Skill", "\n## Sample Skill")
        report = self.validate("sample-skill", text)
        self.assertTrue(any("single H1 heading" in error for error in report.errors))

    def test_body_without_an_h1_is_an_error(self) -> None:
        text = VALID_SKILL.replace("# Sample Skill", "Sample Skill")
        report = self.validate("sample-skill", text)
        self.assertTrue(any("single H1 heading" in error for error in report.errors))

    def test_html_comment_in_the_body_is_an_error(self) -> None:
        text = VALID_SKILL.replace("Do the sample thing.", "<!-- a note for humans -->\n\nDo the sample thing.")
        report = self.validate("sample-skill", text)
        self.assertTrue(any("HTML comment" in error for error in report.errors))

    def test_multi_line_html_comment_is_reported_once(self) -> None:
        text = VALID_SKILL.replace("Do the sample thing.", "<!-- line one\nline two -->\n\nDo the sample thing.")
        report = self.validate("sample-skill", text)
        self.assertEqual(len([e for e in report.errors if "HTML comment" in e]), 1)

    def test_spec_fields_are_recognized(self) -> None:
        text = VALID_SKILL.replace(
            "user-invocable: true",
            "license: Apache-2.0\ncompatibility: Requires git\nmetadata:\n  author: example-org",
        )
        report = self.validate("sample-skill", text)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_overlong_name_is_an_error(self) -> None:
        long_name = "a" * 65
        text = VALID_SKILL.replace("name: sample-skill", f"name: {long_name}")
        report = self.validate(long_name, text)
        self.assertTrue(any("the limit is 64" in error for error in report.errors))

    def test_consecutive_hyphens_in_name_are_an_error(self) -> None:
        text = VALID_SKILL.replace("name: sample-skill", "name: sample--skill")
        report = self.validate("sample--skill", text)
        self.assertTrue(any("consecutive hyphens" in error for error in report.errors))

    def test_overlong_compatibility_is_an_error(self) -> None:
        text = VALID_SKILL.replace("user-invocable: true", "compatibility: " + "x" * 501)
        report = self.validate("sample-skill", text)
        self.assertTrue(any("the limit is 500" in error for error in report.errors))

    def test_long_body_warns_but_does_not_error(self) -> None:
        body = "\n".join(f"- line {number}" for number in range(600))
        text = VALID_SKILL.replace("Do the sample thing.", body)
        report = self.validate("sample-skill", text)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("recommends under 500" in warning for warning in report.warnings))

    def test_token_heavy_body_warns(self) -> None:
        body = "\n".join("word " * 60 for _ in range(80))
        text = VALID_SKILL.replace("Do the sample thing.", body)
        report = self.validate("sample-skill", text)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("tokens" in warning for warning in report.warnings))

    def test_html_comment_inside_a_code_fence_is_allowed(self) -> None:
        text = VALID_SKILL.replace(
            "Do the sample thing.",
            "```markdown\n<!-- sample content, not a note -->\n```",
        )
        report = self.validate("sample-skill", text)
        self.assertEqual(report.errors, [])

    def test_block_scalar_description_is_parsed(self) -> None:
        text = (
            "---\nname: sample-skill\ndescription: |\n  First line.\n  Second line.\n---\n"
            "\n# Sample Skill\n\nBody.\n"
        )
        report = self.validate("sample-skill", text)
        self.assertEqual(report.errors, [])

    def test_missing_skill_file_is_an_error(self) -> None:
        (self.root / "empty-skill").mkdir()
        report = validate_skills.Report()
        validate_skills.validate_skill(self.root / "empty-skill", report)
        self.assertTrue(any("missing SKILL.md" in error for error in report.errors))

    def test_incomplete_agent_manifest_is_an_error(self) -> None:
        skill_dir = write_skill(self.root, "sample-skill", VALID_SKILL)
        manifest = skill_dir / "agents" / "openai.yaml"
        manifest.parent.mkdir()
        manifest.write_text('interface:\n  display_name: "Sample"\n', encoding="utf-8")
        report = validate_skills.Report()
        validate_skills.validate_skill(skill_dir, report)
        self.assertTrue(any("short_description" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()
