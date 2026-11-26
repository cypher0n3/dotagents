# Fleet Setup Guide

## Overview

This guide walks through setting up an agent fleet work area from scratch, including directory structure, configuration files, and agent launch.

## Prerequisites

- Herdr installed and running
- Python 3.12+ with venv support
- `skills/herdr`, `skills/task-management`, and `skills/agent-fleet` available
- Git repository for the project

## Step 1: Create Work Area

Choose a work root directory and create the fleet structure:

```bash
export FLEET_ROOT=/path/to/your/project
mkdir -p "$FLEET_ROOT"/{repo,agent_files/{lead,_todos,_inbox,_bin}}
```

The layout is:

- `repo/`: git repository
- `agent_files/`: fleet coordination area
- `agent_files/lead/`: lead agent home and decision artifacts
- `agent_files/_todos/`: shared task board
- `agent_files/_inbox/`: inbox directories per agent
- `agent_files/_bin/`: optional shared scripts

## Step 2: Seed Fleet-Wide `AGENTS.md`

Create `$FLEET_ROOT/AGENTS.md` with fleet-wide rules:

```markdown
# Fleet-Wide Agent Rules

## Communication

Every message to another agent goes through the safe-send gate.
Never use raw `herdr agent prompt` or `send-text`.

Reports are files in `agent_files/_inbox/<target>/`, followed by a one-line `REPORT:` ping.

## Task Board Hygiene

Update `agent_files/_todos/todos.yaml` at task pickup and completion.
Stale board causes missed wakes and false alarms.

## Persistence

Durable artifacts land in their final location incrementally.
Scratch directories are banned.
The file is the source of truth, not context.

## Commit Style

Imperative one-sentence subject.
Explicit pathspec, never `git add -A`.
No trailers.

## Gates

Narrowest gate covering touched file types before every commit.
Full CI only at workstream end.

## Kickoff Ritual

Run `python3 skills/agent-fleet/scripts/kickoff.py` at the start of every task and after any compaction.
```

## Step 3: Create Per-Agent Homes

For each agent, create a home directory with its own AGENTS.md:

```bash
mkdir -p "$FLEET_ROOT/agent_files/implementer"
mkdir -p "$FLEET_ROOT/agent_files/reviewer"
mkdir -p "$FLEET_ROOT/agent_files/tester"
```

Create `$FLEET_ROOT/agent_files/lead/AGENTS.md`:

```markdown
# Lead Agent

## Role

Coordinate the fleet, dispatch work, monitor progress, handle operator decisions.

## Responsibilities

- Monitor fleet liveness through `herdr agent list`
- Mine task board and evergreen pool for dispatchable work
- Assign work to idle agents through safe-send gate
- Track progress and detect stalls
- Drain worker inboxes and act on reports
- Maintain operator decision queue

## Wake Procedure

1. Run kickoff to load current state
2. Mine board for actionable work
3. Mine evergreen pool
4. Dispatch ungated work to idle agents
5. Ledger remaining items with specific existing blockers
6. Alarm if fewer than 3 agents running and zero dispatch
7. Update task board after all actions

## Dispatch

Use goal-loop commands first.
Verify target ready with safe-send check.
Monitor pane for approval dialogs.
Re-check progress 5-10 minutes later.

## Evergreen Pool

Keep at least 3 unstarted units in `agent_files/lead/evergreen-units.md`.
Refill by decomposing gated parents.
```

Create similar AGENTS.md files for each worker agent with role-specific instructions.

## Step 4: Create Inbox Directories

Create inbox directories for each agent:

```bash
mkdir -p "$FLEET_ROOT/agent_files/_inbox/lead/read"
mkdir -p "$FLEET_ROOT/agent_files/_inbox/implementer/read"
mkdir -p "$FLEET_ROOT/agent_files/_inbox/reviewer/read"
mkdir -p "$FLEET_ROOT/agent_files/_inbox/tester/read"
```

## Step 5: Initialize Task Board

Initialize the todos board:

```bash
cd "$FLEET_ROOT/agent_files/_todos"
python3 "$FLEET_ROOT/repo/skills/task-management/scripts/todos.py" init --title "Project Tasks" --file todos.yaml
```

Add initial tasks:

```bash
python3 "$FLEET_ROOT/repo/skills/task-management/scripts/todos.py" add "Set up development environment" --file todos.yaml --assignee-kind agent --assignee-name lead --agent-type pi --priority medium
python3 "$FLEET_ROOT/repo/skills/task-management/scripts/todos.py" add "Create project structure" --file todos.yaml --assignee-kind agent --assignee-name implementer --agent-type pi --priority high
```

Verify board structure:

```bash
python3 "$FLEET_ROOT/repo/skills/task-management/scripts/todos.py" list all --file todos.yaml
```

## Step 6: Create Leader-Wake Policy

Write the initial policy (see `docs/draft_specs/agent-fleet/leader-wake-setup.md` for complete steps):

```bash
mkdir -p ~/.config/leader-wake
leader-wake-policy set work_area "$FLEET_ROOT"
leader-wake-policy set target.name lead
leader-wake-policy set target.workspace_id w1
leader-wake-policy set fleet.workspace_id w1
leader-wake-policy set work.todos agent_files/_todos/todos.yaml
leader-wake-policy set gates.min_other_agents_working 3
leader-wake-policy set tick_seconds 600
```

Add multi-line prompt templates by editing `~/.config/leader-wake/policy.yaml` directly.

Validate the policy:

```bash
leader-wake-policy check
```

## Step 7: Install Systemd User Unit

**Note**: The systemd user unit cannot deliver wake prompts until Q15 is decided and its option is implemented.
The `herdr_send.py` command requires `HERDR_ENV=1`, which confirms the caller is inside a herdr pane.
See `docs/draft_specs/agent-fleet-spec.md` Q15 for options and the exit-14 entry in the daemon exit code table.

Create `~/.config/systemd/user/leader-wake.service`:

```ini
[Unit]
Description=Leader-Wake Daemon
After=herdr.service
Wants=herdr.service

[Service]
Type=simple
# ExecStart line depends on Q15 resolution (see agent-fleet-spec.md Q15)
ExecStart=/path/to/leader-wake
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Enable and start the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now leader-wake.service
systemctl --user status leader-wake.service
```

## Step 8: Launch and Name Agents

Launch each agent in herdr with its home as cwd:

```bash
# Lead agent (pi kind)
herdr tab create --workspace w1 --cwd "$FLEET_ROOT/agent_files/lead" --label lead --no-focus
# Note the pane ID, e.g., w1:p1
herdr pane run w1:p1 "pi"
# Wait for pi to start, then name the session per agent-kinds.yaml
python3 skills/herdr/scripts/herdr_send.py prompt w1:p1 --text "/name lead" --from-role operator --no-header

# Implementer agent (pi kind)
herdr tab create --workspace w1 --cwd "$FLEET_ROOT/agent_files/implementer" --label implementer --no-focus
herdr pane run w1:p2 "pi"
python3 skills/herdr/scripts/herdr_send.py prompt w1:p2 --text "/name implementer" --from-role operator --no-header

# Reviewer agent (pi kind)
herdr tab create --workspace w1 --cwd "$FLEET_ROOT/agent_files/reviewer" --label reviewer --no-focus
herdr pane run w1:p3 "pi"
python3 skills/herdr/scripts/herdr_send.py prompt w1:p3 --text "/name reviewer" --from-role operator --no-header
```

For other agent kinds, use their kind-specific session-naming commands from `skills/agent-fleet/references/agent-kinds.yaml`.

Verify agents are running:

```bash
herdr agent list
```

## Step 9: Smoke Check Leader Wake

Test that the lead can be woken:

```bash
# Verify lead is idle
python3 skills/herdr/scripts/herdr_send.py check lead

# Send a test message
python3 skills/herdr/scripts/herdr_send.py prompt lead --text "Test message" --from-role operator

# Check herdr_send exit code
echo $?
# Exit 0 means delivered successfully
```

Wait for the daemon's first tick (default 600 seconds, 10 minutes) or trigger manually by restarting the service:

```bash
systemctl --user restart leader-wake.service
```

Check daemon logs for wake decision:

```bash
journalctl --user -u leader-wake.service -n 20
```

Check wake log:

```bash
tail -20 ~/.local/state/leader-wake/wake_log.yaml
```

## Step 10: Create Evergreen Pool

Create the evergreen pool at `$FLEET_ROOT/agent_files/lead/evergreen-units.md`:

```markdown
# Evergreen Dispatch Pool

Pre-authorized, ungated, useful units.
Keep at least 3 unstarted.

## Available Units

### U001: Code Review Checklist Update

Review and update the code review checklist in docs/ based on recent review findings.

### U002: Test Coverage Report

Generate test coverage report and identify untested modules.

### U003: Dependency Audit

Audit project dependencies for updates and security issues.
```

## Task Board Tracking

The task board at `agent_files/_todos/todos.yaml` tracks work through these fields:

- `status`: `pending`, `in_progress`, `done`, or `blocked`
- `assignee.name`: agent name
- `priority`: `low`, `medium`, `high`, `critical`
- `description`: optional details including blocker reasons

### Status Workflow

1. **Pending**: Task exists, not started.
   Actionable work for the daemon.
2. **In Progress**: Agent picked up task.
   Run `python3 skills/task-management/scripts/todos.py start TASK_ID --file agent_files/_todos/todos.yaml`.
3. **Blocked**: Task cannot proceed.
   Add blocker reason.
   Run `python3 skills/task-management/scripts/todos.py update TASK_ID --blocked-reason "reason text" --file agent_files/_todos/todos.yaml`.
4. **Done**: Task completed.
   Run `python3 skills/task-management/scripts/todos.py done TASK_ID --file agent_files/_todos/todos.yaml`.

### Reading the Board

The lead and daemon read actionable work:

```bash
python3 skills/task-management/scripts/todos.py list all --file agent_files/_todos/todos.yaml
```

Filtered views:

```bash
# Pending tasks only
python3 skills/task-management/scripts/todos.py list all --status pending --file agent_files/_todos/todos.yaml

# Blocked tasks
python3 skills/task-management/scripts/todos.py list all --status blocked --file agent_files/_todos/todos.yaml

# Agent tasks only
python3 skills/task-management/scripts/todos.py list agent --file agent_files/_todos/todos.yaml
```

The daemon evaluates wake reasons based on:

- Actionable work count (pending + in_progress + blocked)
- Number of running agents (from `herdr agent list`)
- Policy thresholds (`gates.min_other_agents_working`)

### Decision Queue

The operator decision queue at `agent_files/lead/decision-queue.md` tracks decisions needing owner input.
Each card includes:

- Unique ID (D001, D002, etc.)
- Context and options
- Recommendation
- Silent default (what happens if no answer arrives)
- Status (OPEN, ANSWERED, SUPERSEDED)

When an answer lands, the lead:

1. Updates decision card status to ANSWERED
2. Finds all board items blocked on that decision
3. Re-evaluates blockers
4. Dispatches if no other blocker remains
5. Moves resolved card to archive section

## Verification Checklist

After setup, verify:

- [ ] Work area structure exists
- [ ] Fleet-wide AGENTS.md exists and is readable
- [ ] Each agent home has its own AGENTS.md
- [ ] Inbox directories exist for each agent
- [ ] Task board initialized and contains tasks
- [ ] Leader-wake policy validated
- [ ] Systemd user unit enabled and running
- [ ] All agents launched and named in herdr
- [ ] Lead responds to test message
- [ ] Daemon logs show tick decisions
- [ ] Evergreen pool exists with at least 3 units

## Next Steps

1. Add real project tasks to the board
2. Dispatch first task to an idle agent
3. Monitor daemon behavior through logs
4. Tune policy thresholds based on fleet size
5. Build out evergreen pool with common tasks
6. Establish decision queue workflow
