---
name: update-todos
description: Update the step and todo status of a Cursor, Claude Code, or Xorc plan. Invoke only when explicitly called by user.
user-invocable: true
disable-model-invocation: false
---
# Update Todos

Reconcile a plan's recorded step status with the work actually done.
Invoke this workflow only when explicitly requested by the user.

## Identify the Plan Type

Work out which kind of plan it is before changing anything, because each kind keeps its status in a different place.

- A Cursor plan is a `.plan.md` file whose YAML frontmatter carries `name`, `overview`, and `todos`.
- A Claude Code plan is a Markdown file with no frontmatter, whose `- [ ]` / `- [x]` checklist is the record of the work.
- An Xorc plan is a `.xorcp.md` artifact whose task state is owned by Xorc's native plan tools.

If the plan matches none of these, or the signals conflict, stop and ask which kind it is.
Never convert one kind's status into another's, such as Xorc task state into Cursor `todos`.

## Check Each Step

Read the whole plan first.
For each step, check the evidence for its status, such as commits, changed files, and the results of the commands the step names.
Mark a step complete only from observed evidence, and never report a planned test as passed.
A completed step whose result no longer holds is a finding to report, not something to uncheck silently.

## Update the Status

- For a Cursor plan, update each checkbox under `## Execution Plan` and the matching `todos[].status` together, so both still agree in count, order, and meaning.
  Update the Cursor agent todos to match when they are in use.
- For a Claude Code plan, update each checkbox line in the plan file.
  The session task list may be updated to match, but the plan file stays the record.
- For an Xorc plan, read the plan and its version through Xorc's native inspection tools and record status only through its native update tools.
  Do not edit the `.xorcp.md` file by hand or force a lifecycle state.
  If the native tools are unavailable or cannot represent the change, report that and stop.

## Finish

If a Cursor or Claude Code plan is fully complete, move it to the folder the repository keeps for finished plans, if it has one.
Report which steps changed status, the evidence for each, and any step whose status could not be confirmed.
If unsure, stop and ask.
