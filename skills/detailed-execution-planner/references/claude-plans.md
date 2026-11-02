# Claude Code Planning Workflow

## Plan Artifact

Claude Code has no plan import format, so a Claude plan is a plain Markdown file whose checklist is the record of the work.
It carries no Cursor or Xorc fields.

## Plan Location

Save the plan where the user asks, or else where the repository's instructions or existing plans directory put plans.
In plan mode, write it to the plan file the harness names, because plan mode allows no other writes.
With none of those, ask rather than inventing a directory.

## Approval

In plan mode, present the finished plan for approval through the plan-mode exit tool.
Do not call a plan approved until the user approves it, or start executing it in the same turn unless asked.

## Task List

Claude Code's task list is session state, not the plan; do not fill it while planning unless the user asks.
An executor may mirror the current task's steps into it, but records each finished step as `- [x]` in the plan file, from observed results only.
`update-todos` reconciles the checklist with the work done.
