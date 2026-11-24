#!/usr/bin/env python3
"""Tests for task field edits: tags, criteria, files, due dates, assignees, and input validation."""

import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "task-management" / "scripts"))

from todos_lib import advanced_commands, basic_commands, io_ops, list_show, update_command  # noqa: E402

MINIMAL = """---
todos:
  - id: task-1
    title: Test task
    status: pending
    assignee:
      kind: human
"""


class TagsTest(unittest.TestCase):
    """Test tag operations."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_add_tags_on_create(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text("todos: []", encoding="utf-8")

        args = argparse.Namespace(
            title="Tagged task", id="task-1", status=None, priority=None, description=None,
            blocked_reason=None, assignee_kind=None, assignee_name=None, agent_type=None,
            requires_human_review=None, add_depends_on=None, add_tags=["urgent", "bug"],
            due=None, add_acceptance_criteria=None, parent=None,
        )
        result = basic_commands.add_todo(path, args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertEqual(data["todos"][0]["tags"], ["urgent", "bug"])

    def test_add_tag_to_existing(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(add_tags=["feature"])
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertIn("feature", data["todos"][0]["tags"])

    def test_remove_tag(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace("kind: human", "kind: human\n    tags:\n      - old\n      - keep")
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(remove_tags=["old"])
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertEqual(data["todos"][0]["tags"], ["keep"])

    def test_clear_tags(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace("kind: human", "kind: human\n    tags: [a, b]")
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(clear_tags=True)
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertNotIn("tags", data["todos"][0])


class DependenciesTest(unittest.TestCase):
    """Test dependency operations."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_add_dependency(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
todos:
  - id: base
    title: Base
    status: done
    assignee:
      kind: human
  - id: task-1
    title: Test
    status: pending
    assignee:
      kind: human
"""
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(add_depends_on=["base"])
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        task = next(t for t in data["todos"] if t["id"] == "task-1")
        self.assertIn("base", task["depends_on"])

    def test_remove_dependency(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace(
            "kind: human", "kind: human\n    depends_on:\n      - old\n      - keep"
        )
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(remove_depends_on=["old"])
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertEqual(data["todos"][0]["depends_on"], ["keep"])


class AcceptanceCriteriaTest(unittest.TestCase):
    """Test acceptance criteria operations."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_add_acceptance_criteria(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(add_acceptance_criteria=["Must pass tests"])
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertIn("Must pass tests", data["todos"][0]["acceptance_criteria"])


class FilesTest(unittest.TestCase):
    """Test file entry operations."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_add_file(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(add_file=["src/main.py:update"])
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        files = data["todos"][0]["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "src/main.py")
        self.assertEqual(files[0]["op"], "update")


class ScalarFieldsTest(unittest.TestCase):
    """Test scalar field operations."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_set_due_date(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(due="2026-12-31")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertIn("due", data["todos"][0])

    def test_clear_due_date(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace("kind: human", "kind: human\n    due: 2026-12-31")
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(due="")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertNotIn("due", data["todos"][0])

    def test_set_description(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(description="Detailed description")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertEqual(data["todos"][0]["description"], "Detailed description")

    def test_clear_description(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace("kind: human", "kind: human\n    description: Old text")
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(description="")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertNotIn("description", data["todos"][0])


class ValidationTest(unittest.TestCase):
    """Test that invalid input is rejected and leaves the file unchanged."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tempdir.name) / "todos.yaml"
        self.addCleanup(self._tempdir.cleanup)
        self.path.write_text(MINIMAL.replace("todos:", "todos:\n  - id: task-2\n    title: Other"), encoding="utf-8")

    def assert_rejected(self, args: argparse.Namespace) -> None:
        before = self.path.read_text(encoding="utf-8")
        self.assertEqual(update_command.update_todo(self.path, "task-1", args), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_rejects_malformed_due(self) -> None:
        self.assert_rejected(argparse.Namespace(due="tomorrow"))

    def test_rejects_impossible_due(self) -> None:
        self.assert_rejected(argparse.Namespace(due="2026-02-30"))

    def test_rejects_self_dependency(self) -> None:
        self.assert_rejected(argparse.Namespace(add_depends_on=["task-1"]))

    def test_rejects_unknown_dependency(self) -> None:
        self.assert_rejected(argparse.Namespace(add_depends_on=["ghost"]))

    def test_accepts_known_dependency(self) -> None:
        args = argparse.Namespace(add_depends_on=["task-2"])
        self.assertEqual(update_command.update_todo(self.path, "task-1", args), 0)
        self.assertEqual(io_ops.load_yaml(self.path)["todos"][1]["depends_on"], ["task-2"])

    def test_rejects_blocked_reason_with_other_status(self) -> None:
        self.assert_rejected(argparse.Namespace(status="pending", blocked_reason="waiting"))

    def test_blocked_reason_sets_blocked(self) -> None:
        args = argparse.Namespace(status=None, blocked_reason="waiting")
        self.assertEqual(update_command.update_todo(self.path, "task-1", args), 0)
        self.assertEqual(io_ops.load_yaml(self.path)["todos"][1]["status"], "blocked")

    def test_assignee_name_edits_current_assignee(self) -> None:
        args = argparse.Namespace(assignee_name="Bob")
        self.assertEqual(update_command.update_todo(self.path, "task-1", args), 0)
        self.assertEqual(io_ops.load_yaml(self.path)["todos"][1]["assignee"], {"kind": "human", "name": "Bob"})

    def test_rejects_assignee_name_without_assignee(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        args = argparse.Namespace(assignee_name="Bob")
        self.assertEqual(update_command.update_todo(self.path, "task-2", args), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_rejects_agent_type_on_human(self) -> None:
        self.assert_rejected(argparse.Namespace(assignee_kind="human", agent_type="coder"))

    def test_add_file_path_with_colon(self) -> None:
        args = argparse.Namespace(add_file=["C:\\src\\x.py:update"])
        self.assertEqual(update_command.update_todo(self.path, "task-1", args), 0)
        files = io_ops.load_yaml(self.path)["todos"][1]["files"]
        self.assertEqual(files, [{"path": "C:\\src\\x.py", "op": "update"}])

    def test_add_rejects_unknown_dependency(self) -> None:
        args = argparse.Namespace(title="New", id="task-3", add_depends_on=["ghost"], parent=None)
        before = self.path.read_text(encoding="utf-8")
        self.assertEqual(basic_commands.add_todo(self.path, args), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_meta_rejects_malformed_created(self) -> None:
        args = argparse.Namespace(show=False, title=None, created="yesterday")
        before = self.path.read_text(encoding="utf-8")
        self.assertEqual(advanced_commands.meta_command(self.path, args), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_remove_and_move_stamp_updated(self) -> None:
        self.assertEqual(advanced_commands.move_todo(self.path, "task-2", "task-1"), 0)
        self.assertIn("updated", io_ops.load_yaml(self.path)["meta"])
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.assertEqual(basic_commands.remove_todo(self.path, "task-1"), 0)
        self.assertIn("updated", io_ops.load_yaml(self.path)["meta"])


class FullCrudTest(unittest.TestCase):
    """Test file creation and the remaining field edits."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tempdir.name) / "todos.yaml"
        self.addCleanup(self._tempdir.cleanup)

    def update(self, **kwargs: object) -> int:
        return update_command.update_todo(self.path, "task-1", argparse.Namespace(**kwargs))

    def task(self) -> dict:
        return io_ops.load_yaml(self.path)["todos"][0]

    def test_init_creates_valid_file(self) -> None:
        self.assertEqual(basic_commands.init_file(self.path, "Plan"), 0)
        data = io_ops.load_yaml(self.path)
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["meta"]["title"], "Plan")
        self.assertIn("created", data["meta"])

    def test_init_refuses_existing_file(self) -> None:
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.assertEqual(basic_commands.init_file(self.path, None), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), MINIMAL)

    def test_add_with_files_and_reason(self) -> None:
        basic_commands.init_file(self.path, None)
        args = argparse.Namespace(
            title="T", id="task-1", parent=None, add_file=["src/a.py:update"],
            file_reason=["src/a.py=Fix bug"],
        )
        self.assertEqual(basic_commands.add_todo(self.path, args), 0)
        self.assertEqual(self.task()["files"], [{"path": "src/a.py", "op": "update", "reason": "Fix bug"}])

    def test_edit_and_clear_file_entry_fields(self) -> None:
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.assertEqual(self.update(add_file=["a.py:update"], file_renamed_to=["a.py=b.py"]), 0)
        self.assertEqual(self.update(file_op=["a.py=delete"], file_renamed_to=["a.py="]), 0)
        self.assertEqual(self.task()["files"], [{"path": "a.py", "op": "delete"}])

    def test_file_modifier_rejects_unknown_path(self) -> None:
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.assertEqual(self.update(file_reason=["missing.py=x"]), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), MINIMAL)

    def test_clear_priority(self) -> None:
        content = MINIMAL.replace("status: pending", "status: pending\n    priority: high")
        self.path.write_text(content, encoding="utf-8")
        self.assertEqual(self.update(clear_priority=True), 0)
        self.assertNotIn("priority", self.task())

    def test_set_created(self) -> None:
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.assertEqual(self.update(created="2026-01-02T03:04:05Z"), 0)
        self.assertEqual(self.update(created="not a time"), 1)

    def test_unset_requires_human_review(self) -> None:
        self.path.write_text(MINIMAL, encoding="utf-8")
        self.update(assignee_kind="agent", agent_type="coder", requires_human_review=True)
        self.assertEqual(self.update(requires_human_review=False), 0)
        self.assertEqual(self.task()["assignee"], {"kind": "agent", "agent_type": "coder"})

    def test_list_done_tasks(self) -> None:
        self.path.write_text(MINIMAL.replace("status: pending", "status: done"), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            list_show.list_todos(self.path, "all")
        self.assertNotIn("task-1", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            list_show.list_todos(self.path, "all", status_filter="done")
        self.assertIn("task-1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
