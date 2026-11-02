---
name: update-todos
description: Update the step and todo status of a Cursor, Claude Code, or Xorc plan. Invoke only when explicitly called by user.
user-invocable: true
disable-model-invocation: false
---
# Update Todos

Reconcile a plan's recorded step status with the work actually done.

## Identify the Plan Type

Each kind of plan keeps its status in a different place.

- Cursor: a `.plan.md` file whose checkboxes and YAML `todos[].status` must agree in count, order, and meaning.
- Claude Code: a Markdown file with no frontmatter, whose `- [ ]` / `- [x]` checklist is the record.
- Xorc: a `.xorcp.md` artifact whose task state only Xorc's native plan tools may read and change.

If the plan matches none of these, or the signals conflict, ask which it is.
Never translate one kind's status into another's.

## Check Each Step

Read the whole plan, then check each step against evidence such as commits, changed files, and the output of the commands it names.
Mark a step complete only from observed evidence, never report a planned test as passed, and report rather than silently uncheck a completed step whose result no longer holds.

## Update the Status

- Cursor: change each checkbox and its `todos[].status` in the same edit, and the Cursor agent todos when they are in use.
- Claude Code: change the checkbox lines in the plan file; the session task list may mirror them.
- Xorc: read the plan and its version, then record status, through the native tools only, without hand-editing the file or forcing a lifecycle state.
  If those tools are unavailable or cannot represent the change, report that and stop.

## Finish

Move a fully complete Cursor or Claude Code plan to the repository's folder for finished plans, if it has one.
Report each step whose status changed with its evidence, and each step whose status could not be confirmed.
If unsure, stop and ask.
