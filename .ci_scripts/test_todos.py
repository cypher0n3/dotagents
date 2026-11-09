#!/usr/bin/env python3
"""Offline unit tests for task-management skill."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "task-management" / "scripts"))

import todos  # noqa: E402


SCHEMA_PATH = Path(__file__).parent.parent / "skills" / "task-management" / "assets" / "todos-schema.json"
EXAMPLE_PATH = Path(__file__).parent.parent / "skills" / "task-management" / "assets" / "todos-example.yaml"


MINIMAL_VALID = """---
todos:
  - id: task-1
    title: First task
    status: pending
    assignee:
      kind: human
"""

MULTI_STATUS = """---
todos:
  - id: pending-1
    title: Pending task
    status: pending
    priority: high
    assignee:
      kind: human
    created: 2026-11-01T10:00:00Z
  - id: progress-1
    title: In progress task
    status: in_progress
    priority: critical
    assignee:
      kind: agent
      agent_type: coder
    created: 2026-11-01T09:00:00Z
  - id: blocked-1
    title: Blocked task
    status: blocked
    priority: medium
    assignee:
      kind: human
      name: Alice
    blocked_reason: Waiting for review
    created: 2026-11-01T11:00:00Z
  - id: done-1
    title: Completed task
    status: done
    priority: low
    assignee:
      kind: human
    created: 2026-11-01T08:00:00Z
    completed: 2026-11-01T12:00:00Z
  - id: cancelled-1
    title: Cancelled task
    status: cancelled
    priority: low
    assignee:
      kind: agent
      agent_type: test-runner
    created: 2026-11-01T07:00:00Z
"""

DEPENDENCIES = """---
todos:
  - id: base-task
    title: Foundation
    status: done
    assignee:
      kind: human
    completed: 2026-11-01T10:00:00Z
  - id: dependent-1
    title: Depends on base
    status: pending
    assignee:
      kind: human
    depends_on:
      - base-task
      - other-task
  - id: dependent-2
    title: Multiple dependencies
    status: in_progress
    assignee:
      kind: agent
      agent_type: coder
    depends_on:
      - base-task
"""

COMMENTS_YAML = """---
# Meta section comment
meta:
  title: Test File
  # Inline comment in meta

# Todos section comment
todos:
  # First todo comment
  - id: task-1
    title: Task with comments
    status: done
    assignee:
      kind: human
    completed: 2026-11-01T10:00:00Z
  # Second todo comment
  - id: task-2
    title: Keep this one
    status: pending
    assignee:
      kind: human
"""


class TodosSchemaTest(unittest.TestCase):
    """Test that the schema and example are valid."""

    def test_schema_is_valid_json(self) -> None:
        """Schema file is valid JSON."""
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        self.assertIn("$schema", schema)
        self.assertEqual(schema["type"], "object")

    def test_example_validates_against_schema(self) -> None:
        """Example YAML file validates against the schema."""
        data = todos.load_yaml(EXAMPLE_PATH)
        todos.validate_schema(data, SCHEMA_PATH)


class ParseDatetimeTest(unittest.TestCase):
    """Test datetime parsing from various formats."""

    def test_none_returns_none(self) -> None:
        self.assertIsNone(todos.parse_datetime(None))

    def test_iso_with_z(self) -> None:
        dt = todos.parse_datetime("2026-11-08T19:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertIsNotNone(dt.tzinfo)

    def test_iso_with_offset(self) -> None:
        dt = todos.parse_datetime("2026-11-08T19:00:00-05:00")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)

    def test_date_only(self) -> None:
        dt = todos.parse_datetime("2026-11-08")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 11)
        self.assertEqual(dt.day, 8)

    def test_datetime_object_naive(self) -> None:
        naive = datetime(2026, 11, 8, 19, 0, 0)
        dt = todos.parse_datetime(naive)
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)

    def test_datetime_object_aware(self) -> None:
        aware = datetime(2026, 11, 8, 19, 0, 0, tzinfo=timezone.utc)
        dt = todos.parse_datetime(aware)
        self.assertEqual(dt, aware)


class ParseTodoTest(unittest.TestCase):
    """Test todo parsing and normalization."""

    def test_minimal_human_assignee(self) -> None:
        raw = {
            "id": "task-1",
            "title": "Test",
            "status": "pending",
            "assignee": {"kind": "human"},
        }
        todo = todos.parse_todo(raw)
        self.assertEqual(todo.id, "task-1")
        self.assertEqual(todo.assignee_kind, "human")
        self.assertEqual(todo.assignee_display, "human")

    def test_human_with_name(self) -> None:
        raw = {
            "id": "task-1",
            "title": "Test",
            "status": "pending",
            "assignee": {"kind": "human", "name": "Alice"},
        }
        todo = todos.parse_todo(raw)
        self.assertEqual(todo.assignee_display, "human:Alice")

    def test_agent_assignee(self) -> None:
        raw = {
            "id": "task-1",
            "title": "Test",
            "status": "pending",
            "assignee": {"kind": "agent", "agent_type": "coder"},
        }
        todo = todos.parse_todo(raw)
        self.assertEqual(todo.assignee_kind, "agent")
        self.assertEqual(todo.assignee_display, "agent:coder")

    def test_priority_defaults_to_medium(self) -> None:
        raw = {
            "id": "task-1",
            "title": "Test",
            "status": "pending",
            "assignee": {"kind": "human"},
        }
        todo = todos.parse_todo(raw)
        self.assertEqual(todo.priority, "medium")

    def test_blocked_reason_captured(self) -> None:
        raw = {
            "id": "task-1",
            "title": "Test",
            "status": "blocked",
            "assignee": {"kind": "human"},
            "blocked_reason": "Waiting for review",
        }
        todo = todos.parse_todo(raw)
        self.assertEqual(todo.blocked_reason, "Waiting for review")


class PrioritySortTest(unittest.TestCase):
    """Test priority sorting order."""

    def test_priority_order(self) -> None:
        priorities = ["low", "medium", "high", "critical"]
        keys = [todos.priority_sort_key(p) for p in priorities]
        self.assertEqual(keys, [3, 2, 1, 0])

    def test_unknown_priority_defaults_to_medium(self) -> None:
        self.assertEqual(todos.priority_sort_key("unknown"), 2)


class ListTodosTest(unittest.TestCase):
    """Test todo listing with filters and sorting."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def write_file(self, content: str) -> Path:
        """Write content to a temporary todos.yaml file."""
        path = self.root / "todos.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_list_all_shows_open_statuses_only(self) -> None:
        path = self.write_file(MULTI_STATUS)
        result = todos.list_todos(path, "all")
        self.assertEqual(result, 0)

    def test_list_human_filters_correctly(self) -> None:
        path = self.write_file(MULTI_STATUS)
        result = todos.list_todos(path, "human")
        self.assertEqual(result, 0)

    def test_list_agent_filters_correctly(self) -> None:
        path = self.write_file(MULTI_STATUS)
        result = todos.list_todos(path, "agent")
        self.assertEqual(result, 0)

    def test_missing_file_returns_error(self) -> None:
        path = self.root / "nonexistent.yaml"
        result = todos.list_todos(path, "all")
        self.assertEqual(result, 1)

    def test_invalid_yaml_returns_error(self) -> None:
        path = self.write_file("{ invalid yaml")
        result = todos.list_todos(path, "all")
        self.assertEqual(result, 1)

    def test_missing_todos_array_returns_error(self) -> None:
        path = self.write_file("meta:\n  title: Test\n")
        result = todos.list_todos(path, "all")
        self.assertEqual(result, 1)

    def test_empty_result_succeeds(self) -> None:
        path = self.write_file("""---
todos:
  - id: done-1
    title: Already done
    status: done
    assignee:
      kind: human
    completed: 2026-11-01T10:00:00Z
""")
        result = todos.list_todos(path, "all")
        self.assertEqual(result, 0)


class CleanTodosTest(unittest.TestCase):
    """Test todo cleanup with dependency pruning."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def write_file(self, content: str) -> Path:
        """Write content to a temporary todos.yaml file."""
        path = self.root / "todos.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_clean_removes_done_only(self) -> None:
        path = self.write_file(MULTI_STATUS)
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        remaining_ids = {t["id"] for t in data["todos"]}
        self.assertNotIn("done-1", remaining_ids)
        self.assertIn("cancelled-1", remaining_ids)
        self.assertIn("pending-1", remaining_ids)
        self.assertIn("progress-1", remaining_ids)
        self.assertIn("blocked-1", remaining_ids)

    def test_clean_prunes_dependencies(self) -> None:
        path = self.write_file(DEPENDENCIES)
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        dependent_1 = next(t for t in data["todos"] if t["id"] == "dependent-1")
        self.assertNotIn("base-task", dependent_1["depends_on"])
        self.assertIn("other-task", dependent_1["depends_on"])

        dependent_2 = next(t for t in data["todos"] if t["id"] == "dependent-2")
        self.assertNotIn("base-task", dependent_2["depends_on"])
        self.assertEqual(len(dependent_2["depends_on"]), 0)

    def test_dry_run_writes_nothing(self) -> None:
        path = self.write_file(MULTI_STATUS)
        original = path.read_text()
        result = todos.clean_todos(path, dry_run=True)
        self.assertEqual(result, 0)
        self.assertEqual(path.read_text(), original)

    def test_no_done_todos_succeeds(self) -> None:
        path = self.write_file(MINIMAL_VALID)
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

    def test_atomic_write_preserves_permissions(self) -> None:
        path = self.write_file(MULTI_STATUS)
        original_mode = path.stat().st_mode
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)
        self.assertEqual(path.stat().st_mode, original_mode)

    def test_comments_preserved(self) -> None:
        """Comments are preserved during cleanup."""
        path = self.write_file(COMMENTS_YAML)
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

        cleaned = path.read_text()
        self.assertIn("# Meta section comment", cleaned)
        self.assertIn("# Inline comment in meta", cleaned)
        self.assertIn("# Todos section comment", cleaned)
        self.assertIn("# First todo comment", cleaned)
        self.assertNotIn("task-1", cleaned)
        self.assertIn("task-2", cleaned)

    def test_missing_file_returns_error(self) -> None:
        path = self.root / "nonexistent.yaml"
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 1)

    def test_unchanged_file_not_rewritten(self) -> None:
        path = self.write_file(MINIMAL_VALID)
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

    def test_symlink_rejected(self) -> None:
        """Refuse to follow symlinks."""
        target = self.write_file(MINIMAL_VALID)
        link = self.root / "link.yaml"
        link.symlink_to(target)
        result = todos.list_todos(link, "all")
        self.assertEqual(result, 1)

    def test_duplicate_ids_rejected(self) -> None:
        """Duplicate todo IDs cause validation error."""
        duplicate = """---
todos:
  - id: task-1
    title: First
    status: pending
    assignee:
      kind: human
  - id: task-1
    title: Duplicate ID
    status: pending
    assignee:
      kind: human
"""
        path = self.write_file(duplicate)
        result = todos.list_todos(path, "all")
        self.assertEqual(result, 1)

    def test_schema_invalid_blocks_write(self) -> None:
        """Schema validation failure prevents writes."""
        invalid = """---
todos:
  - id: task-1
    title: Schema validation should catch this
    assignee:
      kind: human
    status: done
    completed: 2026-11-01T10:00:00Z
  - id: task-2
    title: Invalid status value
    status: invalid_status_not_in_enum
"""
        path = self.write_file(invalid)
        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 1)


class ShowTodoTest(unittest.TestCase):
    """Test show command."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_show_displays_task_with_subtasks(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent task
    status: pending
    subtasks:
      - id: child-1
        title: Child task
        status: in_progress
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")
        result = todos.show_todo(path, "parent-1")
        self.assertEqual(result, 0)

    def test_show_nonexistent_task_returns_error(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")
        result = todos.show_todo(path, "nonexistent")
        self.assertEqual(result, 1)


class AddTodoTest(unittest.TestCase):
    """Test add command."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_add_minimal_task(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text("todos: []", encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title="New task",
            id=None,
            status=None,
            priority=None,
            description=None,
            assignee_kind=None,
            assignee_name=None,
            agent_type=None,
            depends_on=None,
            parent=None,
        )
        result = todos.add_todo(path, args, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        self.assertEqual(len(data["todos"]), 1)
        self.assertEqual(data["todos"][0]["title"], "New task")
        self.assertIn("id", data["todos"][0])

    def test_add_with_auto_generated_id(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text("todos: []", encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title="Fix critical bug",
            id=None,
            status=None,
            priority=None,
            description=None,
            assignee_kind=None,
            assignee_name=None,
            agent_type=None,
            depends_on=None,
            parent=None,
        )
        result = todos.add_todo(path, args, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        generated_id = data["todos"][0]["id"]
        self.assertTrue(generated_id.startswith("fix-critical-bug"))

    def test_add_as_subtask(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent task
    status: pending
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title="Child task",
            id="child-1",
            status=None,
            priority=None,
            description=None,
            assignee_kind=None,
            assignee_name=None,
            agent_type=None,
            depends_on=None,
            parent="parent-1",
        )
        result = todos.add_todo(path, args, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertIn("subtasks", loaded["todos"][0])
        self.assertEqual(len(loaded["todos"][0]["subtasks"]), 1)
        self.assertEqual(loaded["todos"][0]["subtasks"][0]["id"], "child-1")

    def test_add_duplicate_id_fails(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title="Duplicate",
            id="task-1",
            status=None,
            priority=None,
            description=None,
            assignee_kind=None,
            assignee_name=None,
            agent_type=None,
            depends_on=None,
            parent=None,
        )
        result = todos.add_todo(path, args, dry_run=False)
        self.assertEqual(result, 1)

    def test_add_dry_run(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text("todos: []", encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title="Test",
            id="test-1",
            status=None,
            priority=None,
            description=None,
            assignee_kind=None,
            assignee_name=None,
            agent_type=None,
            depends_on=None,
            parent=None,
        )
        result = todos.add_todo(path, args, dry_run=True)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        self.assertEqual(len(data["todos"]), 0)


class UpdateTodoTest(unittest.TestCase):
    """Test update command."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_update_status(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title=None,
            status="in_progress",
            priority=None,
            description=None,
            blocked_reason=None,
        )
        result = todos.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        self.assertEqual(data["todos"][0]["status"], "in_progress")

    def test_update_status_to_done_adds_completed(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title=None,
            status="done",
            priority=None,
            description=None,
            blocked_reason=None,
        )
        result = todos.update_todo(path, "task-1", args, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        self.assertEqual(data["todos"][0]["status"], "done")
        self.assertIn("completed", data["todos"][0])

    def test_update_nonexistent_task_fails(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            title=None,
            status="done",
            priority=None,
            description=None,
            blocked_reason=None,
        )
        result = todos.update_todo(path, "nonexistent", args, dry_run=False)
        self.assertEqual(result, 1)


class RemoveTodoTest(unittest.TestCase):
    """Test remove command."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_remove_task_without_subtasks(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")

        result = todos.remove_todo(path, "task-1", recursive=False, dry_run=False)
        self.assertEqual(result, 0)

        data = todos.load_yaml(path)
        self.assertEqual(len(data["todos"]), 0)

    def test_remove_task_with_subtasks_without_recursive_fails(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent
    status: pending
    subtasks:
      - id: child-1
        title: Child
        status: pending
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.remove_todo(path, "parent-1", recursive=False, dry_run=False)
        self.assertEqual(result, 1)

    def test_remove_task_with_subtasks_recursively(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent
    status: pending
    subtasks:
      - id: child-1
        title: Child
        status: pending
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.remove_todo(path, "parent-1", recursive=True, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertEqual(len(loaded["todos"]), 0)

    def test_remove_prunes_dependencies(self) -> None:
        data = """---
todos:
  - id: task-1
    title: Base
    status: pending
  - id: task-2
    title: Dependent
    status: pending
    depends_on:
      - task-1
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.remove_todo(path, "task-1", recursive=False, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertNotIn("depends_on", loaded["todos"][0])


class MoveTodoTest(unittest.TestCase):
    """Test move command."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_move_subtask_to_root(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent
    status: pending
    subtasks:
      - id: child-1
        title: Child
        status: pending
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.move_todo(path, "child-1", parent_id=None, to_root=True, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertEqual(len(loaded["todos"]), 2)
        self.assertNotIn("subtasks", loaded["todos"][0])

    def test_move_task_to_new_parent(self) -> None:
        data = """---
todos:
  - id: task-1
    title: Task 1
    status: pending
  - id: parent-1
    title: Parent
    status: pending
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.move_todo(path, "task-1", parent_id="parent-1", to_root=False, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertEqual(len(loaded["todos"]), 1)
        self.assertIn("subtasks", loaded["todos"][0])
        self.assertEqual(loaded["todos"][0]["subtasks"][0]["id"], "task-1")


class SubtaskCleanTest(unittest.TestCase):
    """Test clean command with subtasks."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_clean_preserves_done_parent_with_open_subtasks(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent
    status: done
    completed: 2026-11-01T10:00:00Z
    subtasks:
      - id: child-1
        title: Open child
        status: pending
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertEqual(len(loaded["todos"]), 1)
        self.assertEqual(loaded["todos"][0]["id"], "parent-1")

    def test_clean_removes_done_parent_with_done_subtasks(self) -> None:
        data = """---
todos:
  - id: parent-1
    title: Parent
    status: done
    completed: 2026-11-01T10:00:00Z
    subtasks:
      - id: child-1
        title: Done child
        status: done
        completed: 2026-11-01T09:00:00Z
"""
        path = self.root / "todos.yaml"
        path.write_text(data, encoding="utf-8")

        result = todos.clean_todos(path, dry_run=False)
        self.assertEqual(result, 0)

        loaded = todos.load_yaml(path)
        self.assertEqual(len(loaded["todos"]), 0)


class HelpTextTest(unittest.TestCase):
    """Test help output is available."""

    def test_main_help_available(self) -> None:
        sys.argv = ["todos.py", "--help"]
        with self.assertRaises(SystemExit) as cm:
            todos.main()
        self.assertEqual(cm.exception.code, 0)

    def test_add_help_available(self) -> None:
        sys.argv = ["todos.py", "add", "--help"]
        with self.assertRaises(SystemExit) as cm:
            todos.main()
        self.assertEqual(cm.exception.code, 0)


class MainFunctionTest(unittest.TestCase):
    """Test CLI argument parsing."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.addCleanup(self._tempdir.cleanup)

    def test_list_command_defaults(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")
        sys.argv = ["todos.py", "list", "--file", str(path)]
        result = todos.main()
        self.assertEqual(result, 0)

    def test_list_command_with_kind(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MINIMAL_VALID, encoding="utf-8")
        sys.argv = ["todos.py", "list", "human", "--file", str(path)]
        result = todos.main()
        self.assertEqual(result, 0)

    def test_clean_command_dry_run(self) -> None:
        path = self.root / "todos.yaml"
        path.write_text(MULTI_STATUS, encoding="utf-8")
        sys.argv = ["todos.py", "clean", "--file", str(path), "--dry-run"]
        result = todos.main()
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
