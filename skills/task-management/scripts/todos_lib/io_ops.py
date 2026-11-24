"""Loading, validating, and atomically writing the todos file."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

INSTALL_HINT = "Install with: pip install -r skills/task-management/requirements.txt"
SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "todos-schema.json"

try:
    from ruamel.yaml import YAML
except ImportError:
    print(f"Error: ruamel.yaml is required.\n{INSTALL_HINT}", file=sys.stderr)
    sys.exit(1)

try:
    import jsonschema
except ImportError:
    print(f"Error: jsonschema is required.\n{INSTALL_HINT}", file=sys.stderr)
    sys.exit(1)


def setup_yaml() -> YAML:
    """Return a round-trip YAML handler that keeps comments, quotes, and long lines intact."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096  # Never wrap long titles or descriptions.
    return yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, keeping its comments for the next write."""
    with open(path, encoding="utf-8") as f:
        return setup_yaml().load(f)


def dump_yaml(data: dict[str, Any], path: Path) -> None:
    """Write data to path as YAML, keeping any loaded comments."""
    with open(path, "w", encoding="utf-8") as f:
        setup_yaml().dump(data, f)


def serialize_for_validation(obj: Any) -> Any:
    """Turn the dates and datetimes YAML loads into ISO strings, which is what the JSON Schema expects."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize_for_validation(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_for_validation(item) for item in obj]
    return obj


def validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    """Raise ValueError if data does not match the JSON Schema at schema_path."""
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(serialize_for_validation(data), schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Schema validation failed: {e.message}") from e


def validate_todos_structure(data: dict[str, Any]) -> None:
    """Raise ValueError if the todos list is missing or two tasks share an ID."""
    if "todos" not in data:
        raise ValueError("Missing 'todos' array in YAML structure")
    ids_seen = set()

    def check_task(task: dict[str, Any]) -> None:
        if "id" in task:
            task_id = task["id"]
            if task_id in ids_seen:
                raise ValueError(f"Duplicate todo ID: {task_id}")
            ids_seen.add(task_id)
        if "subtasks" in task:
            for subtask in task["subtasks"]:
                check_task(subtask)

    for todo in data["todos"]:
        check_task(todo)


def load_and_validate_file(file_path: Path) -> dict[str, Any] | int:
    """Load and check the file; return its data, or print the error and return exit code 1."""
    try:
        data = load_yaml(file_path)
        validate_todos_structure(data)
        return data
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error loading YAML: {e}", file=sys.stderr)
        return 1


def write_data(data: dict[str, Any], file_path: Path, validate_after: bool = True) -> int:
    """Validate data, then write it atomically; return 0, or print the error and return 1.

    The data goes to a temporary file beside the target, takes the target's permissions,
    and replaces it in one rename, so a failed write never leaves a partial file.
    """
    if validate_after:
        try:
            validate_schema(data, SCHEMA_PATH)
            validate_todos_structure(data)
        except ValueError as e:
            print(f"Error: Validation failed: {e}", file=sys.stderr)
            print("Changes not written to preserve file integrity.", file=sys.stderr)
            return 1

    real_path = file_path.resolve()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=real_path.parent, prefix=f".{real_path.name}.",
            suffix=".tmp", delete=False, encoding="utf-8",
        ) as tmp:
            tmp_path = Path(tmp.name)
            try:
                dump_yaml(data, tmp_path)
                tmp_path.chmod(real_path.stat().st_mode if real_path.exists() else _new_file_mode())
                tmp_path.replace(real_path)
                return 0
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error writing file: {e}", file=sys.stderr)
        return 1


def _new_file_mode() -> int:
    """Return the mode a newly created file gets under the current umask."""
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def get_default_path() -> Path:
    """Return $TODOS_FILE, or todos.yaml in the current directory."""
    return Path(os.environ.get("TODOS_FILE", "todos.yaml"))
