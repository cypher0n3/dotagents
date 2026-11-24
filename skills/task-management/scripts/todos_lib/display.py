"""Printing tasks for list and show."""

from typing import Any

from .models import Todo, parse_datetime, parse_todo


def print_task_line(todo: Todo, prefix: str) -> None:
    """Print the status, priority, ID, and assignee line, then the title."""
    status_marker = {"blocked": "⚠", "done": "✓", "cancelled": "✗"}.get(todo.status, "○")
    print(f"{prefix}{status_marker} [{todo.priority:8}] {todo.status:12} {todo.id:20} ({todo.assignee_display})")
    print(f"{prefix}  {todo.title}")


def print_task_tree(task: dict[str, Any], indent: int = 0, show_subtasks: bool = True) -> None:
    """Print a task's fields, then its subtasks indented one level deeper."""
    todo = parse_todo(task)
    prefix = "  " * indent
    print_task_line(todo, prefix)

    _print_task_metadata(task, todo, prefix)
    _print_task_files(task, prefix)

    if show_subtasks and "subtasks" in task:
        for subtask in task["subtasks"]:
            print()
            print_task_tree(subtask, indent + 1)


def _print_task_metadata(task: dict[str, Any], todo: Todo, prefix: str) -> None:
    """Print each optional field that is set."""
    if "description" in task:
        print(f"{prefix}  Description: {task['description']}")
    if todo.blocked_reason:
        print(f"{prefix}  BLOCKED: {todo.blocked_reason}")
    if task.get("depends_on"):
        print(f"{prefix}  Depends on: {', '.join(task['depends_on'])}")
    if task.get("acceptance_criteria"):
        print(f"{prefix}  Acceptance criteria:")
        for criterion in task["acceptance_criteria"]:
            print(f"{prefix}    - {criterion}")
    if task.get("tags"):
        print(f"{prefix}  Tags: {', '.join(task['tags'])}")
    if "due" in task:
        print(f"{prefix}  Due: {task['due']}")
    if task.get("assignee", {}).get("requires_human_review"):
        print(f"{prefix}  Requires human review: Yes")
    if todo.created:
        print(f"{prefix}  Created: {todo.created.isoformat()}")
    if "completed" in task:
        completed = parse_datetime(task["completed"])
        if completed:
            print(f"{prefix}  Completed: {completed.isoformat()}")


def _print_task_files(task: dict[str, Any], prefix: str) -> None:
    """Print file entries as 'path (op) -> renamed_to: reason'."""
    if not task.get("files"):
        return
    print(f"{prefix}  Files:")
    for entry in task["files"]:
        line = f"{entry['path']} ({entry['op']})"
        if entry.get("renamed_to"):
            line += f" -> {entry['renamed_to']}"
        if entry.get("reason"):
            line += f": {entry['reason']}"
        print(f"{prefix}    - {line}")
