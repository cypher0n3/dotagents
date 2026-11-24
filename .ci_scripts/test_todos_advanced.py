#!/usr/bin/env python3
"""Tests for advanced operations (ID rename, timestamps, assignee, filters, meta)."""

import argparse
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


class IdRenameTest(unittest.TestCase):
    """Test ID rename with dependency rewrite."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_rename_id_rewrites_dependencies(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
todos:
  - id: old-id
    title: Base
    status: done
    assignee:
      kind: human
  - id: dependent
    title: Depends on old-id
    status: pending
    assignee:
      kind: human
    depends_on:
      - old-id
"""
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(new_id="new-id")
        result = update_command.update_todo(path, "old-id", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        renamed = next(t for t in data["todos"] if t["id"] == "new-id")
        self.assertEqual(renamed["title"], "Base")

        dependent = next(t for t in data["todos"] if t["id"] == "dependent")
        self.assertIn("new-id", dependent["depends_on"])
        self.assertNotIn("old-id", dependent["depends_on"])

    def test_rename_id_collision_fails(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
todos:
  - id: task-1
    title: First
    status: pending
    assignee:
      kind: human
  - id: task-2
    title: Second
    status: pending
    assignee:
      kind: human
"""
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(new_id="task-2")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 1)


class TimestampTest(unittest.TestCase):
    """Test timestamp management."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_add_stamps_created(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text("todos: []", encoding="utf-8")

        args = argparse.Namespace(
            title="New task", id="task-1", status=None, priority=None, description=None,
            blocked_reason=None, assignee_kind=None, assignee_name=None, agent_type=None,
            requires_human_review=None, add_depends_on=None, add_tags=None, due=None,
            add_acceptance_criteria=None, parent=None,
        )
        result = basic_commands.add_todo(path, args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertIn("created", data["todos"][0])

    def test_update_stamps_meta_updated(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(priority="high")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertIn("updated", data["meta"])

    def test_reopen_removes_completed(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace("status: pending", "status: done\n    completed: 2026-11-20T10:00:00Z")
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(status="in_progress")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertNotIn("completed", data["todos"][0])


class AssigneeTest(unittest.TestCase):
    """Test assignee field operations."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_change_assignee_kind(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        args = argparse.Namespace(assignee_kind="agent", agent_type="coder")
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        assignee = data["todos"][0]["assignee"]
        self.assertEqual(assignee["kind"], "agent")
        self.assertEqual(assignee["agent_type"], "coder")

    def test_set_requires_human_review(self) -> None:
        path = self.root / "todos.yaml"
        content = MINIMAL.replace("kind: human", "kind: agent\n      agent_type: coder")
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(
            assignee_kind="agent", agent_type="coder", requires_human_review=True
        )
        result = update_command.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertTrue(data["todos"][0]["assignee"]["requires_human_review"])


class ListFiltersTest(unittest.TestCase):
    """Test list command filtering."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_filter_by_status(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
todos:
  - id: pending-1
    title: Pending
    status: pending
    assignee:
      kind: human
  - id: blocked-1
    title: Blocked
    status: blocked
    assignee:
      kind: human
"""
        path.write_text(content, encoding="utf-8")

        from io import StringIO
        import sys

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            list_show.list_todos(path, "all", status_filter="blocked")
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("blocked-1", output)
        self.assertNotIn("pending-1", output)

    def test_filter_by_priority(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
todos:
  - id: high-1
    title: High priority
    status: pending
    priority: high
    assignee:
      kind: human
  - id: low-1
    title: Low priority
    status: pending
    priority: low
    assignee:
      kind: human
"""
        path.write_text(content, encoding="utf-8")

        from io import StringIO
        import sys

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            list_show.list_todos(path, "all", priority_filter="high")
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("high-1", output)
        self.assertNotIn("low-1", output)

    def test_filter_by_tag(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
todos:
  - id: tagged
    title: Tagged task
    status: pending
    assignee:
      kind: human
    tags:
      - urgent
  - id: untagged
    title: Untagged task
    status: pending
    assignee:
      kind: human
"""
        path.write_text(content, encoding="utf-8")

        from io import StringIO
        import sys

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            list_show.list_todos(path, "all", tag_filter="urgent")
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("tagged", output)
        self.assertNotIn("untagged", output)


class DryRunTest(unittest.TestCase):
    """Test dry-run on done and start commands."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_done_dry_run(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        original = path.read_text()
        args = argparse.Namespace(status="done")
        result = update_command.update_todo(path, "task-1", args, dry_run=True)
        self.assertEqual(result, 0)
        self.assertEqual(path.read_text(), original)

    def test_start_dry_run(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL, encoding="utf-8")

        original = path.read_text()
        args = argparse.Namespace(status="in_progress")
        result = update_command.update_todo(path, "task-1", args, dry_run=True)
        self.assertEqual(result, 0)
        self.assertEqual(path.read_text(), original)


class MetaTest(unittest.TestCase):
    """Test meta command."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_meta_set_title(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text("todos: []", encoding="utf-8")

        args = argparse.Namespace(title="Project Title")
        result = advanced_commands.meta_command(path, args)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertEqual(data["meta"]["title"], "Project Title")

    def test_meta_clear_title(self) -> None:
        path = self.root / "todos.yaml"
        content = """---
meta:
  title: Old Title
todos: []
"""
        path.write_text(content, encoding="utf-8")

        args = argparse.Namespace(title="")
        result = advanced_commands.meta_command(path, args)
        self.assertEqual(result, 0)

        data = io_ops.load_yaml(path)
        self.assertNotIn("title", data.get("meta", {}))


if __name__ == "__main__":
    unittest.main()
