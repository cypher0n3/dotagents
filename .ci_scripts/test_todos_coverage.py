#!/usr/bin/env python3
"""Tests for task-management CLI paths not covered elsewhere: show output, errors, and failures."""

import argparse
import contextlib
import importlib
import importlib.util
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parent.parent / "skills" / "task-management" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import todos  # noqa: E402
from todos_lib import (  # noqa: E402
    advanced_commands, basic_commands, io_ops, list_show, models, mutations, update_command,
)

FIXTURE = """\
meta:
  title: Fixture
todos:
  - id: parent
    title: Parent
    status: pending
    priority: high
    description: Parent task
    tags: [a]
    due: 2026-12-01
    acceptance_criteria: [Works]
    assignee: {kind: agent, agent_type: coder}
    files:
      - {path: src/a.py, op: update, renamed_to: src/b.py, reason: Rename}
      - {path: src/c.py, op: read}
    subtasks:
      - id: child
        title: Child
        status: blocked
        blocked_reason: Waiting
        depends_on: [other, keep]
      - id: done-child
        title: Done child
        status: done
  - id: other
    title: Other
    status: done
    created: 2026-11-01T00:00:00Z
    completed: 2026-11-02T00:00:00Z
  - id: keep
    title: Keep
    depends_on: [parent]
  - title: No id task
    status: done
"""


class CliTestCase(unittest.TestCase):
    """Base class: a fixture file and a helper that runs the CLI entry point."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.path = Path(self._tempdir.name) / "todos.yaml"
        self.path.write_text(FIXTURE, encoding="utf-8")

    def cli(self, *argv: str, file: bool = True) -> tuple[int, str, str]:
        """Run todos.main with argv; return (exit code, stdout, stderr)."""
        args = ["todos.py", *argv] + (["--file", str(self.path)] if file else [])
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = todos.main()
        return code, out.getvalue(), err.getvalue()

    def data(self) -> dict:
        """Load the fixture file."""
        return io_ops.load_yaml(self.path)

    def assert_unchanged(self, code: int) -> None:
        """Assert a failed command left the file as it was."""
        self.assertEqual(code, 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FIXTURE)


class EntryPointTest(CliTestCase):
    """Test the entry point and its shortcuts."""

    def test_done_and_start(self) -> None:
        self.assertEqual(self.cli("start", "keep")[0], 0)
        self.assertEqual(models.find_task_by_id(self.data()["todos"], "keep")[0]["status"], "in_progress")
        self.assertEqual(self.cli("done", "keep", "--dry-run")[0], 0)
        self.assertEqual(self.cli("done", "keep")[0], 0)
        task = models.find_task_by_id(self.data()["todos"], "keep")[0]
        self.assertEqual(task["status"], "done")
        self.assertIn("completed", task)

    def test_default_path_from_environment(self) -> None:
        with mock.patch.dict(os.environ, {"TODOS_FILE": str(self.path)}):
            code, out, _ = self.cli("show", "keep", file=False)
        self.assertEqual(code, 0)
        self.assertIn("Keep", out)

    def test_default_path_without_environment(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(io_ops.get_default_path(), Path("todos.yaml"))

    def test_run_as_script(self) -> None:
        argv = ["todos.py", "show", "keep", "--file", str(self.path)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(str(SCRIPTS / "todos.py"), run_name="__main__")
        self.assertEqual(raised.exception.code, 0)

    def test_import_as_package_module(self) -> None:
        with mock.patch.object(sys, "path", [str(SCRIPTS.parent), *sys.path]):
            module = importlib.import_module("scripts.todos")
        self.addCleanup(sys.modules.pop, "scripts.todos", None)
        self.addCleanup(sys.modules.pop, "scripts", None)
        self.assertEqual(module.__package__, "scripts")

    def test_missing_file_for_every_command(self) -> None:
        self.path.unlink()
        for argv in (["list"], ["show", "x"], ["add", "T"], ["update", "x", "--title", "T"], ["remove", "x"],
                     ["move", "x", "--root"], ["clean"], ["meta", "--show"]):
            code, _, err = self.cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("File not found", err)


class ShowTest(CliTestCase):
    """Test that show prints every set field."""

    def test_show_prints_all_fields(self) -> None:
        code, out, _ = self.cli("show", "parent")
        self.assertEqual(code, 0)
        for text in ("Description: Parent task", "Tags: a", "Due: 2026-12-01", "Acceptance criteria:",
                     "- Works", "src/a.py (update) -> src/b.py: Rename", "src/c.py (read)",
                     "BLOCKED: Waiting", "Depends on: other, keep", "agent:coder"):
            self.assertIn(text, out)

    def test_show_prints_timestamps(self) -> None:
        _, out, _ = self.cli("show", "other")
        self.assertIn("Created: 2026-11-01T00:00:00+00:00", out)
        self.assertIn("Completed: 2026-11-02T00:00:00+00:00", out)

    def test_show_review_flag_and_unparseable_completed(self) -> None:
        self.cli("update", "parent", "--requires-human-review")
        data = self.data()
        data["todos"][0]["completed"] = "someday"
        io_ops.dump_yaml(data, self.path)
        _, out, _ = self.cli("show", "parent")
        self.assertIn("Requires human review: Yes", out)
        self.assertNotIn("Completed:", out)

    def test_show_unknown_task(self) -> None:
        code, out, _ = self.cli("show", "ghost")
        self.assertEqual(code, 1)
        self.assertIn("not found", out)


class ListTest(CliTestCase):
    """Test list filters and edge cases."""

    def test_status_filter_finds_done_subtasks(self) -> None:
        _, out, _ = self.cli("list", "--status", "done")
        self.assertIn("done-child", out)
        self.assertIn("other", out)
        self.assertNotIn("keep", out)

    def test_no_matches(self) -> None:
        _, out, _ = self.cli("list", "human", "--priority", "low", "--tag", "zzz", "--status", "pending")
        self.assertIn("No todos found (assignee=human, status=pending, priority=low, tag=zzz)", out)

    def test_skips_task_without_title(self) -> None:
        self.path.write_text("todos:\n  - id: untitled\n  - id: ok\n    title: OK\n", encoding="utf-8")
        code, out, err = self.cli("list")
        self.assertEqual(code, 0)
        self.assertIn("Skipping todo missing required field", err)
        self.assertIn("ok", out)


class MoveTest(CliTestCase):
    """Test move paths."""

    def test_argument_errors(self) -> None:
        self.assert_unchanged(self.cli("move", "keep")[0])
        self.assert_unchanged(self.cli("move", "keep", "--root", "--parent", "parent")[0])
        self.assert_unchanged(self.cli("move", "ghost", "--root")[0])
        self.assert_unchanged(self.cli("move", "keep", "--parent", "ghost")[0])

    def test_no_ops_and_dry_runs(self) -> None:
        for argv in (["move", "keep", "--root"], ["move", "child", "--parent", "parent"],
                     ["move", "child", "--root", "--dry-run"], ["move", "keep", "--parent", "parent", "--dry-run"]):
            self.assertEqual(self.cli(*argv)[0], 0, argv)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FIXTURE)

    def test_move_into_parent_with_subtasks_and_back(self) -> None:
        self.assertEqual(self.cli("move", "keep", "--parent", "parent")[0], 0)
        self.assertEqual(models.find_task_by_id(self.data()["todos"], "keep")[1],
                         self.data()["todos"][0]["subtasks"])
        self.assertEqual(self.cli("move", "done-child", "--root")[0], 0)
        self.assertEqual(self.cli("move", "child", "--parent", "other")[0], 0)
        self.assertEqual(self.cli("move", "keep", "--root")[0], 0)
        self.assertNotIn("subtasks", self.data()["todos"][0])


class CleanTest(CliTestCase):
    """Test clean with subtasks and dependency pruning."""

    def test_clean_prunes_done_tasks_and_dependencies(self) -> None:
        code, out, _ = self.cli("clean")
        self.assertEqual(code, 0)
        self.assertIn("child: removed other", out)
        todos_list = self.data()["todos"]
        self.assertEqual([t.get("id") for t in todos_list], ["parent", "keep"])
        self.assertEqual([t["id"] for t in todos_list[0]["subtasks"]], ["child"])
        self.assertEqual(todos_list[0]["subtasks"][0]["depends_on"], ["keep"])

    def test_clean_drops_emptied_dependency_list(self) -> None:
        self.assertEqual(self.cli("update", "child", "--remove-depends-on", "keep")[0], 0)
        self.assertEqual(self.cli("clean")[0], 0)
        self.assertNotIn("depends_on", models.find_task_by_id(self.data()["todos"], "child")[0])

    def test_clean_removes_emptied_subtasks(self) -> None:
        self.path.write_text(
            "todos:\n  - id: p\n    title: P\n    subtasks:\n      - id: c\n        title: C\n        status: done\n"
            "  - id: d\n    title: D\n    status: done\n    subtasks:\n      - id: e\n        title: E\n",
            encoding="utf-8",
        )
        self.assertEqual(self.cli("clean")[0], 0)
        todos_list = self.data()["todos"]
        self.assertNotIn("subtasks", todos_list[0])
        self.assertEqual(todos_list[1]["subtasks"][0]["id"], "e")


class MetaTest(CliTestCase):
    """Test the meta command."""

    def test_show(self) -> None:
        _, out, _ = self.cli("meta", "--show")
        self.assertIn("title: Fixture", out)
        self.path.write_text("todos: []\n", encoding="utf-8")
        _, out, _ = self.cli("meta", "--show")
        self.assertIn("No meta section", out)

    def test_set_and_clear(self) -> None:
        self.assertEqual(self.cli("meta", "--created", "2026-01-01T00:00:00Z")[0], 0)
        self.assertEqual(self.cli("meta", "--title", "")[0], 0)
        self.assertNotIn("title", self.data()["meta"])
        _, out, _ = self.cli("meta", "--title", "")
        self.assertIn("No action specified", out)
        self.path.write_text("todos: []\n", encoding="utf-8")
        self.assertEqual(self.cli("meta", "--title", "New")[0], 0)
        self.assertEqual(self.data()["meta"]["title"], "New")

    def test_no_action(self) -> None:
        _, out, _ = self.cli("meta")
        self.assertIn("No action specified", out)


class AddRemoveTest(CliTestCase):
    """Test add and remove paths."""

    def test_add_to_unknown_parent(self) -> None:
        self.assert_unchanged(self.cli("add", "T", "--parent", "ghost")[0])

    def test_add_to_parent_with_subtasks(self) -> None:
        self.assertEqual(self.cli("add", "Sub", "--parent", "parent")[0], 0)
        self.assertEqual(self.data()["todos"][0]["subtasks"][-1]["id"], "sub")

    def test_generated_id_avoids_collision(self) -> None:
        self.assertEqual(self.cli("add", "Keep")[0], 0)
        self.assertEqual(self.data()["todos"][-1]["id"], "keep-1")
        self.assertEqual(models.generate_id("!!!", set()), "task")

    def test_remove_paths(self) -> None:
        self.assert_unchanged(self.cli("remove", "ghost")[0])
        _, out, _ = self.cli("remove", "parent", "--recursive", "--dry-run")
        self.assertIn("and 2 subtask(s)", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FIXTURE)
        code, out, _ = self.cli("remove", "parent", "--recursive")
        self.assertEqual(code, 0)
        self.assertIn("and 2 subtask(s)", out)
        self.assertNotIn("depends_on", models.find_task_by_id(self.data()["todos"], "keep")[0])

    def test_remove_prunes_nested_dependencies(self) -> None:
        self.assertEqual(self.cli("remove", "other")[0], 0)
        self.assertEqual(models.find_task_by_id(self.data()["todos"], "child")[0]["depends_on"], ["keep"])


class UpdateTest(CliTestCase):
    """Test update paths and rejections not covered elsewhere."""

    def task(self, task_id: str = "parent") -> dict:
        """Return a task from the fixture file."""
        return models.find_task_by_id(self.data()["todos"], task_id)[0]

    def test_no_updates(self) -> None:
        _, out, _ = self.cli("update", "keep")
        self.assertIn("No updates specified", out)
        self.assertEqual(self.cli("update", "ghost", "--title", "T")[0], 1)

    def test_remove_and_clear_files(self) -> None:
        self.assertEqual(self.cli("update", "parent", "--remove-file", "src/c.py")[0], 0)
        self.assertEqual([f["path"] for f in self.task()["files"]], ["src/a.py"])
        self.assertEqual(self.cli("update", "parent", "--clear-files", "--add-file", "x.py:create")[0], 0)
        self.assertEqual(self.task()["files"], [{"path": "x.py", "op": "create"}])
        self.assertEqual(self.cli("update", "parent", "--remove-file", "x.py")[0], 0)
        self.assertNotIn("files", self.task())

    def test_edit_second_file_entry_and_no_op_clear(self) -> None:
        self.assertEqual(self.cli("update", "parent", "--file-reason", "src/c.py=Read it")[0], 0)
        self.assertEqual(self.task()["files"][1]["reason"], "Read it")
        _, out, _ = self.cli("update", "parent", "--file-renamed-to", "src/c.py=")
        self.assertIn("No updates specified", out)

    def test_add_existing_list_item_is_kept_once(self) -> None:
        self.assertEqual(self.cli("update", "parent", "--add-tags", "a", "b")[0], 0)
        self.assertEqual(self.task()["tags"], ["a", "b"])

    def test_file_rejections(self) -> None:
        for argv in (["--add-file", "no-op"], ["--add-file", "a.py:move"], ["--add-file", "src/a.py:read"],
                     ["--file-reason", "no-equals"], ["--file-op", "src/a.py=move"]):
            self.assert_unchanged(self.cli("update", "parent", *argv)[0])

    def test_assignee_rejections(self) -> None:
        agent_with_name = ["--assignee-kind", "agent", "--agent-type", "x", "--assignee-name", "Bob"]
        for argv in (["--assignee-kind", "agent"], agent_with_name):
            self.assert_unchanged(self.cli("update", "keep", *argv)[0])
        self.assert_unchanged(self.cli("update", "parent", "--assignee-name", "Bob")[0])

    def test_assignee_edits(self) -> None:
        self.assertEqual(self.cli("update", "keep", "--assignee-kind", "human", "--assignee-name", "Ann")[0], 0)
        self.assertEqual(self.cli("update", "keep", "--assignee-name", "")[0], 0)
        self.assertEqual(self.task("keep")["assignee"], {"kind": "human"})
        self.assertEqual(self.cli("update", "keep", "--clear-assignee")[0], 0)
        self.assertNotIn("assignee", self.task("keep"))
        _, out, _ = self.cli("update", "keep", "--clear-assignee")
        self.assertIn("No updates specified", out)

    def test_clear_missing_field_is_no_op(self) -> None:
        _, out, _ = self.cli("update", "keep", "--description", "")
        self.assertIn("No updates specified", out)

    def test_list_field_remove_all_and_clear(self) -> None:
        self.assertEqual(self.cli("update", "parent", "--remove-tags", "a")[0], 0)
        self.assertNotIn("tags", self.task())
        self.assertEqual(self.cli("update", "parent", "--clear-acceptance-criteria")[0], 0)
        self.assertNotIn("acceptance_criteria", self.task())

    def test_rename_rewrites_nested_dependencies(self) -> None:
        self.assertEqual(self.cli("update", "other", "--new-id", "renamed")[0], 0)
        self.assertEqual(self.task("child")["depends_on"], ["renamed", "keep"])

    def test_rename_rejects_existing_id(self) -> None:
        self.assert_unchanged(self.cli("update", "keep", "--new-id", "parent")[0])


class WriteFailureTest(CliTestCase):
    """Test that commands report a failed write and print no success message."""

    def test_commands_return_write_failure(self) -> None:
        cases = (
            (basic_commands, ["add", "T"]), (basic_commands, ["remove", "keep"]),
            (update_command, ["update", "keep", "--title", "T"]), (advanced_commands, ["move", "child", "--root"]),
            (advanced_commands, ["clean"]), (advanced_commands, ["meta", "--title", "T"]),
        )
        for module, argv in cases:
            with mock.patch.object(module, "write_data", return_value=1):
                code, out, _ = self.cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertNotRegex(out, r"^(Added|Removed|Updated|Moved)", argv)

    def test_init_write_failure(self) -> None:
        new = self.path.with_name("new.yaml")
        with mock.patch.object(basic_commands, "write_data", return_value=1):
            self.assertEqual(basic_commands.init_file(new, None), 1)

    def test_atomic_write_failure_keeps_original(self) -> None:
        err = io.StringIO()
        with mock.patch.object(io_ops, "dump_yaml", side_effect=OSError("disk full")), contextlib.redirect_stderr(err):
            self.assertEqual(io_ops.write_data(self.data(), self.path), 1)
        self.assertIn("disk full", err.getvalue())
        self.assertEqual(self.path.read_text(encoding="utf-8"), FIXTURE)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["todos.yaml"])

    def test_write_without_validation(self) -> None:
        self.assertEqual(io_ops.write_data({"todos": [{"id": "x"}]}, self.path, validate_after=False), 0)
        self.assertEqual(self.data()["todos"], [{"id": "x"}])


class MissingDependencyTest(unittest.TestCase):
    """Test the messages shown when a required package is missing."""

    def test_missing_packages_exit_with_install_hint(self) -> None:
        for missing in ("ruamel.yaml", "jsonschema"):
            io_ops_path = SCRIPTS / "todos_lib" / "io_ops.py"
            spec = importlib.util.spec_from_file_location(f"io_ops_probe_{missing}", io_ops_path)
            module = importlib.util.module_from_spec(spec)
            err = io.StringIO()
            with mock.patch.dict(sys.modules, {missing: None}), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit):
                    spec.loader.exec_module(module)
            self.assertIn(f"{missing} is required", err.getvalue())


class HelperTest(unittest.TestCase):
    """Test small helpers directly."""

    def test_parse_datetime_rejects_other_values(self) -> None:
        self.assertIsNone(models.parse_datetime(42))
        self.assertIsNone(models.parse_datetime("not a date"))

    def test_collect_ids_skips_tasks_without_id(self) -> None:
        tasks = [{"title": "x", "subtasks": [{"id": "a", "title": "a"}]}]
        self.assertEqual(models.collect_all_ids(tasks), {"a"})

    def test_set_or_clear_missing_key(self) -> None:
        target: dict = {}
        self.assertIsNone(mutations.set_or_clear(target, "k", ""))

    def test_build_assignee_without_flags(self) -> None:
        self.assertIsNone(mutations.build_assignee(argparse.Namespace(), {"kind": "human"}))

    def test_list_without_status_skips_closed_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "todos.yaml"
            path.write_text("todos:\n  - id: p\n    title: P\n    status: done\n    subtasks:\n"
                            "      - id: c\n        title: C\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                list_show.list_todos(path, "all")
            self.assertIn("No open todos found", out.getvalue())


if __name__ == "__main__":
    unittest.main()
