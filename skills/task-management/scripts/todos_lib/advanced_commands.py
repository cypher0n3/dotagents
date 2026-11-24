"""The move, clean, and meta commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .io_ops import load_and_validate_file, write_data
from .models import find_task_by_id
from .mutations import check_datetime, set_or_clear, touch_meta


def move_todo(
    file_path: Path, task_id: str, parent_id: str | None, to_root: bool = False, dry_run: bool = False
) -> int:
    """Move a task under parent_id, or to the root with to_root."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    if not to_root and not parent_id:
        print("Error: Must specify --parent or --root")
        return 1
    if to_root and parent_id:
        print("Error: Cannot specify both --parent and --root")
        return 1

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found")
        return 1

    task, old_parent_list = task_result

    if to_root:
        if old_parent_list is data["todos"]:
            print(f"Task '{task_id}' is already at root level")
            return 0
        if dry_run:
            print(f"Dry run: would move task '{task_id}' to root level")
            return 0
        old_parent_list.remove(task)
        data["todos"].append(task)
        _cleanup_empty_subtasks(data["todos"])
        location = "root level"
    else:
        parent_result = find_task_by_id(data["todos"], parent_id)  # type: ignore
        if not parent_result:
            print(f"Error: Parent task '{parent_id}' not found")
            return 1
        parent_task, _ = parent_result
        if task in parent_task.get("subtasks", []):
            print(f"Task '{task_id}' is already a subtask of '{parent_id}'")
            return 0
        if dry_run:
            print(f"Dry run: would move task '{task_id}' to be subtask of '{parent_id}'")
            return 0
        old_parent_list.remove(task)
        parent_task.setdefault("subtasks", []).append(task)
        _cleanup_empty_subtasks(data["todos"])
        location = f"subtask of {parent_id}"

    touch_meta(data)
    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Moved task '{task_id}' to {location}")
    return result_code


def _cleanup_empty_subtasks(tasks: list[dict[str, Any]]) -> None:
    """Delete subtasks lists left empty by a move, at any depth."""
    for t in tasks:
        if "subtasks" in t and not t["subtasks"]:
            del t["subtasks"]
        elif "subtasks" in t:
            _cleanup_empty_subtasks(t["subtasks"])


def clean_todos(file_path: Path, dry_run: bool) -> int:
    """Remove done tasks, keeping a done task that still has open subtasks, and drop dependencies on them."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    done_ids: set[str] = set()
    cleaned_tasks: list[dict[str, Any]] = []

    for task in data["todos"]:
        cleaned = _process_task_for_clean(task, done_ids)
        if cleaned:
            cleaned_tasks.append(cleaned)

    if not done_ids:
        print("No completed todos to remove.")
        return 0

    print(f"Found {len(done_ids)} completed todo(s) to remove:")
    for todo_id in sorted(done_ids):
        print(f"  - {todo_id}")

    pruned_deps = _prune_dependencies(cleaned_tasks, done_ids)
    if pruned_deps:
        print(f"\nPruning {len(pruned_deps)} dependency reference(s):")
        for todo_id, removed_ids in pruned_deps:
            print(f"  {todo_id}: removed {', '.join(removed_ids)}")

    if dry_run:
        print(f"\nDry run: would remove {len(done_ids)} todo(s) (no changes written)")
        return 0

    data["todos"] = cleaned_tasks
    touch_meta(data)

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"\nRemoved {len(done_ids)} completed todo(s), {len(cleaned_tasks)} remaining.")
    return result_code


def _process_task_for_clean(task: dict[str, Any], done_ids: set[str]) -> dict[str, Any] | None:
    """Return task without its done subtasks, or None if it is done and nothing open remains under it.

    Adds the ID of every removed task to done_ids.
    """
    task_id = task.get("id", "")
    status = task.get("status", "pending")

    cleaned_subtasks = []
    if "subtasks" in task:
        for subtask in task["subtasks"]:
            cleaned = _process_task_for_clean(subtask, done_ids)
            if cleaned:
                cleaned_subtasks.append(cleaned)

    if status == "done":
        if cleaned_subtasks:
            task_copy = task.copy()
            task_copy["subtasks"] = cleaned_subtasks
            return task_copy
        if task_id:
            done_ids.add(task_id)
        return None

    if cleaned_subtasks:
        task["subtasks"] = cleaned_subtasks
    elif "subtasks" in task:
        del task["subtasks"]
    return task


def _prune_dependencies(remaining: list[dict[str, Any]], done_ids: set[str]) -> list[tuple[str, list[str]]]:
    """Drop removed task IDs from depends_on lists; return (task ID, removed IDs) for each change."""
    pruned_deps = []

    def prune_task(task: dict[str, Any]) -> None:
        if "depends_on" in task:
            original_deps = task["depends_on"]
            new_deps = [dep for dep in original_deps if dep not in done_ids]
            if len(new_deps) < len(original_deps):
                removed = set(original_deps) - set(new_deps)
                task_id = task.get("id", "unknown")
                pruned_deps.append((task_id, sorted(removed)))
                if new_deps:
                    task["depends_on"] = new_deps
                else:
                    del task["depends_on"]
        if "subtasks" in task:
            for subtask in task["subtasks"]:
                prune_task(subtask)

    for task in remaining:
        prune_task(task)
    return pruned_deps


def meta_command(file_path: Path, args: argparse.Namespace) -> int:
    """Print the meta section with --show, or set or clear its title and created timestamp."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    if getattr(args, "show", False):
        if "meta" in data:
            print("Meta:")
            for key, value in data["meta"].items():
                print(f"  {key}: {value}")
        else:
            print("No meta section")
        return 0

    if getattr(args, "created", None):
        try:
            check_datetime(args.created, "--created")
        except ValueError as e:
            print(f"Error: {e}")
            return 1

    meta = data.get("meta", {})
    updates = [change for field in ("title", "created")
               if (change := set_or_clear(meta, field, getattr(args, field, None)))]

    if updates:
        data["meta"] = meta
        touch_meta(data)
        result_code = write_data(data, file_path)
        if not result_code:
            print(f"Updated meta: {', '.join(updates)}")
        return result_code

    print("No action specified. Use --show, --title, or --created")
    return 0
