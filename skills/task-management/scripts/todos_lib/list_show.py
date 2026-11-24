"""The list and show commands."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .display import print_task_line, print_task_tree
from .io_ops import load_and_validate_file
from .models import OPEN_STATUSES, TaskFilters, Todo, find_task_by_id, parse_todo, priority_sort_key


def list_todos(
    file_path: Path, kind_filter: str, status_filter: str | None = None,
    priority_filter: str | None = None, tag_filter: str | None = None,
) -> int:
    """List tasks matching the filters; only open tasks unless a status is given."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    filters = TaskFilters(kind=kind_filter, status=status_filter, priority=priority_filter, tag=tag_filter)
    todos: list[Todo] = []
    _collect_tasks(data["todos"], filters, todos)
    todos.sort(key=lambda t: (
        priority_sort_key(t.priority),
        t.created if t.created else datetime.max.replace(tzinfo=timezone.utc),
        t.id,
    ))

    filter_parts = [f"assignee={kind_filter}"] + [
        f"{name}={value}" for name, value in
        (("status", status_filter), ("priority", priority_filter), ("tag", tag_filter)) if value
    ]
    label = "Todos" if status_filter else "Open todos"
    if not todos:
        print(f"No {label.lower()} found ({', '.join(filter_parts)})")
        return 0
    print(f"{label} ({', '.join(filter_parts)}):\n")

    for todo in todos:
        print_task_line(todo, "")
        if todo.blocked_reason:
            print(f"  BLOCKED: {todo.blocked_reason}")
        print()
    return 0


def _collect_tasks(tasks: list[dict[str, Any]], filters: TaskFilters, todos: list[Todo]) -> None:
    """Append matching tasks to todos.

    Without a status filter, subtasks of closed tasks are skipped along with their parent.
    """
    for raw in tasks:
        try:
            todo = parse_todo(raw)
        except KeyError as e:
            print(f"Warning: Skipping todo missing required field {e}", file=sys.stderr)
            continue

        in_scope = todo.status == filters.status if filters.status else todo.status in OPEN_STATUSES
        matches = (
            in_scope
            and filters.kind in ("all", todo.assignee_kind)
            and (not filters.priority or todo.priority == filters.priority)
            and (not filters.tag or filters.tag in raw.get("tags", []))
        )
        if matches:
            todos.append(todo)
        if "subtasks" in raw and (filters.status or in_scope):
            _collect_tasks(raw["subtasks"], filters, todos)


def show_todo(file_path: Path, task_id: str) -> int:
    """Print one task with every field that is set, and its subtasks."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found")
        return 1

    task, _ = task_result
    print_task_tree(task, show_subtasks=True)
    return 0
