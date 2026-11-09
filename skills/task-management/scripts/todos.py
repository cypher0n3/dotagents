#!/usr/bin/env python3
"""YAML todos management CLI with full CRUD + subtask operations.

This module provides a command-line interface for managing structured task lists
in YAML format. It supports full CRUD operations on tasks and subtasks while
maintaining comment preservation and schema validation.

Commands:
    list: Display open tasks filtered by assignee kind (all/human/agent/unassigned)
    show: Display a single task with its subtasks in tree format
    add: Create a new task at root level or as a subtask (auto-generates IDs)
    update: Modify task fields (status, priority, title, description, etc.)
    done: Shortcut to mark a task as done (sets status and adds completed timestamp)
    start: Shortcut to mark a task as in_progress
    remove: Delete a task by ID (with --recursive for tasks with subtasks)
    move: Reparent a task to a new parent or move it to root level
    clean: Remove completed tasks and prune stale dependency references

Features:
    - Schema validation before all writes using JSON Schema draft 2020-12
    - Comment preservation via ruamel.yaml
    - Atomic file writes with permission preservation
    - Auto-generated task IDs from titles if not provided
    - Recursive subtask support with conservative cleanup
    - Dependency management with automatic pruning on task removal
    - Dry-run mode for all destructive operations

File Format:
    Tasks are stored in YAML with a todos array. Only the title field is required.
    All other fields (id, status, priority, assignee, depends_on, subtasks, etc.)
    are optional. The schema supports extension fields for custom metadata.

Examples:
    python3 todos.py list human
    python3 todos.py add "Fix bug" --priority high --assignee-kind human
    python3 todos.py add "Subtask" --parent task-1
    python3 todos.py update task-1 --status in_progress
    python3 todos.py done task-1
    python3 todos.py remove task-1 --recursive
    python3 todos.py move subtask-1 --root
    python3 todos.py clean --dry-run

Dependencies:
    - ruamel.yaml >= 0.18 for comment-preserving YAML handling
    - jsonschema >= 4.20 for schema validation

Architecture:
    The module is organized into layers:
    - YAML I/O functions for comment-preserving file operations
    - Schema validation with JSON Schema support
    - Core CRUD operations on task trees
    - CLI argument parsing and command dispatch
    - Helper functions for ID generation and tree traversal

All write operations follow a validate-then-write pattern with atomic file
replacement to prevent data loss. The schema allows extension fields so users
can add custom metadata without breaking validation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML
except ImportError:
    print(
        "Error: ruamel.yaml is required for comment-preserving YAML handling.\n"
        "Install with: pip install -r skills/task-management/requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import jsonschema
except ImportError:
    print(
        "Error: jsonschema is required for schema validation.\n"
        "Install with: pip install -r skills/task-management/requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


@dataclass
class Todo:
    """Parsed todo item with normalized fields."""
    id: str
    title: str
    status: str
    priority: str
    assignee_kind: str
    assignee_display: str
    created: datetime | None
    blocked_reason: str | None
    raw: dict[str, Any]


def setup_yaml() -> YAML:
    """Set up YAML parser with comment preservation."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096
    return yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file preserving comments."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    yaml = setup_yaml()
    return yaml.load(content)


def dump_yaml(data: dict[str, Any], path: Path) -> None:
    """Write YAML file preserving comments."""
    yaml = setup_yaml()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def serialize_for_validation(obj: Any) -> Any:
    """Convert objects to JSON-serializable form for schema validation."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize_for_validation(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_for_validation(item) for item in obj]
    return obj


def validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    """Validate data against JSON Schema."""
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    serialized = serialize_for_validation(data)

    try:
        jsonschema.validate(serialized, schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Schema validation failed: {e.message}") from e


def parse_datetime(value: Any) -> datetime | None:
    """Parse datetime from various formats including YAML datetime objects."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, str):
        for fmt in [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(value, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    return None


def parse_todo(raw: dict[str, Any]) -> Todo:
    """Parse raw todo dict into normalized Todo object."""
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

    priority = raw.get("priority", "medium")
    created = parse_datetime(raw.get("created"))

    return Todo(
        id=raw.get("id", ""),
        title=raw["title"],
        status=raw.get("status", "pending"),
        priority=priority,
        assignee_kind=kind,
        assignee_display=display,
        created=created,
        blocked_reason=raw.get("blocked_reason"),
        raw=raw,
    )


def priority_sort_key(priority: str) -> int:
    """Return sort key for priority (lower is more urgent)."""
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return order.get(priority, 2)


def validate_todos_structure(data: dict[str, Any]) -> None:
    """Validate todos structure and check for duplicate IDs."""
    if "todos" not in data:
        raise ValueError("Missing 'todos' array in YAML structure")

    ids_seen = set()

    def check_task(task: dict[str, Any], path: str = "root") -> None:
        """Recursively check task and subtasks for duplicate IDs."""
        if "id" in task:
            task_id = task["id"]
            if task_id in ids_seen:
                raise ValueError(f"Duplicate todo ID: {task_id}")
            ids_seen.add(task_id)

        if "subtasks" in task:
            for idx, subtask in enumerate(task["subtasks"]):
                check_task(subtask, f"{path}.subtasks[{idx}]")

    for idx, todo in enumerate(data["todos"]):
        check_task(todo, f"todos[{idx}]")


def load_and_validate_file(file_path: Path) -> dict[str, Any] | int:
    """Load and validate YAML file, return data or error code."""
    try:
        data = load_yaml(file_path)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error loading YAML: {e}", file=sys.stderr)
        return 1

    try:
        validate_todos_structure(data)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return data


def write_data(data: dict[str, Any], file_path: Path, validate_after: bool = True) -> int:
    """Write data atomically with optional validation, return exit code."""
    if validate_after:
        skill_dir = Path(__file__).parent.parent
        schema_path = skill_dir / "assets" / "todos-schema.json"
        try:
            validate_schema(data, schema_path)
            validate_todos_structure(data)
        except ValueError as e:
            print(f"Error: Validation failed: {e}", file=sys.stderr)
            print("Changes not written to preserve file integrity.", file=sys.stderr)
            return 1

    real_path = file_path.resolve()

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=real_path.parent,
            prefix=f".{real_path.name}.",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp_path = Path(tmp.name)
            try:
                dump_yaml(data, tmp_path)
                tmp_path.chmod(real_path.stat().st_mode)
                tmp_path.replace(real_path)
                return 0
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error writing file: {e}", file=sys.stderr)
        return 1


def find_task_by_id(tasks: list[dict[str, Any]], task_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Find task by ID recursively, return (task, parent_subtasks_list) or None."""
    for task in tasks:
        if task.get("id") == task_id:
            return (task, tasks)
        if "subtasks" in task:
            result = find_task_by_id(task["subtasks"], task_id)
            if result:
                return result
    return None


def collect_all_ids(tasks: list[dict[str, Any]]) -> set[str]:
    """Collect all task IDs recursively."""
    ids = set()
    for task in tasks:
        if "id" in task:
            ids.add(task["id"])
        if "subtasks" in task:
            ids.update(collect_all_ids(task["subtasks"]))
    return ids


def generate_id(title: str, existing_ids: set[str]) -> str:
    """Generate a unique ID from title."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base[:30] if base else "task"

    candidate = base
    counter = 1
    while candidate in existing_ids:
        candidate = f"{base}-{counter}"
        counter += 1

    return candidate


def print_task_tree(task: dict[str, Any], indent: int = 0, show_subtasks: bool = True) -> None:
    """Print task with optional subtasks in tree format."""
    todo = parse_todo(task)
    prefix = "  " * indent
    status_marker = "⚠" if todo.status == "blocked" else "○"

    print(f"{prefix}{status_marker} [{todo.priority:8}] {todo.status:12} {todo.id:20} ({todo.assignee_display})")
    print(f"{prefix}  {todo.title}")
    if todo.blocked_reason:
        print(f"{prefix}  BLOCKED: {todo.blocked_reason}")

    if show_subtasks and "subtasks" in task:
        for subtask in task["subtasks"]:
            print()
            print_task_tree(subtask, indent + 1)


def _collect_open_tasks(
    tasks: list[dict[str, Any]], kind_filter: str, open_statuses: set[str], todos: list[Todo]
) -> None:
    """Recursively collect open tasks matching filter."""
    for raw in tasks:
        try:
            todo = parse_todo(raw)
        except KeyError as e:
            print(f"Warning: Skipping todo missing required field {e}", file=sys.stderr)
            continue

        is_open = todo.status in open_statuses

        matches_filter = (
            kind_filter == "all"
            or (kind_filter == "human" and todo.assignee_kind == "human")
            or (kind_filter == "agent" and todo.assignee_kind == "agent")
            or (kind_filter == "unassigned" and todo.assignee_kind == "unassigned")
        )

        if is_open and matches_filter:
            todos.append(todo)

        if "subtasks" in raw and is_open:
            _collect_open_tasks(raw["subtasks"], kind_filter, open_statuses, todos)


def list_todos(file_path: Path, kind_filter: str) -> int:
    """List open todos filtered by assignee kind."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    open_statuses = {"pending", "in_progress", "blocked"}
    todos: list[Todo] = []

    _collect_open_tasks(data["todos"], kind_filter, open_statuses, todos)

    todos.sort(key=lambda t: (
        priority_sort_key(t.priority),
        t.created if t.created else datetime.max.replace(tzinfo=timezone.utc),
        t.id,
    ))

    if not todos:
        print(f"No open todos found (filter: {kind_filter})")
        return 0

    print(f"Open todos (filter: {kind_filter}):\n")
    for todo in todos:
        status_marker = "⚠" if todo.status == "blocked" else "○"
        print(f"{status_marker} [{todo.priority:8}] {todo.status:12} {todo.id:20} ({todo.assignee_display})")
        print(f"  {todo.title}")
        if todo.blocked_reason:
            print(f"  BLOCKED: {todo.blocked_reason}")
        print()

    return 0


def show_todo(file_path: Path, task_id: str) -> int:
    """Show a single task with its subtasks."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found", file=sys.stderr)
        return 1

    task, _ = task_result
    print_task_tree(task, show_subtasks=True)
    return 0


def add_todo(file_path: Path, args: argparse.Namespace, dry_run: bool = False) -> int:
    """Add a new task."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    existing_ids = collect_all_ids(data["todos"])

    task_id = args.id if args.id else generate_id(args.title, existing_ids)

    if task_id in existing_ids:
        print(f"Error: Task ID '{task_id}' already exists", file=sys.stderr)
        return 1

    new_task: dict[str, Any] = {
        "id": task_id,
        "title": args.title,
    }

    if args.status:
        new_task["status"] = args.status
    if args.priority:
        new_task["priority"] = args.priority
    if args.description:
        new_task["description"] = args.description

    if args.assignee_kind:
        assignee: dict[str, Any] = {"kind": args.assignee_kind}
        if args.assignee_kind == "human" and args.assignee_name:
            assignee["name"] = args.assignee_name
        elif args.assignee_kind == "agent":
            if not args.agent_type:
                print("Error: --agent-type required for agent assignee", file=sys.stderr)
                return 1
            assignee["agent_type"] = args.agent_type
        new_task["assignee"] = assignee

    if args.depends_on:
        new_task["depends_on"] = args.depends_on

    if args.parent:
        parent_result = find_task_by_id(data["todos"], args.parent)
        if not parent_result:
            print(f"Error: Parent task '{args.parent}' not found", file=sys.stderr)
            return 1

        parent_task, _ = parent_result
        if "subtasks" not in parent_task:
            parent_task["subtasks"] = []
        parent_task["subtasks"].append(new_task)
        location = f"as subtask of {args.parent}"
    else:
        data["todos"].append(new_task)
        location = "at root level"

    if dry_run:
        print(f"Dry run: would add task '{task_id}' {location}")
        return 0

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Added task '{task_id}' {location}")
    return result_code


def update_todo(file_path: Path, task_id: str, args: argparse.Namespace, dry_run: bool = False) -> int:
    """Update an existing task."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found", file=sys.stderr)
        return 1

    task, _ = task_result
    updates = []

    if args.title:
        task["title"] = args.title
        updates.append(f"title='{args.title}'")
    if args.status:
        task["status"] = args.status
        updates.append(f"status={args.status}")
        if args.status == "done" and "completed" not in task:
            task["completed"] = datetime.now(timezone.utc).isoformat()
            updates.append("completed=now")
    if args.priority:
        task["priority"] = args.priority
        updates.append(f"priority={args.priority}")
    if args.description is not None:
        if args.description:
            task["description"] = args.description
            updates.append(f"description='{args.description}'")
        elif "description" in task:
            del task["description"]
            updates.append("description removed")
    if args.blocked_reason is not None:
        if args.blocked_reason:
            task["blocked_reason"] = args.blocked_reason
            task["status"] = "blocked"
            updates.append(f"blocked_reason='{args.blocked_reason}'")
        elif "blocked_reason" in task:
            del task["blocked_reason"]
            updates.append("blocked_reason removed")

    if not updates:
        print("No updates specified")
        return 0

    if dry_run:
        print(f"Dry run: would update task '{task_id}': {', '.join(updates)}")
        return 0

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Updated task '{task_id}': {', '.join(updates)}")
    return result_code


def remove_todo(file_path: Path, task_id: str, recursive: bool = False, dry_run: bool = False) -> int:
    """Remove a task by ID."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found", file=sys.stderr)
        return 1

    task, parent_list = task_result

    if "subtasks" in task and task["subtasks"] and not recursive:
        print(f"Error: Task '{task_id}' has subtasks. Use --recursive to remove task and subtasks.", file=sys.stderr)
        return 1

    if dry_run:
        subtask_note = f" and {len(task.get('subtasks', []))} subtask(s)" if recursive and "subtasks" in task else ""
        print(f"Dry run: would remove task '{task_id}'{subtask_note}")
        return 0

    parent_list.remove(task)

    def prune_deps(tasks: list[dict[str, Any]]) -> None:
        """Recursively prune dependency references."""
        for t in tasks:
            if "depends_on" in t:
                t["depends_on"] = [dep for dep in t["depends_on"] if dep != task_id]
                if not t["depends_on"]:
                    del t["depends_on"]
            if "subtasks" in t:
                prune_deps(t["subtasks"])

    prune_deps(data["todos"])

    result_code = write_data(data, file_path)
    if not result_code:
        subtask_note = f" and {len(task.get('subtasks', []))} subtask(s)" if recursive and "subtasks" in task else ""
        print(f"Removed task '{task_id}'{subtask_note}")
    return result_code


def _cleanup_empty_subtasks(tasks: list[dict[str, Any]]) -> None:
    """Remove empty subtasks arrays recursively."""
    for t in tasks:
        if "subtasks" in t and not t["subtasks"]:
            del t["subtasks"]
        elif "subtasks" in t:
            _cleanup_empty_subtasks(t["subtasks"])


def move_todo(
    file_path: Path, task_id: str, parent_id: str | None, to_root: bool = False, dry_run: bool = False
) -> int:
    """Move a task to a new parent or to root."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    if not to_root and not parent_id:
        print("Error: Must specify --parent or --root", file=sys.stderr)
        return 1

    if to_root and parent_id:
        print("Error: Cannot specify both --parent and --root", file=sys.stderr)
        return 1

    task_result = find_task_by_id(data["todos"], task_id)
    if not task_result:
        print(f"Error: Task '{task_id}' not found", file=sys.stderr)
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
            print(f"Error: Parent task '{parent_id}' not found", file=sys.stderr)
            return 1

        parent_task, _ = parent_result

        if "subtasks" in parent_task:
            if any(st.get("id") == task_id for st in parent_task["subtasks"]):
                print(f"Task '{task_id}' is already a subtask of '{parent_id}'")
                return 0
        else:
            parent_task["subtasks"] = []

        if dry_run:
            print(f"Dry run: would move task '{task_id}' to be subtask of '{parent_id}'")
            return 0

        old_parent_list.remove(task)
        parent_task["subtasks"].append(task)
        _cleanup_empty_subtasks(data["todos"])
        location = f"subtask of {parent_id}"

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"Moved task '{task_id}' to {location}")
    return result_code


def prune_dependencies(remaining: list[dict[str, Any]], done_ids: set[str]) -> list[tuple[str, list[str]]]:
    """Prune stale dependency references recursively, return list of pruned items."""
    pruned_deps = []

    def prune_task(task: dict[str, Any]) -> None:
        """Recursively prune dependencies in task and subtasks."""
        if "depends_on" in task:
            original_deps = task["depends_on"]
            new_deps = [dep for dep in original_deps if dep not in done_ids]
            if len(new_deps) < len(original_deps):
                removed = set(original_deps) - set(new_deps)
                task_id = task.get("id", "unknown")
                pruned_deps.append((task_id, sorted(removed)))
                task["depends_on"] = new_deps

        if "subtasks" in task:
            for subtask in task["subtasks"]:
                prune_task(subtask)

    for task in remaining:
        prune_task(task)

    return pruned_deps


def _process_task_for_clean(task: dict[str, Any], done_ids: set[str]) -> dict[str, Any] | None:
    """Process task recursively, removing done tasks, keeping parents with open children."""
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
    elif "subtasks" in task and not cleaned_subtasks:
        del task["subtasks"]

    return task


def clean_todos(file_path: Path, dry_run: bool) -> int:
    """Remove completed todos and prune stale dependencies."""
    result = load_and_validate_file(file_path)
    if isinstance(result, int):
        return result
    data = result

    done_ids: set[str] = set()
    cleaned_tasks: list[dict[str, Any]] = []

    for task in data["todos"]:
        cleaned = _process_task_for_clean(task, done_ids)
        if cleaned:
            cleaned_tasks.append(cleaned)
        elif task.get("id"):
            done_ids.add(task["id"])

    if not done_ids:
        print("No completed todos to remove.")
        return 0

    print(f"Found {len(done_ids)} completed todo(s) to remove:")
    for todo_id in sorted(done_ids):
        print(f"  - {todo_id}")

    pruned_deps = prune_dependencies(cleaned_tasks, done_ids)

    if pruned_deps:
        print(f"\nPruning {len(pruned_deps)} dependency reference(s):")
        for todo_id, removed_ids in pruned_deps:
            print(f"  {todo_id}: removed {', '.join(removed_ids)}")

    if dry_run:
        print(f"\nDry run: would remove {len(done_ids)} todo(s) and keep {len(cleaned_tasks)} (no changes written)")
        return 0

    data["todos"] = cleaned_tasks

    if "meta" in data and "updated" in data["meta"]:
        data["meta"]["updated"] = datetime.now(timezone.utc).isoformat()

    result_code = write_data(data, file_path)
    if not result_code:
        print(f"\nRemoved {len(done_ids)} completed todo(s), {len(cleaned_tasks)} remaining.")
    return result_code


def _setup_arg_parser() -> argparse.ArgumentParser:
    """Set up argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="YAML todos management CLI with full CRUD + subtask operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run 'todos.py COMMAND --help' for detailed command usage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")
    _add_list_parser(subparsers)
    _add_show_parser(subparsers)
    _add_add_parser(subparsers)
    _add_update_parser(subparsers)
    _add_done_parser(subparsers)
    _add_start_parser(subparsers)
    _add_remove_parser(subparsers)
    _add_move_parser(subparsers)
    _add_clean_parser(subparsers)
    return parser


def _add_list_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add list subcommand parser."""
    list_parser = subparsers.add_parser("list", help="List open todos filtered by assignee")
    list_parser.add_argument("kind", nargs="?", default="all", choices=["all", "human", "agent", "unassigned"])
    list_parser.add_argument("--file", type=Path)


def _add_show_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add show subcommand parser."""
    show_parser = subparsers.add_parser("show", help="Show a task with its subtasks")
    show_parser.add_argument("task_id")
    show_parser.add_argument("--file", type=Path)


def _add_add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add add subcommand parser."""
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("title")
    add_parser.add_argument("--file", type=Path)
    add_parser.add_argument("--id")
    add_parser.add_argument("--status", choices=["pending", "in_progress", "blocked", "done", "cancelled"])
    add_parser.add_argument("--priority", choices=["low", "medium", "high", "critical"])
    add_parser.add_argument("--description")
    add_parser.add_argument("--assignee-kind", choices=["human", "agent"])
    add_parser.add_argument("--assignee-name")
    add_parser.add_argument("--agent-type")
    add_parser.add_argument("--depends-on", nargs="+")
    add_parser.add_argument("--parent")
    add_parser.add_argument("--dry-run", action="store_true")


def _add_update_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add update subcommand parser."""
    update_parser = subparsers.add_parser("update", help="Update an existing task")
    update_parser.add_argument("task_id")
    update_parser.add_argument("--file", type=Path)
    update_parser.add_argument("--title")
    update_parser.add_argument("--status", choices=["pending", "in_progress", "blocked", "done", "cancelled"])
    update_parser.add_argument("--priority", choices=["low", "medium", "high", "critical"])
    update_parser.add_argument("--description")
    update_parser.add_argument("--blocked-reason")
    update_parser.add_argument("--dry-run", action="store_true")


def _add_done_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add done subcommand parser."""
    done_parser = subparsers.add_parser("done", help="Mark task as done")
    done_parser.add_argument("task_id")
    done_parser.add_argument("--file", type=Path)


def _add_start_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add start subcommand parser."""
    start_parser = subparsers.add_parser("start", help="Mark task as in_progress")
    start_parser.add_argument("task_id")
    start_parser.add_argument("--file", type=Path)


def _add_remove_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add remove subcommand parser."""
    remove_parser = subparsers.add_parser("remove", help="Remove a task")
    remove_parser.add_argument("task_id")
    remove_parser.add_argument("--file", type=Path)
    remove_parser.add_argument("--recursive", action="store_true")
    remove_parser.add_argument("--dry-run", action="store_true")


def _add_move_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add move subcommand parser."""
    move_parser = subparsers.add_parser("move", help="Move a task to a new parent or root")
    move_parser.add_argument("task_id")
    move_parser.add_argument("--file", type=Path)
    move_parser.add_argument("--parent")
    move_parser.add_argument("--root", action="store_true")
    move_parser.add_argument("--dry-run", action="store_true")


def _add_clean_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore
    """Add clean subcommand parser."""
    clean_parser = subparsers.add_parser("clean", help="Remove completed todos and prune dependencies")
    clean_parser.add_argument("--file", type=Path)
    clean_parser.add_argument("--dry-run", action="store_true")


def main() -> int:
    """Main entry point."""
    parser = _setup_arg_parser()
    args = parser.parse_args()
    file_path = args.file if args.file else Path(os.environ.get("TODOS_FILE", "todos.yaml"))

    if args.command == "list":
        return list_todos(file_path, args.kind)
    if args.command == "show":
        return show_todo(file_path, args.task_id)
    if args.command == "add":
        return add_todo(file_path, args, args.dry_run)
    if args.command == "update":
        return update_todo(file_path, args.task_id, args, args.dry_run)
    if args.command == "done":
        dummy_args = argparse.Namespace(
            title=None, status="done", priority=None, description=None, blocked_reason=None
        )
        return update_todo(file_path, args.task_id, dummy_args, dry_run=False)
    if args.command == "start":
        dummy_args = argparse.Namespace(
            title=None, status="in_progress", priority=None, description=None, blocked_reason=None
        )
        return update_todo(file_path, args.task_id, dummy_args, dry_run=False)
    if args.command == "remove":
        return remove_todo(file_path, args.task_id, args.recursive, args.dry_run)
    if args.command == "move":
        return move_todo(file_path, args.task_id, args.parent, args.root, args.dry_run)
    if args.command == "clean":
        return clean_todos(file_path, args.dry_run)
    return 1


if __name__ == "__main__":
    sys.exit(main())
