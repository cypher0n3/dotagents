"""The update command, which done and start also use."""

from __future__ import annotations

import argparse
from pathlib import Path

from .io_ops import load_and_validate_file, write_data
from .models import find_task_by_id
from .mutations import apply_field_updates, touch_meta


def update_todo(file_path: Path, task_id: str, args: argparse.Namespace, dry_run: bool = False) -> int:
    """Apply the field flags in args to a task and write the file."""
    data = load_and_validate_file(file_path)
    if isinstance(data, int):
        return data

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found")
        return 1

    task, _ = task_result

    try:
        task_id, updates = apply_field_updates(task, data, task_id, args)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if not updates:
        print("No updates specified")
        return 0

    touch_meta(data)

    if dry_run:
        print(f"Dry run: would update task '{task_id}': {', '.join(updates)}")
        return 0

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Updated task '{task_id}': {', '.join(updates)}")
    return result_code
