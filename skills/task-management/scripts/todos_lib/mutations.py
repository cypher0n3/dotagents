"""Field mutations shared by the add and update commands."""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timezone
from typing import Any

from .models import FILE_OPS, collect_all_ids

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LIST_FIELDS = ("depends_on", "tags", "acceptance_criteria")
# Optional scalar fields: an empty string clears them.
CLEARABLE_FIELDS = ("description", "blocked_reason", "due", "created")
# File-entry modifier flags (PATH=VALUE) and the entry key each one sets.
FILE_MODIFIERS = {"file_op": "op", "file_reason": "reason", "file_renamed_to": "renamed_to"}


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def touch_meta(data: dict[str, Any]) -> None:
    """Set meta.updated to now, creating meta if needed."""
    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = now_iso()


def check_date(value: str, flag: str) -> None:
    """Raise ValueError unless value is a YYYY-MM-DD calendar date."""
    try:
        if _DATE_RE.match(value):
            date.fromisoformat(value)
            return
    except ValueError:
        pass
    raise ValueError(f"{flag} must be a date in YYYY-MM-DD form, got '{value}'")


def check_datetime(value: str, flag: str) -> None:
    """Raise ValueError unless value is an ISO 8601 date-time with a time zone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None or "T" not in value or parsed.tzinfo is None:
        raise ValueError(f"{flag} must be an ISO 8601 date-time with a time zone, got '{value}'")


def check_dependencies(deps: list[str], existing_ids: set[str], task_id: str) -> None:
    """Raise ValueError if a dependency is the task itself or does not exist."""
    for dep in deps:
        if dep == task_id:
            raise ValueError(f"Task '{task_id}' cannot depend on itself")
        if dep not in existing_ids:
            raise ValueError(f"Dependency '{dep}' not found")


def _arg(args: argparse.Namespace, name: str, default: Any = None) -> Any:
    """Read a flag that a command (or a test's Namespace) may not define."""
    return getattr(args, name, default)


def build_assignee(args: argparse.Namespace, current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the assignee the args describe, or None if they change nothing.

    Without --assignee-kind, the name, agent type, and review flags edit the current assignee.
    """
    kind = _arg(args, "assignee_kind")
    name = _arg(args, "assignee_name")
    agent_type = _arg(args, "agent_type")
    review = _arg(args, "requires_human_review")
    if not kind and name is None and agent_type is None and review is None:
        return None
    if not kind:
        if not current:
            raise ValueError("Task has no assignee; pass --assignee-kind")
        kind = current["kind"]

    assignee = dict(current) if current and current.get("kind") == kind else {"kind": kind}
    if kind == "human":
        if agent_type or review:
            raise ValueError("--agent-type and --requires-human-review apply only to agent assignees")
        set_or_clear(assignee, "name", name)
        return assignee

    if name:
        raise ValueError("--assignee-name applies only to human assignees")
    if agent_type:
        assignee["agent_type"] = agent_type
    if not assignee.get("agent_type"):
        raise ValueError("--agent-type required for agent assignee")
    if review:
        assignee["requires_human_review"] = True
    elif review is False:
        assignee.pop("requires_human_review", None)
    return assignee


def set_or_clear(target: dict[str, Any], key: str, value: str | None) -> str | None:
    """Set key to value, delete it for an empty value, or leave it for None; describe the change."""
    if value is None:
        return None
    if value:
        target[key] = value
        return f"{key}='{value}'"
    if key in target:
        del target[key]
        return f"{key} removed"
    return None


def _check_scalar_args(args: argparse.Namespace) -> None:
    """Validate scalar args before anything is changed."""
    reason = _arg(args, "blocked_reason")
    status = _arg(args, "status")
    if reason and status and status != "blocked":
        raise ValueError(f"--blocked-reason sets status to blocked; it cannot be combined with --status {status}")
    if _arg(args, "due"):
        check_date(args.due, "--due")
    if _arg(args, "created"):
        check_datetime(args.created, "--created")


def _update_status(task: dict[str, Any], status: str) -> list[str]:
    """Set status and keep the completed timestamp in step with it."""
    updates = [f"status={status}"]
    old_status = task.get("status", "pending")
    task["status"] = status
    if status == "done" and "completed" not in task:
        task["completed"] = now_iso()
        updates.append("completed=now")
    elif status != "done" and old_status == "done" and "completed" in task:
        del task["completed"]
        updates.append("completed timestamp removed")
    return updates


def _update_scalar_fields(task: dict[str, Any], args: argparse.Namespace) -> list[str]:
    """Update title, status, priority, and the clearable scalar fields."""
    updates = []
    if _arg(args, "title"):
        task["title"] = args.title
        updates.append(f"title='{args.title}'")

    status = _arg(args, "status") or ("blocked" if _arg(args, "blocked_reason") else None)
    if status:
        updates.extend(_update_status(task, status))

    if _arg(args, "priority"):
        task["priority"] = args.priority
        updates.append(f"priority={args.priority}")
    elif _arg(args, "clear_priority") and "priority" in task:
        del task["priority"]
        updates.append("priority removed")

    for field in CLEARABLE_FIELDS:
        change = set_or_clear(task, field, _arg(args, field))
        if change:
            updates.append(change)
    return updates


def _update_assignee(task: dict[str, Any], args: argparse.Namespace) -> list[str]:
    """Update or clear the assignee."""
    if _arg(args, "clear_assignee"):
        if "assignee" not in task:
            return []
        del task["assignee"]
        return ["assignee cleared"]
    assignee = build_assignee(args, task.get("assignee"))
    if assignee is None:
        return []
    task["assignee"] = assignee
    return [f"assignee={assignee['kind']}"]


def _find_file_entry(task: dict[str, Any], path: str) -> dict[str, Any]:
    """Return the task's file entry for path."""
    for entry in task.get("files", []):
        if entry["path"] == path:
            return entry
    raise ValueError(f"No file entry for '{path}'")


def _parse_file_spec(spec: str) -> dict[str, str]:
    """Parse 'PATH:OP' into a file entry."""
    path, sep, op = spec.rpartition(":")
    if not sep or not path:
        raise ValueError(f"Invalid file spec '{spec}', expected 'path:op'")
    _check_file_op(op)
    return {"path": path, "op": op}


def _check_file_op(op: str) -> None:
    """Raise ValueError unless op is a schema file op."""
    if op not in FILE_OPS:
        raise ValueError(f"Invalid file op '{op}', expected one of {', '.join(FILE_OPS)}")


def _modify_file_entries(task: dict[str, Any], args: argparse.Namespace) -> list[str]:
    """Apply the PATH=VALUE file-entry modifier flags."""
    updates = []
    for attr, key in FILE_MODIFIERS.items():
        for item in _arg(args, attr) or []:
            path, sep, value = item.partition("=")
            if not sep or not path:
                raise ValueError(f"--{attr.replace('_', '-')} expects PATH=VALUE, got '{item}'")
            if key == "op":
                _check_file_op(value)
            change = set_or_clear(_find_file_entry(task, path), key, value)
            if change:
                updates.append(f"file '{path}' {change}")
    return updates


def _update_file_entries(task: dict[str, Any], args: argparse.Namespace) -> list[str]:
    """Clear, remove, add, then edit file entries."""
    updates = []
    files = [] if _arg(args, "clear_files") else list(task.get("files", []))
    if len(files) < len(task.get("files", [])):
        updates.append("files cleared")

    remove_paths = _arg(args, "remove_file") or []
    if remove_paths:
        files = [f for f in files if f["path"] not in remove_paths]
        updates.append(f"removed {len(remove_paths)} file(s)")

    for entry in map(_parse_file_spec, _arg(args, "add_file") or []):
        if any(f["path"] == entry["path"] for f in files):
            raise ValueError(f"File entry for '{entry['path']}' already exists")
        files.append(entry)
        updates.append(f"added file '{entry['path']}'")

    if files:
        task["files"] = files
    else:
        task.pop("files", None)
    return updates + _modify_file_entries(task, args)


def _apply_list_update(task: dict[str, Any], field: str, args: argparse.Namespace) -> list[str]:
    """Apply the clear, remove, and add flags for a list field."""
    updates = []
    if _arg(args, f"clear_{field}") and field in task:
        del task[field]
        updates.append(f"{field} cleared")
    remove_items = _arg(args, f"remove_{field}")
    if remove_items and field in task:
        task[field] = [item for item in task[field] if item not in remove_items]
        if not task[field]:
            del task[field]
        updates.append(f"{field} removed {len(remove_items)} item(s)")
    add_items = _arg(args, f"add_{field}")
    if add_items:
        items = task.setdefault(field, [])
        for item in add_items:
            if item not in items:
                items.append(item)
        updates.append(f"{field} added {len(add_items)} item(s)")
    return updates


def apply_field_updates(
    task: dict[str, Any], data: dict[str, Any], task_id: str, args: argparse.Namespace
) -> tuple[str, list[str]]:
    """Apply the field flags in args to task; return its (possibly renamed) ID and a description of each change.

    Raises ValueError on invalid input, possibly after changing some fields;
    callers then exit without writing, so the file is never left half-updated.
    """
    _check_scalar_args(args)
    updates = []

    new_id = _arg(args, "new_id")
    if new_id:
        if new_id != task_id and new_id in collect_all_ids(data["todos"]):
            raise ValueError(f"Task ID '{new_id}' already exists")
        task["id"] = new_id
        _rename_task_id(data, task_id, new_id)
        updates.append(f"id renamed to '{new_id}'")
        task_id = new_id

    add_deps = _arg(args, "add_depends_on")
    if add_deps:
        check_dependencies(add_deps, collect_all_ids(data["todos"]), task_id)

    updates.extend(_update_scalar_fields(task, args))
    updates.extend(_update_assignee(task, args))
    for field in LIST_FIELDS:
        updates.extend(_apply_list_update(task, field, args))
    updates.extend(_update_file_entries(task, args))
    return task_id, updates


def _rename_task_id(data: dict[str, Any], old_id: str, new_id: str) -> None:
    """Point every depends_on reference to old_id at new_id, at any depth."""
    def update_refs(tasks: list[dict[str, Any]]) -> None:
        for t in tasks:
            if "depends_on" in t:
                t["depends_on"] = [new_id if dep == old_id else dep for dep in t["depends_on"]]
            if "subtasks" in t:
                update_refs(t["subtasks"])

    update_refs(data["todos"])
