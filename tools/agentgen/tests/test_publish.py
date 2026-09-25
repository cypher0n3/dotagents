"""Tests for checking and publishing generated files."""

from __future__ import annotations

import os
import unittest

from agentgen import yamlio

from tests.helpers import RepoTestCase

OUTPUTS = [
    "agents/sample.md",
    "generated/cai/personas/sample.md",
    "generated/codex/agents/sample.toml",
    "generated/cursor/agents/sample.md",
    "generated/hermes/personalities/sample.yaml",
]


class PublishTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_role()

    def generate(self, *args: str) -> tuple[int, str, str]:
        return self.run_cli(*args)

    def snapshot(self) -> dict[str, tuple[bytes, int]]:
        result = {}
        for base in ("agents", "generated"):
            for path in sorted((self.root / base).rglob("*")):
                if path.is_file():
                    result[path.relative_to(self.root).as_posix()] = (path.read_bytes(), path.stat().st_mtime_ns)
        return result

    def test_first_run_creates_every_output_and_manifest(self) -> None:
        code, out, _ = self.generate()
        self.assertEqual(code, 0)
        for relative in OUTPUTS:
            self.assertTrue((self.root / relative).is_file(), relative)
            self.assertIn(f"created: {relative}", out)
        manifest = yamlio.loads(self.read("generated/manifest.yaml"))
        self.assertEqual([entry["path"] for entry in manifest["outputs"]], OUTPUTS)
        self.assertEqual(self.read("agents/README.md"), "# Agent Index\n")

    def test_rerun_writes_nothing(self) -> None:
        self.generate()
        before = self.snapshot()
        code, out, _ = self.generate()
        self.assertEqual(code, 0)
        self.assertIn("outputs are current", out)
        self.assertEqual(self.snapshot(), before)

    def test_output_is_byte_identical_across_runs(self) -> None:
        self.generate()
        first = {key: value[0] for key, value in self.snapshot().items()}
        for relative in first:
            (self.root / relative).unlink()
        (self.root / "agents/README.md").write_text("# Agent Index\n")
        self.generate("--accept-source")
        self.assertEqual({key: value[0] for key, value in self.snapshot().items()}, first)

    def test_source_change_updates_outputs(self) -> None:
        self.generate()
        body = self.root / "agent_sources/prompts/sample.md"
        body.write_text(body.read_text() + "- A new rule.\n")
        code, out, _ = self.generate()
        self.assertEqual(code, 0)
        self.assertIn("updated: agents/sample.md", out)
        self.assertTrue(self.read("agents/sample.md").endswith("- A new rule.\n"))

    def test_hand_edit_is_refused_and_nothing_is_written(self) -> None:
        self.generate()
        (self.root / "agents/sample.md").write_text("hand edit\n")
        body = self.root / "agent_sources/prompts/sample.md"
        body.write_text(body.read_text() + "- A new rule.\n")
        before = self.snapshot()
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("agents/sample.md: edited by hand", err)
        self.assertIn("--accept-source", err)
        self.assertEqual(self.snapshot(), before)

    def test_accept_source_overwrites_hand_edit(self) -> None:
        self.generate()
        (self.root / "agents/sample.md").write_text("hand edit\n")
        code, out, _ = self.generate("--accept-source")
        self.assertEqual(code, 0)
        self.assertIn("overwrote hand edit: agents/sample.md", out)
        self.assertTrue(self.read("agents/sample.md").startswith("---\nname: sample\n"))

    def test_accept_source_recovers_from_conflicted_manifest(self) -> None:
        self.generate()
        (self.root / "generated/manifest.yaml").write_text("<<<<<<< ours\nbroken: [\n")
        (self.root / "agents/sample.md").write_text("<<<<<<< ours\n")
        self.assertEqual(self.generate()[0], 1)
        code, _, _ = self.generate("--accept-source")
        self.assertEqual(code, 0)
        self.assertEqual(self.generate("--check")[0], 0)

    def test_file_matching_new_rendering_is_not_a_hand_edit(self) -> None:
        self.generate()
        body = self.root / "agent_sources/prompts/sample.md"
        body.write_text(body.read_text() + "- A new rule.\n")
        self.generate()
        manifest = self.root / "generated/manifest.yaml"
        new_manifest = manifest.read_bytes()
        # Simulate a run interrupted before the manifest moved into place.
        body.write_text(body.read_text().replace("- A new rule.\n", "- Another rule.\n"))
        self.generate()
        manifest.write_bytes(new_manifest)
        self.assertEqual(self.generate()[0], 0)

    def test_unlisted_file_at_managed_path_is_refused(self) -> None:
        (self.root / "agents/sample.md").write_text("my own agent\n")
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("agents/sample.md: not listed in generated/manifest.yaml", err)
        self.assertEqual(self.read("agents/sample.md"), "my own agent\n")

    def test_unlisted_agent_is_left_alone(self) -> None:
        (self.root / "agents/local.md").write_text("mine\n")
        self.generate()
        self.assertEqual(self.read("agents/local.md"), "mine\n")

    def test_removed_role_removes_its_outputs(self) -> None:
        self.generate()
        self.write_role("other")
        (self.root / "agent_sources/roles/sample.yaml").unlink()
        (self.root / "agent_sources/prompts/sample.md").unlink()
        code, out, _ = self.generate()
        self.assertEqual(code, 0)
        for relative in OUTPUTS:
            self.assertFalse((self.root / relative).exists(), relative)
            self.assertIn(f"removed: {relative}", out)

    def test_hand_edited_obsolete_file_is_refused(self) -> None:
        self.generate()
        self.write_role("other")
        (self.root / "agent_sources/roles/sample.yaml").unlink()
        (self.root / "agents/sample.md").write_text("hand edit\n")
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("agents/sample.md: no longer generated, but edited by hand", err)

    def test_symlinked_output_is_refused(self) -> None:
        (self.root / "elsewhere.md").write_text("x\n")
        (self.root / "agents/sample.md").symlink_to(self.root / "elsewhere.md")
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("is not a regular file", err)
        self.assertEqual(self.read("elsewhere.md"), "x\n")

    def test_symlinked_output_directory_is_refused(self) -> None:
        (self.root / "outside").mkdir()
        (self.root / "generated").mkdir()
        (self.root / "generated/cursor").symlink_to(self.root / "outside")
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("passes through a symlink", err)
        self.assertEqual(list((self.root / "outside").iterdir()), [])

    def test_case_folded_collision_is_refused(self) -> None:
        (self.root / "agents/Sample.md").write_text("mine\n")
        if (self.root / "agents/sample.md").exists():
            self.skipTest("case-insensitive filesystem")
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("collides with existing", err)

    def test_manifest_path_escape_is_refused(self) -> None:
        self.generate()
        manifest = self.root / "generated/manifest.yaml"
        manifest.write_text(manifest.read_text().replace("- path: agents/sample.md", "- path: ../victim.md"))
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("not a clean relative path", err)

    def test_check_mode_reports_and_never_writes(self) -> None:
        code, _, err = self.generate("--check")
        self.assertEqual(code, 1)
        self.assertIn("missing: agents/sample.md", err)
        self.assertFalse((self.root / "generated").exists())
        self.generate()
        self.assertEqual(self.generate("--check")[0], 0)
        (self.root / "agents/sample.md").write_text("hand edit\n")
        before = self.snapshot()
        code, _, err = self.generate("--check")
        self.assertEqual(code, 1)
        self.assertIn("hand edited: agents/sample.md", err)
        self.assertEqual(self.snapshot(), before)

    def test_check_mode_reports_obsolete_and_manifest_drift(self) -> None:
        self.generate()
        self.write_role("other")
        (self.root / "agent_sources/roles/sample.yaml").unlink()
        code, _, err = self.generate("--check")
        self.assertEqual(code, 1)
        self.assertIn("obsolete: agents/sample.md", err)
        self.assertIn("stale: generated/manifest.yaml", err)

    def test_validation_error_writes_nothing(self) -> None:
        self.generate()
        before = self.snapshot()
        self.write_role("broken", targets="[nowhere]")
        code, _, err = self.generate()
        self.assertEqual(code, 1)
        self.assertIn("nothing was written", err)
        self.assertEqual(self.snapshot(), before)

    def test_no_temporary_files_remain(self) -> None:
        self.generate()
        leftovers = [path for path in self.root.rglob("*agentgen-tmp*")]
        self.assertEqual(leftovers, [])

    def test_new_files_follow_umask(self) -> None:
        self.generate()
        mode = (self.root / "agents/sample.md").stat().st_mode & 0o777
        umask = os.umask(0)
        os.umask(umask)
        self.assertEqual(mode, 0o666 & ~umask)


if __name__ == "__main__":
    unittest.main()
