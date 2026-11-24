"""CLI argument parser."""

import argparse
from pathlib import Path

from .models import ASSIGNEE_KINDS, FILE_OPS, PRIORITIES, STATUSES

_LIST_FIELDS = (
    ("depends-on", "dependency task IDs"),
    ("tags", "tags"),
    ("acceptance-criteria", "acceptance criteria"),
)
_FILE_SPEC = f"'PATH:OP', OP one of {'/'.join(FILE_OPS)}"


def setup_arg_parser() -> argparse.ArgumentParser:
    """Set up argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="YAML todos management CLI",
        epilog="Run 'todos.py COMMAND --help' for detailed command usage.",
    )
    sub = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    init = _command(sub, "init", "Create a new todos file", dry_run=False)
    init.add_argument("--title", help="Meta title")

    lst = _command(sub, "list", "List tasks (open tasks unless --status is given)", dry_run=False)
    lst.add_argument("kind", nargs="?", default="all", choices=["all", "human", "agent", "unassigned"],
                     help="Filter by assignee kind")
    lst.add_argument("--status", choices=STATUSES, help="Filter by status, including done or cancelled")
    lst.add_argument("--priority", choices=PRIORITIES, help="Filter by priority")
    lst.add_argument("--tag", help="Filter by tag")

    _command(sub, "show", "Show a task with all fields and subtasks", task_id=True, dry_run=False)

    add = _command(sub, "add", "Add a new task")
    add.add_argument("title", help="Task title")
    add.add_argument("--id", help="Custom task ID (generated from the title if omitted)")
    add.add_argument("--parent", help="Parent task ID (creates a subtask)")
    _add_field_args(add, update=False)

    upd = _command(sub, "update", "Update a task's fields", task_id=True)
    upd.add_argument("--new-id", help="Rename the task ID (rewrites depends_on references)")
    upd.add_argument("--title", help="New task title")
    upd.add_argument("--created", help="Created timestamp, ISO 8601 with time zone (empty string to clear)")
    _add_field_args(upd, update=True)

    _command(sub, "done", "Mark a task done and stamp its completion time", task_id=True)
    _command(sub, "start", "Mark a task in_progress", task_id=True)

    rem = _command(sub, "remove", "Remove a task", task_id=True)
    rem.add_argument("--recursive", action="store_true", help="Also remove its subtasks")

    mov = _command(sub, "move", "Move a task to a new parent or to root", task_id=True)
    mov.add_argument("--parent", help="New parent task ID")
    mov.add_argument("--root", action="store_true", help="Move the task to root level")

    _command(sub, "clean", "Remove completed tasks and prune dependencies")

    meta = _command(sub, "meta", "Show or update the meta section", dry_run=False)
    meta.add_argument("--show", action="store_true", help="Show the meta section")
    meta.add_argument("--title", help="Set meta title (empty string to clear)")
    meta.add_argument("--created", help="Set meta created timestamp (empty string to clear)")
    return parser


def _command(
    sub: argparse._SubParsersAction, name: str, help_text: str,  # type: ignore
    task_id: bool = False, dry_run: bool = True,
) -> argparse.ArgumentParser:
    """Add a subcommand with the options every command shares."""
    cmd = sub.add_parser(name, help=help_text, description=help_text)
    if task_id:
        cmd.add_argument("task_id", help="Task ID")
    cmd.add_argument("--file", type=Path, help="Path to the todos YAML file (default: $TODOS_FILE or todos.yaml)")
    if dry_run:
        cmd.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    return cmd


def _add_field_args(cmd: argparse.ArgumentParser, update: bool) -> None:
    """Add the task field flags shared by add and update.

    Both commands store list values under add_<field>, so they share one mutation path.
    """
    clear = " (empty string to clear)" if update else ""
    cmd.add_argument("--status", choices=STATUSES, help="Task status")
    cmd.add_argument("--priority", choices=PRIORITIES, help="Task priority")
    cmd.add_argument("--description", help=f"Task description{clear}")
    cmd.add_argument("--blocked-reason", help=f"Reason the task is blocked; sets status to blocked{clear}")
    cmd.add_argument("--due", help=f"Due date, YYYY-MM-DD{clear}")
    cmd.add_argument("--assignee-kind", choices=ASSIGNEE_KINDS,
                     help="Assignee kind" + ("; omit to edit the current assignee" if update else ""))
    cmd.add_argument("--assignee-name", help=f"Human assignee name{clear}")
    cmd.add_argument("--agent-type", help="Agent type (required for an agent assignee)")
    cmd.add_argument("--requires-human-review", action=argparse.BooleanOptionalAction,
                     help="Whether an agent task requires human review")

    for flag, label in _LIST_FIELDS:
        dest = "add_" + flag.replace("-", "_")
        if update:
            cmd.add_argument(f"--add-{flag}", dest=dest, nargs="+", help=f"Add {label}")
            cmd.add_argument(f"--remove-{flag}", nargs="+", help=f"Remove {label}")
            cmd.add_argument(f"--clear-{flag}", action="store_true", help=f"Clear all {label}")
        else:
            cmd.add_argument(f"--{flag}", dest=dest, nargs="+", help=f"List of {label}")

    if update:
        cmd.add_argument("--clear-priority", action="store_true", help="Remove the priority")
        cmd.add_argument("--clear-assignee", action="store_true", help="Remove the assignee")
        cmd.add_argument("--add-file", nargs="+", help=f"Add file entries, each {_FILE_SPEC}")
        cmd.add_argument("--remove-file", nargs="+", help="Remove file entries by path")
        cmd.add_argument("--clear-files", action="store_true", help="Remove all file entries")
    else:
        cmd.add_argument("--files", dest="add_file", nargs="+", help=f"File entries, each {_FILE_SPEC}")
    cmd.add_argument("--file-op", action="append", metavar="PATH=OP", help="Change a file entry's op")
    cmd.add_argument("--file-reason", action="append", metavar="PATH=TEXT",
                     help="Set a file entry's reason (empty TEXT clears)")
    cmd.add_argument("--file-renamed-to", action="append", metavar="PATH=NEW",
                     help="Set a file entry's renamed_to path (empty NEW clears)")
