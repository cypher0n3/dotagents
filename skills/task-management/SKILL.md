---
name: task-management
description: Manage structured task lists with human and agent assignees, priorities, dependencies. Use for standalone project planning, not execution plan updates.
---

# Task Management

Use this skill to track project tasks and deliverables with structured YAML task lists.
Do not use this for Cursor/Claude/Xorc execution plans; use `update-todos` for those.
For creating execution plans, see `detailed-execution-planner`.

Store the todos file in `.agents/todos.yaml` or `.claude/todos.yaml` within the repo.
For multi-repo work, use a dedicated meta repo.
Point the CLI at the file with `--file PATH` or set `$TODOS_FILE`.
Commit the file alongside related changes.

Change the task list only through the CLI; never edit the YAML file directly.
The CLI validates before writing, preserving file integrity.

Run `python3 scripts/todos.py list [all|human|agent|unassigned] --file PATH` to list open tasks.
Run `python3 scripts/todos.py add "Task title" --file PATH` to add a task.
Run `python3 scripts/todos.py done TASK_ID --file PATH` to mark a task done.
Run `python3 scripts/todos.py --help` for all commands and `COMMAND --help` for options.

Install dependencies with `pip install -r requirements.txt` (requires ruamel.yaml>=0.18, jsonschema>=4.20).

See `assets/todos-example.yaml` for an example and `assets/todos-schema.json` for the JSON Schema specification.
