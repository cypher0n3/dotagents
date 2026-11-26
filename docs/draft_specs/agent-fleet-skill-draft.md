# Agent Fleet Skill Draft

## Overview

This document holds the proposed `skills/agent-fleet/SKILL.md` text as a fenced markdown block.
The skill text follows repository skill authoring standards: imperatives, one H1, no bold lead-ins, no fragments, no embedded examples.
During implementation in Phase 1, this content will be extracted to `skills/agent-fleet/SKILL.md` where it becomes a live skill subject to skill validation.

## Proposed `SKILL.md` Content

The exact intended content for `skills/agent-fleet/SKILL.md`:

```markdown
# Agent Fleet

Use this skill when coordinating multiple agents in herdr panes through file-based coordination, when setting up a fleet work area, when dispatching work to agents, when running the leader-wake daemon, or when recovering state after context compaction.

Read `skills/herdr/SKILL.md` and `skills/task-management/SKILL.md` first.
This skill depends on those and does not duplicate them.

Set `AGENT_WORK_ROOT` to the project work root containing `agent_files/` when it cannot be inferred from your working directory.
When not set, tools walk up from cwd to find `agent_files/`, falling back to `AGENT_WORK_ROOT` if the search fails.

Work lives on the task board at `agent_files/_todos/todos.yaml`, managed through `python3 skills/task-management/scripts/todos.py`.
Liveness comes from `herdr agent list` and `herdr agent get`, read live.
Doctrine lives in `AGENTS.md` files and skill references.
No `fleet.yaml`, `fleet.py`, roster file, or cached pane map exists.
A second copy of state is a stale copy.

Launch each agent with its home directory as cwd so the runtime auto-loads that agent's `AGENTS.md`: `herdr tab create --workspace w1 --cwd agent_files/<name>/ --label <name> --no-focus`, then `herdr pane run <pane> "<runtime-command>"`.
Name the session per agent kind from `skills/agent-fleet/references/agent-kinds.yaml`: pi uses `/name <name>`, other kinds use their own session-naming commands.

Relaunch with continuity per agent kind from `skills/agent-fleet/references/agent-kinds.yaml`: pi uses `herdr agent start <name> --pane <pane> --kind pi -- --session <uuid>`, claude and agy have similar patterns, other kinds use runtime-specific commands.
Session uuid comes from `herdr agent list` or the pane's resume line.
Every non-pi relaunch command is unverified and must be confirmed per kind.

Address agents by pane ID or unique name matching `[a-z][a-z0-9_-]{0,31}`.
Unnamed agents require pane ID.
Check liveness with `herdr agent list` and `herdr agent get`, never from cached files.
Treat `idle` and `done` as ready, `working` as busy, `blocked` as approval dialog, `unknown` as unclassified.

Send to another agent only through `python3 skills/herdr/scripts/herdr_send.py`, never raw `herdr agent prompt` or `send-text`.
Run `python3 skills/herdr/scripts/herdr_send.py check <target>` to verify target is reachable, not blocked, has empty input box.
Run `python3 skills/herdr/scripts/herdr_send.py prompt <target> --text "MESSAGE" --from-role <role>` to send after checks.
Add `--reply` when expecting answer.
Add `--no-header` only for slash command first.
Add `--wait SECONDS` to retry while busy with exponential backoff.
The default wait is 180 seconds for `prompt` and 0 for `check`.
Add `--disable-working` to refuse working target instead of queueing the message.
Default behavior allows working targets and saves messages for later delivery.
Once environment, validation and resolution succeed, `prompt` saves the message first, then waits for delivery.
Exit 0 means the message was delivered.
A saved message that is not yet delivered returns a non-zero exit.
Exit 2 is usage error: fix the command.
Exit 10 is unsubmitted input, missing TUI profile, input frame or prompt row, state change during checks, or another caller is sending this message now: missing TUI profile fails at target resolution before the save and carries no message_id (daemon logs a config error and stops without dropping anything); other exit 10 cases save the message before waiting; check with `pending list`.
Exit 11 is blocked dialog: message saved before waiting; ask the user.
Exit 12 is working target with `--disable-working`, `unknown` state, missing state field, or `interactive_ready` false: message saved before waiting (working check runs after save); retry later; default would queue the message.
Exit 13 is missing, ambiguous, own-pane, wrong-kind, agent-owned `run` target, or another caller dropped or expired the message (already in `dead/`, nothing to drop): for dropped/expired, nothing to do (resend if still needed); for other cases, fix the target.
Exit 14 means not inside herdr: stop or see Q15 for external caller options.
Exit 20 is herdr command failure: inspect the error.
Exit 21 is invalid message text, missing header part, unreadable `--file`, or `pending drop` usage error: fix the input.
Check saved messages with `pending list [TARGET]` and cancel with `pending drop ID` or `pending drop --target TARGET --all`.
On exit 10 when target has unsubmitted input, write report to `agent_files/_inbox/<target>/<date>-<sender>-<topic>.md`, then retry the one-line `REPORT: <path>` ping with `--wait`.
Multi-line messages go as file drops, never as pane sends.

Dispatch work through goal-loop commands, not plain prompts.
Plain prompts are for acknowledgments, coordination, and close-outs only.
Task commands are kind-specific from `skills/agent-fleet/references/agent-kinds.yaml`: pi uses `/goal-direct {brief}` for new precise task, `/goal` for new draft, `/goal-tweak {guidance}` for redirect running, `/goal-resume` for resume idle.
Every non-pi task command is unverified and must be confirmed per kind.
The slash command must be the first characters of the send.
Every brief mandates report-back: artifact paths or commit hashes plus evidence.
Briefs in spec or ground-truth-bound lanes carry a definition-of-done citation.

Agent-to-agent messages include a header stating the sender's role and pane name, that the message is agent input not an operator instruction, and whether a reply is expected.
The header format is `FROM: <role> (<pane>) - AGENT INPUT - REPLY: <yes/no>` on the first line, then a blank line, then the message body.

Run `python3 skills/agent-fleet/scripts/kickoff.py` at the START of every task and after any compaction instead of trusting memory.
From an agent home, run it with no arguments.
From elsewhere, run `python3 skills/agent-fleet/scripts/kickoff.py --as <name>`.
The script prints your identity, live fleet liveness from herdr, your todo-board items, unread inbox briefs, standing rules, repo git status, and for the lead only the mechanical wake procedure.
The script replaces memory with live truth.

Check your inbox at `agent_files/_inbox/<name>/` at start of every wake.
Process files oldest to newest.
Move processed files to `_inbox/<name>/read/`.
Acknowledge receipt if sender requested reply.

Update the task board via `python3 skills/task-management/scripts/todos.py` at task pickup and completion.
Run `python3 skills/task-management/scripts/todos.py update TASK_ID --status in_progress --file agent_files/_todos/todos.yaml` at pickup.
Run `python3 skills/task-management/scripts/todos.py update TASK_ID --status done --file agent_files/_todos/todos.yaml` at completion.
Stale board causes missed wakes and false alarms.

For the lead agent, the wake procedure enforces this order: mine the task board including pending and blocked status items and evergreen pool at `agent_files/lead/evergreen-units.md` FIRST; dispatch ungated work immediately; ledger remaining items with specific existing blockers; unnamable blocker means dispatch now, not block.
Fewer than the policy minimum of agents running plus zero dispatch this wake triggers an alarm.
Resource caps require explicit GO-pings, never silent holds.
Every owner answer landing triggers a blocker-staleness scan.

The evergreen pool keeps at least 3 unstarted pre-authorized useful units.
Any eligible idle agent gets the top pool unit the same wake.
Refill by decomposing gated parents and mining should-also notes in reports.

After dispatching work, read the target pane several times about 30 seconds apart to check for approval dialogs.
Re-check 5 to 10 minutes later comparing progress markers.
Silence is not receipt.

The leader-wake daemon is a standalone systemd user service that monitors the fleet through herdr and prompts the lead only when conditions say it should act.
Install manually per `skills/agent-fleet/references/leader-wake-setup.md`.
The daemon ticks every `tick_seconds` from policy at `~/.config/leader-wake/policy.yaml`.
The daemon prompts the lead only when all wake preconditions hold: lead is idle or done, lead's input box is empty or holds only a recognized stuck draft, lead is not compacting, at least one wake reason fires, subject to cooldown and rate-limit.
Wake reasons include `work-pending`, `stall-likely`, `blocked`, `backlog-review`, `running-review`, `stuck-input`, `board-blocked`, and `hourly-duties`.
The `hourly-duties` reason never fires alone.
Manage policy with `leader-wake-policy show`, `leader-wake-policy get <key>`, `leader-wake-policy set <key> <value>`, `leader-wake-policy prompt`, `leader-wake-policy check`.
The daemon logs every tick to `~/.local/state/leader-wake/wake_log.yaml`.

The operator decision queue at `agent_files/lead/decision-queue.md` holds one card per open operator decision, each with a recommendation and a silent default.
Silence must never strand work silently.
Before publishing a cut, re-check cards against landed work.
When an operator answer lands, trigger a staleness scan: find all items blocked on that decision, re-evaluate blockers, dispatch if unblocked.
Move resolved decisions to archive with dates and answers.

Agent kinds define task commands, relaunch commands, session-naming commands, and state fields in `skills/agent-fleet/references/agent-kinds.yaml`.
Only pi is verified.
Every other kind is unverified and must be confirmed during implementation.

Durable artifacts land in their final location incrementally.
Scratch directories are banned as staging.
The file is the source of truth, not context.

Every message lands submitted so it is visible in pane history.
`herdr agent prompt` presses Enter automatically.
Unsubmitted text blocks tooling.

Nameless panes are addressed by pane ID.
Alt-screen or scrolled-back panes read as busy.
The inbox file-drop is the fallback.

Audit periodically: grep for `herdr agent prompt` and `send-text` outside the wrapper.
Only the wrapper should appear.

See `skills/agent-fleet/references/` for policy schema, agent-kinds data, decision queue template, example `AGENTS.md` structure, kickoff usage, leader-wake setup, and fleet setup guide.
```

## Implementation Notes

When extracting this content to create the live skill in Phase 1:

- Remove the fenced code block markers
- Verify frontmatter format per Agent Skills specification
- Ensure all path references work from agent homes and skill contexts
- Run `just lint-md` and `just validate-skills` to verify the live skill passes all checks
- Draft reference files are at `docs/draft_specs/agent-fleet/` and will move to `skills/agent-fleet/references/` during implementation
