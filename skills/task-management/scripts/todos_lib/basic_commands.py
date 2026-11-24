"""The init, add, and remove commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .io_ops import load_and_validate_file, write_data
from .models import collect_all_ids, find_task_by_id, generate_id
from .mutations import apply_field_updates, now_iso, touch_meta


def init_file(file_path: Path, title: str | None) -> int:
    """Create an empty todos file; refuse to overwrite an existing one."""
    if file_path.exists():
        print(f"Error: {file_path} already exists")
        return 1
    meta: dict[str, Any] = {"title": title} if title else {}
    meta["created"] = meta["updated"] = now_iso()
    result_code = write_data({"meta": meta, "todos": []}, file_path)
    if not result_code:
        print(f"Created {file_path}")
    return result_code


def add_todo(file_path: Path, args: argparse.Namespace, dry_run: bool = False) -> int:
    """Add a task at the root or under --parent; its fields go through the same code as update."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    existing_ids = collect_all_ids(data["todos"])
    task_id = args.id or generate_id(args.title, existing_ids)

    if task_id in existing_ids:
        print(f"Error: Task ID '{task_id}' already exists")
        return 1

    new_task: dict[str, Any] = {"id": task_id, "title": args.title, "created": now_iso()}

    try:
        apply_field_updates(new_task, data, task_id, args)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if getattr(args, "parent", None):
        parent_result = find_task_by_id(data["todos"], args.parent)
        if not parent_result:
            print(f"Error: Parent task '{args.parent}' not found")
            return 1
        parent_task, _ = parent_result
        parent_task.setdefault("subtasks", []).append(new_task)
        location = f"as subtask of {args.parent}"
    else:
        data["todos"].append(new_task)
        location = "at root level"

    touch_meta(data)

    if dry_run:
        print(f"Dry run: would add task '{task_id}' {location}")
        return 0

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Added task '{task_id}' {location}")
    return result_code


def remove_todo(file_path: Path, task_id: str, recursive: bool = False, dry_run: bool = False) -> int:
    """Remove a task, and with recursive its subtasks, then drop dependencies on it."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found")
        return 1

    task, parent_list = task_result
    subtask_count = len(task.get("subtasks", []))
    if subtask_count and not recursive:
        print(f"Error: Task '{task_id}' has subtasks. Use --recursive.")
        return 1
    subtask_note = f" and {subtask_count} subtask(s)" if subtask_count else ""

    if dry_run:
        print(f"Dry run: would remove task '{task_id}'{subtask_note}")
        return 0

    parent_list.remove(task)
    _prune_deps(data["todos"], task_id)
    touch_meta(data)

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Removed task '{task_id}'{subtask_note}")
    return result_code


def _prune_deps(tasks: list[dict[str, Any]], task_id: str) -> None:
    """Remove task_id from every depends_on list, dropping lists left empty."""
    for t in tasks:
        if "depends_on" in t:
            t["depends_on"] = [dep for dep in t["depends_on"] if dep != task_id]
            if not t["depends_on"]:
                del t["depends_on"]
        if "subtasks" in t:
            _prune_deps(t["subtasks"], task_id)
