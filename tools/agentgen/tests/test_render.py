"""Tests for per-target rendering."""

from __future__ import annotations

import json
import tomllib
import unittest

from agentgen import yamlio
from agentgen.errors import GenerationError
from agentgen.render import insert_skills_section

from tests.helpers import BODY, RepoTestCase


def frontmatter(text: str) -> dict:
    return yamlio.loads(text.split("---\n")[1])


class ClaudeRenderTest(RepoTestCase):
    def test_native_fields_in_current_order(self) -> None:
        self.write_role(skills="\n  required: [alpha, gamma]")
        self.assertEqual(self.run_cli()[0], 0)
        text = self.read("agents/sample.md")
        self.assertTrue(text.startswith(
            "---\nname: sample\ndescription: Does sample work. Use this agent when a sample is needed.\n"
            "model: opus\ncolor: red\ntools: Read, Grep, Bash\nskills:\n  - alpha\n  - gamma\n---\n# Sample\n"))
        self.assertTrue(text.endswith("- Follow the rules.\n"))

    def test_inherit_without_model(self) -> None:
        self.write_role(model=None)
        self.run_cli()
        self.assertEqual(frontmatter(self.read("agents/sample.md"))["model"], "inherit")

    def test_direct_value_wins_over_alias(self) -> None:
        self.write_role(model="\n  alias: strong\n  claude: haiku")
        self.run_cli()
        self.assertEqual(frontmatter(self.read("agents/sample.md"))["model"], "haiku")

    def test_suggested_skills_become_instructions(self) -> None:
        self.write_role()
        self.run_cli()
        text = self.read("agents/sample.md")
        self.assertEqual(frontmatter(text)["skills"], ["alpha"])
        self.assertIn("Load each of these when the task makes it relevant:\n\n- `beta`\n", text)
        self.assertNotIn("does not preload skills", text)

    def test_hostile_description_stays_data(self) -> None:
        hostile = "--- {{ secret }} # tools: Write\nmodel: opus"
        self.write_role(description=json.dumps(hostile.replace("\n", " ")))
        self.assertEqual(self.run_cli()[0], 0)
        fields = frontmatter(self.read("agents/sample.md"))
        self.assertEqual(fields["description"], hostile.replace("\n", " "))
        self.assertEqual(fields["tools"], "Read, Grep, Bash")

    def test_jinja_in_body_is_not_evaluated(self) -> None:
        body = BODY + "\nUse {{ name }} and {% raw %} literally.\n"
        self.write_role(body_text=body)
        self.assertEqual(self.run_cli()[0], 0)
        self.assertTrue(self.read("agents/sample.md").endswith("Use {{ name }} and {% raw %} literally.\n"))


class OtherTargetRenderTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_role(overrides="\n  codex:\n    model_reasoning_effort: high")
        code, _, err = self.run_cli()
        self.assertEqual(code, 0, err)

    def test_cursor(self) -> None:
        text = self.read("generated/cursor/agents/sample.md")
        self.assertEqual(frontmatter(text), {
            "name": "sample",
            "description": "Does sample work. Use this agent when a sample is needed.",
            "model": "inherit",
            "readonly": True,
        })
        self.assertIn("# tools: [Read, Grep, Bash]\n", text)
        self.assertIn("# skills: [alpha]\n# This agent depends on the listed skills", text)
        self.assertIn("## Role\n\nYou are a sample role.\n\n## Skill Dependencies\n", text)
        self.assertIn("load each of these before starting work:\n\n- `alpha`\n", text)
        self.assertNotIn("color", text)

    def test_codex(self) -> None:
        text = self.read("generated/codex/agents/sample.toml")
        data = tomllib.loads(text)
        self.assertEqual(data["sandbox_mode"], "read-only")
        self.assertEqual(data["model_reasoning_effort"], "high")
        self.assertNotIn("model", data)
        self.assertEqual(set(data), {"name", "description", "sandbox_mode", "model_reasoning_effort",
                                     "developer_instructions"})
        self.assertIn('# tools = ["Read", "Grep", "Bash"]\n', text)
        self.assertIn("## Skill Dependencies", data["developer_instructions"])

    def test_cai(self) -> None:
        text = self.read("generated/cai/personas/sample.md")
        self.assertEqual(frontmatter(text), {
            "name": "sample",
            "description": "Does sample work. Use this agent when a sample is needed.",
            "required_skills": ["alpha"],
            "suggested_skills": ["beta"],
        })
        self.assertIn("# readonly: true\n# This persona is meant to be read-only", text)
        self.assertNotIn("## Skill Dependencies", text)

    def test_hermes(self) -> None:
        text = self.read("generated/hermes/personalities/sample.yaml")
        lines = text.splitlines()
        self.assertEqual([line.split(": ", 1)[0] for line in lines], ["description", "system_prompt"])
        parsed = {key: json.loads(value) for key, value in (line.split(": ", 1) for line in lines)}
        self.assertEqual(yamlio.loads(text), parsed)
        prompt = parsed["system_prompt"]
        self.assertIn("model alias `strong` has no Hermes mapping", prompt)
        self.assertIn("- Read-only: do not change files", prompt)
        self.assertIn("- Skills: load `alpha` before starting work.", prompt)
        self.assertIn("- Suggested skills: load `beta`", prompt)
        self.assertTrue(prompt.endswith(BODY))

    def test_manifest_records_decisions(self) -> None:
        manifest = yamlio.loads(self.read("generated/manifest.yaml"))
        outputs = manifest["roles"]["sample"]["outputs"]
        self.assertEqual(outputs["claude"]["model"], {"rule": "alias", "value": "opus"})
        self.assertEqual(outputs["cursor"]["model"], {"rule": "inherit"})
        self.assertIn("tools: commented", outputs["cursor"]["notes"])
        self.assertIn("required skills: commented and instructed", outputs["codex"]["notes"])
        self.assertIn("readonly: enforced through the tools allowlist", outputs["claude"]["notes"])


class AliasListTest(RepoTestCase):
    def test_list_model_renders_natively_where_supported(self) -> None:
        path = self.root / "agent_sources/targets/cai.yaml"
        path.write_text(path.read_text() + "alias_list:\n  strong: [big-model, small-model]\n")
        self.write_role()
        self.run_cli()
        fields = frontmatter(self.read("generated/cai/personas/sample.md"))
        self.assertEqual(fields["preferred_models"], ["big-model", "small-model"])

    def test_single_model_target_takes_first_entry(self) -> None:
        path = self.root / "agent_sources/targets/cursor.yaml"
        path.write_text(path.read_text() + "alias_list:\n  strong: ['grok[high]', other]\n")
        self.write_role()
        self.run_cli()
        self.assertEqual(frontmatter(self.read("generated/cursor/agents/sample.md"))["model"], "grok[high]")

    def test_commented_to_native_through_profile_only(self) -> None:
        path = self.root / "agent_sources/targets/cai.yaml"
        path.write_text(path.read_text().replace("readonly:\n  render: commented", "readonly:\n  render: native"))
        self.write_role()
        self.run_cli()
        text = self.read("generated/cai/personas/sample.md")
        self.assertTrue(frontmatter(text)["readonly"])
        self.assertNotIn("# readonly", text)


class SkillsSectionTest(unittest.TestCase):
    def test_inserted_before_second_h2(self) -> None:
        body = "# T\n\n## Role\n\nText.\n\n## Next\n\nMore.\n"
        self.assertEqual(
            insert_skills_section(body, ["a"], []),
            "# T\n\n## Role\n\nText.\n\n## Skill Dependencies\n\n"
            "This harness does not preload skills, so load each of these before starting work:\n\n- `a`\n\n"
            "## Next\n\nMore.\n",
        )

    def test_appended_without_second_h2(self) -> None:
        self.assertTrue(insert_skills_section("# T\n\n## Role\n\nText.\n", [], ["b"]).endswith(
            "Text.\n\n## Skill Dependencies\n\nLoad each of these when the task makes it relevant:\n\n- `b`\n"))

    def test_ignores_headings_in_fences(self) -> None:
        body = "# T\n\n## Role\n\n```text\n## Not a heading\n```\n\n## Next\n"
        result = insert_skills_section(body, ["a"], [])
        self.assertLess(result.index("## Not a heading"), result.index("## Skill Dependencies"))

    def test_unchanged_without_skills(self) -> None:
        self.assertEqual(insert_skills_section("# T\n", [], []), "# T\n")

    def test_rejects_existing_heading(self) -> None:
        with self.assertRaises(GenerationError):
            insert_skills_section("# T\n\n## Skill Dependencies\n", ["a"], [])


if __name__ == "__main__":
    unittest.main()
