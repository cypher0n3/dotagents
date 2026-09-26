#!/usr/bin/env python3
"""Offline tests for generate_agents.py."""

from __future__ import annotations

import json
import shutil
import tempfile
import textwrap
import tomllib
import unittest
from pathlib import Path

import generate_agents as gen

REPO = Path(__file__).resolve().parents[1]

BODY = textwrap.dedent(
    """\
    # Sample

    ## Role

    You are a sample agent.

    ## Working Rules

    - Follow the rules.
    """
)

SOURCE = textwrap.dedent(
    """\
    ---
    schema: 1
    name: sample
    description: Does sample work. Use this agent when a sample is needed.
    model: strong
    color: red
    readonly: true
    tools: [Read, Grep, Bash]
    skills: [alpha]
    suggested_skills: [beta]
    ---
    """
) + BODY


class TreeTestCase(unittest.TestCase):
    """A throwaway repository with agent_sources/ and skills/."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "agent_sources").mkdir()
        (self.root / "agent_sources/README.md").write_text("# Agent Index\n")
        for skill in ("alpha", "beta"):
            (self.root / "skills" / skill).mkdir(parents=True)
            (self.root / "skills" / skill / "SKILL.md").write_text("---\nname: x\n---\n# X\n")

    def write(self, text: str = SOURCE, name: str = "sample") -> Path:
        path = self.root / "agent_sources" / f"{name}.md"
        path.write_text(text)
        return path

    def replace(self, old: str, new: str, name: str = "sample") -> None:
        self.assertIn(old, SOURCE)
        self.write(SOURCE.replace(old, new), name)

    def load(self) -> gen.Agent:
        return gen.load_agent(self.root / "agent_sources/sample.md", self.root / "skills")

    def assert_invalid(self, fragment: str) -> None:
        with self.assertRaises(gen.SourceError) as caught:
            self.load()
        self.assertIn(fragment, str(caught.exception))

    def generate(self) -> tuple[int, Path]:
        output = self.root / "generated"
        return gen.main(["--root", str(self.root)]), output


class ParserTest(unittest.TestCase):
    def parse(self, front: str) -> dict:
        return gen.parse_front_matter("---\n" + textwrap.dedent(front) + "---\n# T\n", "test")[0]

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
        self.assertEqual(data, {"a": "plain text, with commas", "b": "quoted: # not a comment", "c": "it's",
                                "d": 42, "e": True, "f": ["x", "y, z", "w"], "g": ["one", "two"]})

    def test_nested_model_block_at_any_indent(self) -> None:
        for indent in ("  ", "    "):
            with self.subTest(indent=len(indent)):
                data = self.parse(
                    f"model:\n{indent}claude: opus\n{indent}cai:\n{indent}{indent}- ollama-local/a:1b\n"
                    f"{indent}{indent}- ollama-local/b:2b\n{indent}tier: strong\n"
                )
                self.assertEqual(data["model"], {"claude": "opus", "cai": ["ollama-local/a:1b", "ollama-local/b:2b"],
                                                 "tier": "strong"})

    def test_compact_sequence_under_key(self) -> None:
        self.assertEqual(self.parse("model:\n  cai:\n  - a\n  - b\n")["model"], {"cai": ["a", "b"]})

    def test_rejects_unsupported_syntax(self) -> None:
        for front in ("a: &anchor x\n", "a: *alias\n", "a: !tag x\n", "a: |\n  text\n", "a: {b: c}\n",
                      "a: 1\na: 2\n", "a: yes\n", "a:\n", "a:\n\t- x\n"):
            with self.subTest(front=front), self.assertRaises(gen.SourceError):
                gen.parse_front_matter("---\n" + front + "---\n# T\n", "test")

    def test_requires_front_matter(self) -> None:
        with self.assertRaises(gen.SourceError):
            gen.parse_front_matter("# No front matter\n", "test")


class ValidationTest(TreeTestCase):
    def test_valid_source(self) -> None:
        self.write()
        agent = self.load()
        self.assertEqual((agent.tier, agent.readonly, agent.skills, agent.suggested_skills),
                         ("strong", True, ["alpha"], ["beta"]))

    def test_errors(self) -> None:
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
            ("tools: [Read, Grep, Bash]", "tools: [Read, Write]", "cannot list Write"),
            ("tools: [Read, Grep, Bash]\n", "", "must list its tools"),
            ("tools: [Read, Grep, Bash]", "tools: [Read, Teleport]", "unknown tool(s) Teleport"),
            ("skills: [alpha]", "skills: [gamma]", "does not exist under skills/"),
            ("skills: [alpha]", "skills: [beta]", "both required and suggested"),
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

    def test_body_rules(self) -> None:
        for body, fragment in (("No heading\n", "must open with an H1"), ("# T\n\n", "exactly one newline")):
            with self.subTest(fragment=fragment):
                self.write(SOURCE.replace(BODY, body))
                self.assert_invalid(fragment)

    def test_cai_block_and_model_are_accepted(self) -> None:
        self.replace("color: red", "color: red\ncai:\n  selection: lock\n  max_turns: 15\n  mcp_servers: [a]")
        self.assertEqual(self.load().blocks["cai"], {"selection": "lock", "max_turns": 15, "mcp_servers": ["a"]})
        self.replace("model: strong", "model:\n  tier: strong\n  cai: ollama-local/q:1b")
        self.assertEqual(self.load().models, {"cai": ["ollama-local/q:1b"]})

    def test_all_problems_are_reported_together(self) -> None:
        self.write(SOURCE.replace("schema: 1", "schema: 2"), "one")
        self.write(SOURCE.replace("name: sample", "name: two").replace("color: red", "color: teal"), "two")
        with self.assertRaises(gen.SourceError) as caught:
            gen.load_agents(self.root)
        self.assertEqual(len(str(caught.exception).splitlines()), 2)


class RenderTest(TreeTestCase):
    def render(self, tool: str, text: str = SOURCE) -> str:
        self.write(text)
        return gen.RENDERERS[tool](self.load())

    def test_claude(self) -> None:
        text = self.render("claude")
        self.assertTrue(text.startswith(
            "---\n# Generated from agent_sources/sample.md by .ci_scripts/generate_agents.py; do not edit, "
            "changes are lost at the next generation.\nname: sample\n"
            "description: Does sample work. Use this agent when a sample is needed.\nmodel: opus\ncolor: red\n"
            "tools: Read, Grep, Bash\nskills:\n  - alpha\n---\n# Sample\n"))
        self.assertIn("## Skill Dependencies\n\nLoad each of these when the task makes it relevant:\n\n- `beta`\n", text)
        self.assertNotIn("does not preload", text)

    def test_claude_model_rules(self) -> None:
        self.assertIn("model: inherit\n", self.render("claude", SOURCE.replace("model: strong\n", "")))
        self.assertIn("model: fable\n", self.render("claude", SOURCE.replace("model: strong", "model: frontier")))
        own = SOURCE.replace("model: strong", "model:\n  tier: strong\n  claude: haiku")
        self.assertIn("model: haiku\n", self.render("claude", own))
        self.assertIn("effort: max\n", self.render("claude", SOURCE.replace("model: strong", "model: strong\neffort: max")))

    def test_codex(self) -> None:
        source = SOURCE.replace("model: strong", "model:\n  tier: strong\n  codex: gpt-x\neffort: max")
        data = tomllib.loads(self.render("codex", source))
        self.assertEqual(data["model"], "gpt-x")
        self.assertEqual(data["model_reasoning_effort"], "xhigh")
        self.assertEqual(data["sandbox_mode"], "read-only")
        self.assertIn("## Skill Dependencies", data["developer_instructions"])
        self.assertIn("load each of these before starting work:\n\n- `alpha`", data["developer_instructions"])
        self.assertNotIn("model", tomllib.loads(self.render("codex")))

    def test_codex_multiline_edge_cases(self) -> None:
        for body in ('# T\n\nQuote " and """ and \\ backslash.\n', '# T\n\nEnds with a quote"\n'):
            with self.subTest(body=body):
                data = tomllib.loads(self.render("codex", SOURCE.replace(BODY, body)))
                self.assertTrue(data["developer_instructions"].startswith(body.rstrip("\n")))

    def test_cursor(self) -> None:
        text = self.render("cursor", SOURCE.replace("model: strong", "model: strong\neffort: high"))
        front = text.split("---\n")[1]
        self.assertIn("model: inherit\nreadonly: true\n", front)
        self.assertIn("# effort: high\n", front)
        self.assertIn("# tools: [Read, Grep, Bash]\n", front)
        self.assertIn("# skills: [alpha]\n", front)
        self.assertNotIn("color", text)
        self.assertIn("## Role\n\nYou are a sample agent.\n\n## Skill Dependencies\n", text)

    def test_hermes(self) -> None:
        text = self.render("hermes")
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("# Generated from"))
        data = {key: json.loads(value) for key, value in (line.split(": ", 1) for line in lines[1:])}
        self.assertEqual(set(data), {"description", "system_prompt"})
        self.assertIn("- Read-only: do not change files", data["system_prompt"])
        self.assertIn("- Skills: load `alpha` before starting work.", data["system_prompt"])
        self.assertTrue(data["system_prompt"].endswith(BODY))

    def test_skills_section_is_lint_shaped(self) -> None:
        section = gen.skills_section(["alpha"], ["beta"])
        self.assertEqual(section[0], "## Skill Dependencies")
        for index, line in enumerate(section):
            if line.startswith(("#", "- ")) and index + 1 < len(section):
                self.assertTrue(section[index + 1] == "" or section[index + 1].startswith("- "), line)
            self.assertLessEqual(line.count(". "), 0, line)

    def test_skills_section_placement(self) -> None:
        body = "# T\n\n## Role\n\n```text\n## Not a heading\n```\n\n## Next\n"
        result = gen.insert_skills_section(body, ["a"], [])
        self.assertLess(result.index("## Not a heading"), result.index("## Skill Dependencies"))
        self.assertLess(result.index("## Skill Dependencies"), result.index("## Next"))
        self.assertTrue(gen.insert_skills_section("# T\n\n## Role\n", [], ["b"]).endswith("- `b`\n"))
        with self.assertRaises(gen.SourceError):
            gen.insert_skills_section("# T\n\n## Skill Dependencies\n", ["a"], [])

    def test_hostile_description_stays_one_scalar(self) -> None:
        description = '"x: y # z --- [a]"'
        text = self.render("cursor", SOURCE.replace(
            "description: Does sample work. Use this agent when a sample is needed.", f"description: {description}"))
        self.assertIn('description: "x: y # z --- [a]"\n', text)


class OutputTest(TreeTestCase):
    def test_generates_every_tool_and_rebuilds_from_scratch(self) -> None:
        self.write()
        code, output = self.generate()
        self.assertEqual(code, 0)
        expected = {"claude/agents/sample.md", "codex/agents/sample.toml", "cursor/agents/sample.md",
                    "hermes/personalities/sample.yaml"}
        self.assertEqual({p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}, expected)
        (output / "codex/agents/stale.toml").write_text("old\n")
        self.generate()
        self.assertFalse((output / "codex/agents/stale.toml").exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".generated")], [])

    def test_exclude_skips_tools(self) -> None:
        self.replace("color: red", "color: red\nexclude: [hermes, cai]")
        _, output = self.generate()
        self.assertFalse((output / "hermes").exists())
        self.assertTrue((output / "claude/agents/sample.md").is_file())

    def test_invalid_source_leaves_previous_output(self) -> None:
        self.write()
        _, output = self.generate()
        before = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
        self.write(SOURCE.replace("schema: 1", "schema: 2"))
        code, _ = self.generate()
        self.assertEqual(code, 1)
        self.assertEqual({p: p.read_bytes() for p in output.rglob("*") if p.is_file()}, before)

    def test_output_that_is_a_symlink_is_refused(self) -> None:
        self.write()
        (self.root / "elsewhere").mkdir()
        (self.root / "generated").symlink_to(self.root / "elsewhere")
        code, _ = self.generate()
        self.assertEqual(code, 1)
        self.assertEqual(list((self.root / "elsewhere").iterdir()), [])


class RepositoryTest(unittest.TestCase):
    def test_repository_sources_generate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "generated"
            self.assertEqual(gen.main(["--root", str(REPO), "--output", str(output)]), 0)
            sources = {p.stem for p in (REPO / "agent_sources").glob("*.md")} - {"README"}
            self.assertEqual({p.stem for p in (output / "claude/agents").glob("*.md")}, sources)
            for path in (output / "codex/agents").glob("*.toml"):
                tomllib.loads(path.read_text())
            shutil.rmtree(output)


if __name__ == "__main__":
    unittest.main()
