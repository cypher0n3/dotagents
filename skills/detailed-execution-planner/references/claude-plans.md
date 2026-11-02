# Claude Code Planning Workflow

## Plan Artifact

Claude Code has no plan import format, so a Claude plan is a plain Markdown file whose checklist is the record of the work.
Write it with the task shape, flat checklist, explicit step wording, and test gates that `SKILL.md` requires for every plan.
Start from [`assets/plan-template.md`](../assets/plan-template.md) but drop its YAML frontmatter, so the file opens at the `# [Plan Title]` heading.
Do not add Cursor `name`, `overview`, or `todos` fields, or native Xorc fields, to a Claude plan.

## Plan Location

Save the plan where the user asks.
Otherwise follow the repository's own convention for plan files, found in its instructions or an existing plans directory.
In plan mode, write the plan to the plan file the harness names, because plan mode allows no other writes.
With none of those, ask where the plan belongs rather than inventing a directory.

## Approval

Finishing a plan in plan mode means presenting it for approval through the plan-mode exit tool.
Do not describe a written plan as approved until the user approves it, and do not start executing it in the same turn unless the user asked for that.

## Task List

Claude Code's task list tools hold session state that ends with the session, so they do not replace the checklist in the plan file.
Do not create task list entries while writing the plan unless the user asks.
An executor may mirror the current task's steps into the task list while working, but records each completed step by changing its `- [ ]` line in the plan file to `- [x]`, from observed results only.
Do not invoke `update-cursor-todos` for a Claude plan.

## Update an Existing Plan

Read the whole plan file first, keep completed steps checked unless they are now invalid, and change only what is pending or invalidated.
A Claude plan carries no frontmatter to keep in step, so the checklist lines are the only state to update.
