#!/usr/bin/env python3
"""Command-line entry point for managing a YAML todos file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run as a script, this directory is not on the import path, so add it for todos_lib.
if not __package__:
    sys.path.insert(0, str(Path(__file__).parent))

from todos_lib.advanced_commands import clean_todos, meta_command, move_todo
from todos_lib.basic_commands import add_todo, init_file, remove_todo
from todos_lib.cli_parser import setup_arg_parser
from todos_lib.io_ops import get_default_path
from todos_lib.list_show import list_todos, show_todo
from todos_lib.update_command import update_todo

# Commands that only set a status, mapped to the status they set.
_STATUS_SHORTCUTS = {"done": "done", "start": "in_progress"}


def main() -> int:
    """Parse the command line, run the command, and return its exit code."""
    args = setup_arg_parser().parse_args()
    path = args.file or get_default_path()
    command = args.command

    if command in _STATUS_SHORTCUTS:
        status_args = argparse.Namespace(status=_STATUS_SHORTCUTS[command])
        return update_todo(path, args.task_id, status_args, args.dry_run)
    handlers = {
        "init": lambda: init_file(path, args.title),
        "list": lambda: list_todos(path, args.kind, args.status, args.priority, args.tag),
        "show": lambda: show_todo(path, args.task_id),
        "add": lambda: add_todo(path, args, args.dry_run),
        "update": lambda: update_todo(path, args.task_id, args, args.dry_run),
        "remove": lambda: remove_todo(path, args.task_id, args.recursive, args.dry_run),
        "move": lambda: move_todo(path, args.task_id, args.parent, args.root, args.dry_run),
        "clean": lambda: clean_todos(path, args.dry_run),
        "meta": lambda: meta_command(path, args),
    }
    return handlers[command]()


if __name__ == "__main__":
    sys.exit(main())
