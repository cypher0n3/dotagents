---
name: herdr
description: Control Herdr panes, tabs, workspaces, and other agents. Use only when the user mentions Herdr.
user-invocable: true
disable-model-invocation: false
---

# Herdr

Herdr organizes terminals into workspaces, tabs, and panes, recognizes coding agents, and exposes server through `herdr` CLI.

Run `test "${HERDR_ENV:-}" = 1` first; if it fails, say you are not inside Herdr and stop.

Run `herdr --help` or `herdr --skill` for syntax; the binary is authoritative.
Never run bare `herdr`, which launches the TUI, or probe mutating commands by omitting arguments.

Control commands return JSON; `pane read` and `agent read` print plain text.

Read IDs and state from JSON; IDs like `w1`, `w1:t1`, `w1:p1` are opaque stable handles never reused, scoped to one server.

Use pane commands for shells; use agent commands when Herdr must validate agent identity.

Treat `idle` and `done` as ready, `working` as busy, `blocked` as approval or question dialog, `unknown` as unclassified, not finished.

Target agents by pane ID or unique name matching `[a-z][a-z0-9_-]{0,31}`; unnamed agents need pane ID.

Read caller location from `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID`, `HERDR_PANE_ID`; prefer `--current`.

Default to sibling pane in current tab; do not create workspace, tab, worktree, or different working directory unless asked; split wide panes right, narrow or tall down.

Start agent with `herdr agent start` only in existing shell pane at prompt; never creates layout; pass native arguments after `--`.

`herdr agent prompt --wait` waits for first settled state; do not repeat defaults with `--until`; refuses blocked agents; inspect with `herdr agent get` or `herdr agent read` and ask user before answering dialogs.

Timeout or `agent_prompt_stalled` does not prove prompt was never delivered; read agent before resubmitting.

Read with `--source visible`, `recent`, `recent-unwrapped` (best for logs), or `detection`; on alternate screen, ask agent to write response to file.

Xorc reports state, so `herdr agent list`, `herdr agent get`, `herdr agent wait`, and `herdr agent read` work.
Herdr has no `xorc` kind, so `herdr agent prompt` and `herdr agent start` refuse Xorc.
Send Xorc tasks with `python3 scripts/herdr_send.py prompt TARGET --tui xorc --text "TASK" --from-role ROLE`, which delivers via `herdr pane run` after checks.

Expect long-lived sessions, one per role, sharing git checkout; identify role from pane title or agent list, not hard-coded names.

Standard roles are Architect for spec and rules, Implementer for the plan and commits, Validator for re-validation, Griller for grill-me, and Logger for the task log on a smaller model.

Inside Herdr, send to another agent only through `python3 scripts/herdr_send.py`; outside, use the tool's native messaging, such as Claude Code's SendMessage.
Silence is not receipt; confirm delivery when it matters.

Run `python3 scripts/herdr_send.py check TARGET` to verify target is reachable, not blocked, has empty input box.
Run `python3 scripts/herdr_send.py prompt TARGET --text "MESSAGE" --from-role ROLE` to send; it saves the message, retries until the input box reads empty, then sends at once, delivering older saved messages to that target first.
Retries back off from `--interval` (2 s) doubling to 30 s with jitter, for `--wait` seconds (180 for `prompt`, 0 for `check`; `--wait 0` is one attempt); only exits `13`, `14`, `20`, and `21` stop early.
Add `--reply` when expecting answer; `--no-header` only for slash command first; `--disable-working` to refuse working target; `--file PATH` or `-` for file or stdin.
Every command prints one JSON line (`--yaml` for YAML) with `result`, `last_refusal`, `status_at_return`, and `next_step`; read `next_step` before acting.
A timed-out message stays saved and the next `prompt` to that target delivers it, so never resend it; run `pending list [TARGET]` to see saved and dead messages and `pending drop ID` or `pending drop --target TARGET --all` to cancel.
Run `python3 scripts/herdr_send.py run PANE --text "COMMAND"` for shell pane.

Exit `0` means sent or ready.
Exit `10` is unsubmitted input, a missing TUI profile, input frame, or prompt row, or a state change during checks: never clear someone's typed text; a missing profile needs `--tui` or a new profile.
Exit `11` is a blocked dialog still open when the wait ran out: ask the user.
Exit `12` is a working target with `--disable-working`, an `unknown` state, a missing state field, or `interactive_ready` false, still true when the wait ran out: report it.
Exit `13` is a missing, ambiguous, own-pane, wrong-kind, or agent-owned `run` target: fix the target.
Exit `14` means you are not inside Herdr: stop.
Exit `20` is a herdr command failure: inspect the error.
Exit `21` is invalid message text, a missing header part, or an unreadable `--file`: fix the input.
Exit `2` is a usage error: fix the command.

Never answer blocked dialogs for other agents; keep durable state in committed files, one owner per file; code goes through git.

Use `--no-focus` for background work unless asked; do not close workspaces, tabs, panes, or sessions you did not create; never add `--group` to `herdr workspace close`; use `--trust-repository` only after user verification.

Never run `herdr server stop` from active session unless user intends to stop server and every pane; never kill main process; use named test sessions with `--session`.

Check `herdr status` before relying on newer features; a missing method is not permission to stop or upgrade the server.

Rediscover IDs for another host; only modify machine profiles when asked.

Expect herdr errors as JSON on stderr with exit 1, syntax errors with exit 2.

Input-box patterns in `assets/tui-profiles.json` are drafts not checked against live panes; if `check` refuses idle agent, report it rather than bypassing gate.

See `references/command-examples.md` for examples.
