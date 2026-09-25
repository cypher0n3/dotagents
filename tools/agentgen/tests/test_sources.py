"""Tests for role and target-profile validation."""

from __future__ import annotations

import unittest

from agentgen.errors import GenerationError
from agentgen.sources import load_sources

from tests.helpers import RepoTestCase


class RoleValidationTest(RepoTestCase):
    def assert_invalid(self, fragment: str, **overrides: str) -> None:
        self.write_role(**overrides)
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertIn(fragment, "\n".join(caught.exception.problems))

    def test_valid_role_loads(self) -> None:
        self.write_role()
        role = load_sources(self.root).roles["sample"]
        self.assertTrue(role.readonly)
        self.assertEqual(role.required_skills, ("alpha",))
        self.assertEqual(role.suggested_skills, ("beta",))

    def test_unknown_schema(self) -> None:
        self.assert_invalid("unsupported schema", schema="2")

    def test_name_must_match_file(self) -> None:
        self.write_role()
        (self.root / "agent_sources/roles/sample.yaml").write_text(
            (self.root / "agent_sources/roles/sample.yaml").read_text().replace("name: sample", "name: other"))
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertIn("must match the file name", str(caught.exception))

    def test_reserved_name(self) -> None:
        self.write_role("readme")
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertIn("reserved", str(caught.exception))

    def test_unknown_top_level_key(self) -> None:
        self.assert_invalid("unknown key 'colour'", colour="red")

    def test_unknown_nested_key(self) -> None:
        self.assert_invalid("unknown key 'optional'", skills="\n  optional: [alpha]")

    def test_duplicate_key(self) -> None:
        self.assert_invalid("duplicate key", presentation="\n  claude:\n    color: red\n    color: blue")

    def test_body_must_stay_under_prompts(self) -> None:
        self.assert_invalid("must be a Markdown file under prompts/", body="../../etc/passwd.md")
        self.assert_invalid("must be a Markdown file under prompts/", body="roles/sample.md")

    def test_body_through_symlink(self) -> None:
        self.write_role()
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere/x.md").write_text("# X\n")
        (self.root / "agent_sources/prompts/linked").symlink_to(self.root / "elsewhere")
        self.assert_invalid("passes through a symlink", body="prompts/linked/x.md")

    def test_body_must_open_with_h1(self) -> None:
        self.write_role(body_text="No heading\n")
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertIn("must open with an H1", str(caught.exception))

    def test_body_rejects_crlf(self) -> None:
        self.write_role(body_text="# Sample\r\n")
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertIn("CR line endings", str(caught.exception))

    def test_unknown_target(self) -> None:
        self.assert_invalid("unknown target(s) gemini", targets="[claude, gemini]")

    def test_missing_skill(self) -> None:
        self.assert_invalid("not found under skills/: delta", skills="\n  required: [delta]")

    def test_skill_in_both_lists(self) -> None:
        self.assert_invalid("both required and suggested", skills="\n  required: [alpha]\n  suggested: [alpha]")

    def test_readonly_with_write_tool(self) -> None:
        self.assert_invalid("cannot list Write", restrictions="\n  readonly: true\n  tools: [Read, Write]")

    def test_readonly_on_claude_needs_tools(self) -> None:
        self.assert_invalid("enforces read-only only through tools", restrictions="\n  readonly: true")

    def test_unknown_tool(self) -> None:
        self.assert_invalid("unknown tool(s) Teleport", restrictions="\n  tools: [Read, Teleport]")

    def test_claude_color_required(self) -> None:
        self.assert_invalid("presentation.claude.color is required", presentation=None)
        self.assert_invalid("presentation.claude.color is required", presentation="\n  claude:\n    color: teal")

    def test_presentation_for_unlisted_target(self) -> None:
        self.assert_invalid("names a target the role does not list",
                            targets="[claude]", presentation="\n  claude:\n    color: red\n  cursor:\n    color: red")

    def test_undefined_alias(self) -> None:
        self.assert_invalid("alias 'strnog' is not defined", model="\n  alias: strnog")

    def test_direct_model_for_unlisted_target(self) -> None:
        self.assert_invalid("names a target the role does not list", targets="[claude]", model="\n  cursor: fast")

    def test_list_model_for_single_model_target(self) -> None:
        self.assert_invalid("takes one model", model="\n  cursor: [a, b]")

    def test_override_allowlist(self) -> None:
        self.assert_invalid("does not allow this override", overrides="\n  cursor:\n    is_background: true")
        self.assert_invalid("cannot change the shared role field", overrides="\n  codex:\n    description: other")
        self.assert_invalid("must be one of", overrides="\n  codex:\n    model_reasoning_effort: extreme")

    def test_valid_override(self) -> None:
        self.write_role(overrides="\n  codex:\n    model_reasoning_effort: high")
        self.assertEqual(load_sources(self.root).roles["sample"].overrides, {"codex": {"model_reasoning_effort": "high"}})

    def test_description_rejects_control_characters(self) -> None:
        self.assert_invalid("unsupported character", description='"bad\\u0007bell"')

    def test_problems_from_every_role_are_collected(self) -> None:
        self.write_role("one", schema="2")
        self.write_role("two", targets="[nowhere]")
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertEqual(len(caught.exception.problems), 2)


class ProfileValidationTest(RepoTestCase):
    def edit_profile(self, name: str, old: str, new: str) -> None:
        path = self.root / f"agent_sources/targets/{name}.yaml"
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def assert_invalid(self, fragment: str) -> None:
        self.write_role()
        with self.assertRaises(GenerationError) as caught:
            load_sources(self.root)
        self.assertIn(fragment, str(caught.exception))

    def test_output_must_stay_in_generated(self) -> None:
        self.edit_profile("cursor", "output: generated/cursor/agents", "output: ../outside")
        self.assert_invalid("must be a relative path under")

    def test_template_must_be_plain_name(self) -> None:
        self.edit_profile("cursor", "template: cursor.md.j2", "template: ../cursor.md.j2")
        self.assert_invalid("must be a plain file name")

    def test_template_must_not_be_symlink(self) -> None:
        template = self.root / "agent_sources/templates/cursor.md.j2"
        template.unlink()
        template.symlink_to(self.root / "agent_sources/templates/claude.md.j2")
        self.assert_invalid("is not a regular file")

    def test_native_render_needs_key(self) -> None:
        self.edit_profile("cursor", "  render: native\n  key: readonly", "  render: native")
        self.assert_invalid("needs a key")

    def test_explainer_only_for_hermes(self) -> None:
        self.edit_profile("cursor", "  render: native\n  key: readonly", "  render: explainer")
        self.assert_invalid("only a hermes profile")

    def test_override_cannot_shadow_shared_field(self) -> None:
        self.edit_profile("codex", "  model_reasoning_effort:", "  description:")
        self.assert_invalid("collides with a shared or reserved field")

    def test_unknown_profile_key(self) -> None:
        self.edit_profile("cursor", "noun: agent", "noun: agent\nextra: true")
        self.assert_invalid("unknown key 'extra'")


if __name__ == "__main__":
    unittest.main()
