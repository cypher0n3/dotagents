# Leader-Wake Daemon Setup

## Overview

This document describes how to install, configure, and operate the leader-wake daemon as a systemd user service.

## Installation Steps

The following steps install and configure the leader-wake daemon.

### Create Policy File

Create the policy configuration at `~/.config/leader-wake/policy.yaml`:

```bash
mkdir -p ~/.config/leader-wake
```

Use `leader-wake-policy` to seed the initial policy:

```bash
leader-wake-policy set work_area /path/to/your/project
leader-wake-policy set target.name lead
leader-wake-policy set target.workspace_id w1
leader-wake-policy set fleet.workspace_id w1
leader-wake-policy set work.todos agent_files/_todos/todos.yaml
leader-wake-policy set gates.min_other_agents_working 3
leader-wake-policy set gates.running_review_max_agents 3
leader-wake-policy set stall.seconds 1800
leader-wake-policy set stall.hash_lines 20
leader-wake-policy set stall.evidence_lines 6
leader-wake-policy set prompting.cooldown_seconds 300
leader-wake-policy set prompting.max_prompts_per_hour 6
leader-wake-policy set prompting.backlog_review_seconds 21600
leader-wake-policy set prompting.duty_seconds 3600
leader-wake-policy set prompting.review_seconds 3600
leader-wake-policy set prompting.stuck_input_ticks 2
leader-wake-policy set tick_seconds 600
```

Edit the policy file directly to add multi-line prompt text:

```yaml
prompt:
  header: 'WAKE (leader-wake, auto): {reasons}'
  verify_line: |
    IDLE IS UNACCEPTABLE: any agent idle while a dispatchable unit exists
    (pending or blocked board items, evergreen pool, or any ungated part of a
    gated parent) makes THIS wake a failure until it is dispatched. Mine the
    live board and pool BEFORE writing any ledger; caps are enforced at dispatch time.
    The tool only detected conditions - verify before acting. After acting,
    update the todo board.
  hourly_duties: |
    Pane skim and paused-goal sweep, dispatch with preflight, worker caps
    per backend, scratch cleanup, todo-board status refresh.
  running_review: |
    Review recipe for each running agent: skim goal and recent output;
    off-track leads to goal redirect per agent-kinds.yaml (pi uses /goal-tweak);
    long-running-no-progress leads to nudge toward the next concrete step, do not rewrite the task.
  board_blocked: 'Chase the blockers; update statuses after acting.'
  work:
    statuses:
      - pending
      - in_progress
      - blocked
```

Validate the policy:

```bash
leader-wake-policy check
```

### Create Systemd User Unit

**Note**: The systemd user unit cannot deliver wake prompts until Q15 is decided and its option is implemented.
The `herdr_send.py` command requires `HERDR_ENV=1`, which confirms the caller is inside a herdr pane.
See `docs/draft_specs/agent-fleet-spec.md` Q15 for options and the exit-14 entry in the daemon exit code table.

Create the systemd user unit file at `~/.config/systemd/user/leader-wake.service`:

```ini
[Unit]
Description=Leader-Wake Daemon for Agent Fleet Coordination
After=herdr.service
Wants=herdr.service

[Service]
Type=simple
# ExecStart line depends on Q15 resolution (see agent-fleet-spec.md Q15)
ExecStart=/path/to/leader-wake
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

Replace `/path/to/leader-wake` with the actual path to the daemon executable.

Reload systemd user configuration:

```bash
systemctl --user daemon-reload
```

### Enable and Start the Service

Enable the service to start automatically:

```bash
systemctl --user enable leader-wake.service
```

Start the service:

```bash
systemctl --user start leader-wake.service
```

Check the service status:

```bash
systemctl --user status leader-wake.service
```

## Operation

The daemon is controlled through systemd and monitored through logs and state files.

### Checking Daemon Status

View current status:

```bash
systemctl --user status leader-wake.service
```

View recent logs:

```bash
journalctl --user -u leader-wake.service -n 50
```

Follow live logs:

```bash
journalctl --user -f -u leader-wake.service
```

### Reading Decision Log

The daemon logs every tick decision to `~/.local/state/leader-wake/wake_log.yaml`:

```bash
tail -50 ~/.local/state/leader-wake/wake_log.yaml
```

Each entry shows tick timestamp, wake decision, reasons, and prompt delivery result.

### Modifying Policy

Change policy settings with `leader-wake-policy`:

```bash
leader-wake-policy set gates.min_other_agents_working 5
leader-wake-policy set tick_seconds 300
```

The daemon hot-reloads the policy at the next tick.

View current policy:

```bash
leader-wake-policy show
```

Get a specific key:

```bash
leader-wake-policy get gates.min_other_agents_working
```

### Stopping the Service

Stop the daemon:

```bash
systemctl --user stop leader-wake.service
```

Disable automatic start:

```bash
systemctl --user disable leader-wake.service
```

### Troubleshooting

If the service fails to start:

1. Check policy validation: `leader-wake-policy check`
2. Check herdr is running: `herdr status`
3. Check logs: `journalctl --user -u leader-wake.service -n 100`
4. Verify work area path exists and is accessible
5. Verify todos board file exists at the configured path

If prompts are not delivered:

1. Check wake preconditions in the logs
2. Verify lead agent is in herdr workspace: `herdr agent list`
3. Check cooldown and rate-limit settings
4. Test manual prompt: `python3 skills/herdr/scripts/herdr_send.py check lead`

If prompts are delivered but ignored:

1. Check lead agent's input box is empty
2. Verify lead is not compacting
3. Check wake log for `herdr_send.py` exit codes and outcomes (see Leader-Wake Daemon section in `docs/draft_specs/agent-fleet-spec.md` for exit code meanings and required operator actions)
4. Test wake reason evaluation: `leader-wake-policy prompt`

## State Management

Daemon state at `~/.local/state/leader-wake/state.yaml` tracks:

- Per-pane output hashes for stall detection
- Last cadence timestamps for periodic reasons
- Cooldown expiry
- Rate-limit window

The state file is automatically managed by the daemon.
Do not edit it manually.

## Policy Schema

See `docs/draft_specs/agent-fleet/policy-schema.yaml` for complete policy structure and field documentation.
