---
name: update-cursor-todos
description: Update Cursor plan and agent todo items. Invoke only when explicitly called by user.
user-invocable: true
disable-model-invocation: false
---
# Update Cursor Todos

Use this skill only for Cursor plan files and Cursor agent todo state.
Do not apply it to CAI `.caip.md` plans, translate their task states into Cursor todos, or claim to synchronize CAI through Cursor tools.
If the request targets CAI, stop this workflow and use CAI's native plan inspection and update tools instead.

Review the plan and Cursor todos, validate the status of each, then update each with its observed status.

If a plan is fully complete, move it to appropriate folder if one is available.
If unsure, stop and ask.
