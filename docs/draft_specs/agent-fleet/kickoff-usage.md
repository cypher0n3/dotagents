# Kickoff Script Usage

## Overview

The kickoff script is run at the START of every task and after any compaction instead of trusting memory.
It prints the agent's current state from live authoritative sources.

Planned location: `skills/agent-fleet/scripts/kickoff.py`

During draft phase: This document serves as the reference template.

## Invocation

From an agent home directory:

```bash
python3 ../../skills/agent-fleet/scripts/kickoff.py
```

From any directory with explicit name:

```bash
python3 path/to/skills/agent-fleet/scripts/kickoff.py --as <agent-name>
```

The script infers identity from launch cwd (`agent_files/<name>/`) or uses the `--as` flag.
The script reads work root by walking up from cwd to find `agent_files/`, then falls back to `AGENT_WORK_ROOT` environment variable if the search fails.

## Output Sections

The script prints 7 sections (lead agents get an 8th):

### Section 1: Fleet Liveness

Live liveness from `herdr agent list`.
This is the ONLY authoritative source for who is running.
Never trust cached status files.

Example output:

```text
## 1. Fleet liveness (herdr agent list - authoritative, live)
  w1:p1    idle      lead     <== YOU
  w1:p2    working   implementer
  w1:p3    done      reviewer
  w1:p4    blocked   tester
```

### Section 2: Sources of Truth

Reminder of where each concern lives:

- Liveness / who-is-running: `herdr agent list` (section 1 above)
- Work: mine, queued, blocked: todo board (section 3) and lead evergreen pool
- Standing rules: work-area AGENTS.md and your home AGENTS.md
- Dispatch mechanics: `agent_files/dispatch-protocol.md`

No fleet.yaml status or queue mirrors exist.
A second copy of state is a stale copy.

### Section 3: Todo Items

The agent's open items from `agent_files/_todos/todos.yaml`.
This is THE work source.

Example output:

```text
## 3. My todo items (agent_files/_todos/todos.yaml)
open 2 / mine 5:
  [pending    ] TASK-001 - Implement user authentication
  [in_progress] TASK-002 - Fix login validation bug
```

For the lead, an empty board while fleet is idle is an alarm: mine the board and evergreen pool.

### Section 4: Inbox

Unread briefs in `agent_files/_inbox/<name>/`.
Convention: move drained items to `read/` subdirectory.

Example output:

```text
## 4. Unread briefs (agent_files/_inbox/implementer/)
  2026-11-26-lead-task-003.md
  2026-11-26-reviewer-review-complete.md
  (convention: move drained items to _inbox/implementer/read/)
```

### Section 5: Standing Rules

Summary of rules that burned the fleet:

- SUBMITTED ONLY: every message must land submitted (Enter pressed).
  `herdr agent prompt` does this automatically.
  Unsubmitted text blocks tooling.
- SAFE-SEND GATE: never raw `herdr agent prompt` or `send-text`.
  Use `python3 ../../skills/herdr/scripts/herdr_send.py prompt <target> "<line>"`.
  On busy (rc=10), write to `_inbox/<target>/` and retry the ping with `--wait`.
  Reports are FILES, never pane text.
- TODO HYGIENE: update `agent_files/_todos/todos.yaml` via the todos.py CLI at pickup AND completion.
  Stale board causes missed wakes and false alarms.
- PERSISTENCE: `/tmp` is RAM scratch.
  Durable artifacts land in their final location incrementally.
  The file is the source of truth, not context.
- COMMIT STYLE: imperative one-sentence subject, explicit pathspec (never `git add -A`), no trailers.
- GATES: narrowest gate covering touched file types before every commit.
  Full CI only at workstream end.
- TASK-START RITUAL: THIS SCRIPT replaces memory.
  Re-read your own AGENTS.md if compaction dropped it: `agent_files/<name>/AGENTS.md`.

### Section 6: Repo In-Flight

Git status summary from `repo/` to avoid collisions.

Example output:

```text
## 6. Repo in-flight (git status -s in repo/)
 M src/auth/login.py
 M tests/test_login.py
A  docs/auth-spec.md
```

### Section 7: Lead-Only Evergreen Block

For the lead agent only, the mechanical wake procedure:

1. Mine the todo board, markers, and evergreen pool FIRST.
2. Dispatch ungated work this wake; fewer than 2 agents running plus zero dispatch = alarm.
3. Ledger each item's specific existing blocker (owner letter in queue index or named artifact); unnamable blocker = dispatch, not blocked.
4. Caps (model concurrency) lead to explicit GO-pings, never silent holds.
5. Every owner answer landing leads to re-scan for items whose only blocker was that answer; blockers go stale.

Evergreen pool at `agent_files/lead/evergreen-units.md`, keep at least 3 units.

## When to Run

Run the kickoff script:

- At the start of every new task.
- After any context compaction.
- After a long idle period.
- When returning from approval dialogs.
- When unsure of current state.

Do NOT trust memory for standing rules or current state.
The script replaces memory with live truth.

## Environment Variables

`AGENT_WORK_ROOT`: Project work root containing `agent_files/`.
If not set, the script walks up from cwd to find `agent_files/`.
If the search fails, the script requires `AGENT_WORK_ROOT` and exits with an error.

`HERDR_ENV`: Set to `1` when inside herdr.
If not set, liveness section shows "(not inside herdr - skipped)".

## Error Handling

The script fails with `Error: <message>` lines, not tracebacks:

- `Error: cannot infer agent name from cwd; pass --as <name>`: not in an agent home and no `--as` flag.
- `Error: todo board unreadable: <reason>`: todos.yaml missing or invalid.
- `Error: herdr agent list failed`: herdr not available or command error.

Errors are informational; the script prints what it can and skips what it cannot.

## Integration With Agent Workflow

Typical agent task flow:

1. Wake (from operator, lead, or daemon).
2. Run kickoff script to load state.
3. Read assigned task from todo board (section 3) or inbox (section 4).
4. Update todo status to `in_progress` via todos.py CLI.
5. Work on task.
6. Run narrow test gate for changed files.
7. Commit with clear message.
8. Write completion report to lead's inbox.
9. Update todo status to `done` via todos.py CLI.
10. Send `REPORT:` ping to lead through safe-send gate.

The kickoff script is step 2: it loads the truth so the agent does not rely on memory.

## Kickoff Output Interpretation

Good state indicators:

- Fleet liveness shows expected agents running.
- Your todo items are clear and actionable.
- Inbox is empty or has only recent reports.
- Repo status is clean or shows only your own in-progress work.

Alarm indicators:

- Fleet liveness shows agents blocked or unknown status.
- Your todo items are ambiguous or lack context.
- Inbox has old unread reports.
- Repo status shows conflicts or unexpected changes.
- (Lead only) Empty board while fleet is idle.

Act on alarms before starting new work.

## Example Full Output

```text
# DISPATCH KICKOFF - implementer - 2026-11-26 09:30

## 1. Fleet liveness (herdr agent list - authoritative, live)
  w1:p1    idle      lead
  w1:p2    working   implementer  <== YOU
  w1:p3    done      reviewer

## 2. Sources of truth (memorized status is NOT one)
  - liveness / who-is-running ......... `herdr agent list` (section 1 above)
  - work: mine, queued, blocked ....... todo board (section 3) + lead evergreen pool
  - standing rules .................... work-area AGENTS.md + your home AGENTS.md
  - dispatch mechanics ................ agent_files/dispatch-protocol.md
  (fleet.yaml status/queue mirrors are RETIRED: a second copy of state is a
   stale copy - herdr answers live state, the board answers work, nothing else.)

## 3. My todo items (agent_files/_todos/todos.yaml)
open 1 / mine 3:
  [in_progress] TASK-002 - Fix login validation bug

## 4. Unread briefs (agent_files/_inbox/implementer/)
  (empty)
  convention: move drained items to _inbox/implementer/read/

## 5. Standing rules - summaries (full text: work-area AGENTS.md)
  - SUBMITTED ONLY: every message to lead/peer must land submitted
    (herdr agent prompt, or send-keys enter after a paste). Unsubmitted
    text silently blocks leader-wake.
  - SAFE-SEND GATE: never raw `herdr agent prompt/send-text/send-keys` to a
    pane you don't own. Use python3 ../../skills/herdr/scripts/herdr_send.py prompt <pane> "<one line>";
    rc=10 (owner typing) -> write to _inbox/<target>/ + retry the ping with
    --wait. Reports are FILES, never pane text.
  - TODO HYGIENE: update agent_files/_todos/todos.yaml via the todos.py CLI at
    pickup AND completion (stale board = missed wakes / false alarms).
  - PERSISTENCE: /tmp is RAM scratch. Durable artifacts land in their final
    location incrementally; the file is the source of truth, not your context.
  - COMMIT STYLE: imperative one-sentence subject, explicit pathspec (never
    git add -A), no trailers.
  - GATES: narrowest gate covering touched file types before every commit;
    full CI only at workstream end.
  - TASK-START RITUAL: THIS SCRIPT replaces memory. Re-read your own AGENTS.md
    if compaction dropped it: agent_files/implementer/AGENTS.md

## 6. Repo in-flight (git status -s in repo/)
 M src/auth/login.py
 M tests/test_login.py

--- kickoff complete: work the highest-priority open item; update the board at pickup. ---
```
