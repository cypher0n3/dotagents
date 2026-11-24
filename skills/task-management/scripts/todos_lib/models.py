"""Task constants, parsing, and lookups over the todos tree."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# Allowed values, kept in step with assets/todos-schema.json.
STATUSES = ("pending", "in_progress", "blocked", "done", "cancelled")
OPEN_STATUSES = ("pending", "in_progress", "blocked")
PRIORITIES = ("low", "medium", "high", "critical")
FILE_OPS = ("create", "read", "update", "delete")
ASSIGNEE_KINDS = ("human", "agent")


@dataclass
class Todo:
    """A task with defaults filled in, for listing and display; raw is the task as stored."""
    id: str
    title: str
    status: str
    priority: str
    assignee_kind: str
    assignee_display: str
    created: datetime | None
    blocked_reason: str | None
    raw: dict[str, Any]


@dataclass
class TaskFilters:
    """List filters; None means no filter, and kind "all" matches every assignee."""
    kind: str
    status: str | None
    priority: str | None
    tag: str | None


def parse_datetime(value: Any) -> datetime | None:
    """Return value as a UTC-aware datetime, or None if it is missing or not a recognized format."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(value, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def parse_todo(raw: dict[str, Any]) -> Todo:
    """Build a Todo from a stored task; raises KeyError if the task has no title."""
    assignee = raw.get("assignee", {})
    kind = assignee.get("kind", "unassigned")

    if kind == "human":
        name = assignee.get("name", "")
        display = f"human:{name}" if name else "human"
    elif kind == "agent":
        agent_type = assignee.get("agent_type", "unknown")
        display = f"agent:{agent_type}"
    else:
        display = "unassigned"

    return Todo(
        id=raw.get("id", ""),
        title=raw["title"],
        status=raw.get("status", "pending"),
        priority=raw.get("priority", "medium"),
        assignee_kind=kind,
        assignee_display=display,
        created=parse_datetime(raw.get("created")),
        blocked_reason=raw.get("blocked_reason"),
        raw=raw,
    )


def priority_sort_key(priority: str) -> int:
    """Sort critical first; an unknown priority sorts as medium."""
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(priority, 2)


def generate_id(title: str, existing_ids: set[str]) -> str:
    """Slugify title (at most 30 characters), adding -1, -2, ... until it is not in existing_ids."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base[:30] if base else "task"
    candidate = base
    counter = 1
    while candidate in existing_ids:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def collect_all_ids(tasks: list[dict[str, Any]]) -> set[str]:
    """Return the IDs of all tasks, including subtasks."""
    ids = set()
    for task in tasks:
        if "id" in task:
            ids.add(task["id"])
        if "subtasks" in task:
            ids.update(collect_all_ids(task["subtasks"]))
    return ids


def find_task_by_id(tasks: list[dict[str, Any]], task_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Return (task, the list that holds it), searching subtasks too, or None if not found."""
    for task in tasks:
        if task.get("id") == task_id:
            return (task, tasks)
        if "subtasks" in task:
            result = find_task_by_id(task["subtasks"], task_id)
            if result:
                return result
    return None
