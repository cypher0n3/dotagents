# Agent Fleet Coordination Requirements

## Overview

This document defines the requirements for an autonomous agent fleet system where a supervisor (lead) agent coordinates multiple worker agents in herdr panes through file-based coordination and enforced safe-send gates.
The system builds on existing herdr safe-send capabilities (from `skills/herdr/scripts/herdr_send.py`) and task-management infrastructure (`skills/task-management`) to prevent injection failures, eliminate wake starvation, and enforce rules mechanically rather than through agent memory.

## Architecture Requirements

These requirements define the core architecture for file-based agent coordination.

### R-FLEET-001: File-Based Coordination

The system SHALL coordinate agents entirely through files and scripts rather than through agent memory or status mirrors.

Rationale: Agent context compaction causes rule and state loss.
Mechanized checks enforced at action time survive context loss.

### R-FLEET-002: Single Source of Truth per Concern

Each coordination concern SHALL have exactly one authoritative source that is read live at use time.

Agent liveness SHALL come from `herdr agent list` and `herdr agent get`, never from cached status files.
Work assignment and queue state SHALL come from the task board (`skills/task-management`), never from status mirrors.
Standing instructions SHALL come from AGENTS.md files and skill references, never from copied or paraphrased rule blocks in status files.
Agent identity and addressing SHALL come from the runtime's session names and pane IDs.

Rationale: A second copy of state becomes a stale copy.
Multiple writers with no arbiter create conflicts.

### R-FLEET-003: Per-Agent Home Directories

Each agent SHALL have its own home directory under a configured agent files root containing its own AGENTS.md and runtime working directory.
Agents SHALL be launched with their home directory as the working directory so the runtime auto-loads that agent's AGENTS.md.

### R-FLEET-004: Work Root Environment Variable

The system SHALL support an `AGENT_WORK_ROOT` environment variable that specifies the project work root.
When `AGENT_WORK_ROOT` is not set, tools SHALL walk up from cwd to find `agent_files/`, falling back to `AGENT_WORK_ROOT` if the search fails.
When `AGENT_WORK_ROOT` is required by a tool, that requirement SHALL be documented.

Rationale: Skills must not assume their own tree as the work area or they cannot operate on external project directories.

### R-FLEET-005: Fail-Closed Safe-Send Enforcement

All agent-to-agent and lead-to-agent sends SHALL go through the existing `herdr_send.py` safe-send gate from `skills/herdr`.
The safe-send gate SHALL refuse sends when the target has unsubmitted input text in its TUI input box, when the target is in a blocked approval dialog, or when the input frame cannot be verified.
Multi-line messages SHALL be delivered as file drops in the target's inbox directory, followed by a single-line ping through the safe-send gate.

Rationale: Pane injection failures (sending text while the operator is typing) fuse messages and submit corrupt input.

### R-FLEET-006: Inbox File-Drop Pattern

Each agent SHALL have an inbox directory for receiving structured reports and messages from other agents.
Senders SHALL write reports as files to the target's inbox directory, then send a single-line `REPORT:` ping through the safe-send gate to notify the target.
The target agent SHALL drain inbox files by moving them to a read subdirectory after processing.

## Lead Agent Requirements

These requirements define the lead agent's responsibilities and wake automation.

### R-FLEET-007: Leader-Wake Daemon

A standalone daemon SHALL monitor the fleet through herdr and prompt the lead agent only when wake conditions are met.
The daemon SHALL check wake preconditions before every prompt: lead is idle with empty input box, lead is not compacting, and at least one wake reason fires.
The daemon SHALL respect configurable cooldown and rate-limit policies to prevent prompt flooding.

### R-FLEET-008: Wake Reasons

The daemon SHALL recognize these wake reasons, each with configurable thresholds:

- work-pending: actionable work exists on the task board with fewer than a configured minimum of workers running, or a stall is suspected
- stall-likely: a working pane's output tail is unchanged for a configured duration
- blocked: any agent sits in herdr blocked state with an approval dialog
- backlog-review: actionable work count is zero; fires on transition then periodically
- running-review: lead idle while few agents run; fires periodically
- stuck-input: lead's input box holds the same unsubmitted draft for multiple consecutive ticks
- board-blocked: task board contains items with status blocked
- hourly-duties: duties checklist fires periodically; never fires alone

### R-FLEET-009: Wake Procedure Enforcement

The lead agent's wake procedure SHALL enforce this order:

1. Mine the task board (including pending and blocked status items) and evergreen dispatch pool FIRST before any ledger.
2. Dispatch ungated work immediately; fewer than N agents running plus zero dispatch this wake SHALL trigger an alarm.
3. Ledger remaining items with specific existing blockers; unnamable blocker means dispatch now, not block.
4. Resource caps SHALL require explicit GO-pings, never silent holds.
5. Every owner answer landing SHALL trigger a blocker-staleness scan.

### R-FLEET-010: Evergreen Dispatch Pool

The lead SHALL maintain a pool of pre-authorized, ungated, useful units in a configured file.
The pool SHALL be kept at a configured minimum size (at least 3 unstarted units).
Any eligible idle agent SHALL be assigned the top pool unit the same wake.

### R-FLEET-011: Operator Decision Queue

The lead SHALL maintain a versioned queue index with one card per open operator decision.
Each decision card SHALL include a recommendation and a silent default (what happens if the answer never arrives).
Every queue cut SHALL re-check cards against landed work before publishing.
Every landed answer SHALL trigger a blocker-staleness scan.

## Task Delivery Requirements

These requirements define how work is dispatched to agents.

### R-FLEET-012: Goal-Loop Command Dispatch

All work dispatch SHALL go through the agent runtime's goal loop commands, not plain prompts.
Plain prompts SHALL be reserved for non-work traffic such as acknowledgments, coordination, and close-outs.
The system SHALL enforce command-first discipline: slash commands must be the first characters of the send.

Rationale: Work dispatch must be greppable in pane history.
One mechanism prevents silent failures where prose before the command causes the goal to not be created.

### R-FLEET-013: Multi-Agent-Kind Support

The system SHALL support multiple agent kinds including pi, claude, codex, cursor, agy, and xorc.
Agent-kind-specific behavior (task commands, relaunch commands, delivery commands) SHALL be defined in data files, not hardcoded.
Every non-pi delivery or relaunch command SHALL be marked as unverified and to be confirmed per kind until tested.

Rationale: The fleet must not be pi-only.
Kind-specific behavior in data allows extension without code changes.

### R-FLEET-014: Report-Back Mandate

Every work brief SHALL mandate report-back with artifact paths or commit hashes plus evidence.
Briefs in spec or ground-truth-bound lanes SHALL carry a definition-of-done citation.

Rationale: Silent completion is not verifiable.
Ground-truth citations prevent fixes that break original behavior.

## Kickoff and State Recovery Requirements

These requirements define how agents recover state after context loss.

### R-FLEET-015: Mechanized Kickoff Ritual

A task-start script SHALL be run at the START of every task and after any compaction instead of trusting memory.
The kickoff script SHALL print the agent's identity, live fleet liveness from herdr, the agent's todo-board items, unread inbox briefs, standing rules, repo git status, and (for the lead only) the mechanical wake procedure.

Rationale: After compaction, agents forget the task-start ritual, todo hygiene, and report format.
A script replaces memory with live truth.

### R-FLEET-016: Submitted-Message Discipline

Every agent message SHALL land submitted (Enter pressed) so it is visible in pane history and does not block operator-side wake tooling.
The safe-send gate SHALL use `herdr agent prompt`, which presses Enter automatically.

Rationale: Unsubmitted text silently blocks tooling and is not greppable.

### R-FLEET-017: Message Header Contract

Every message from one agent to another SHALL include a header identifying the sender's role, pane, and whether a reply is expected.
The header SHALL state that the message is agent input, not an operator instruction.

Rationale: Agents must distinguish peer messages from operator commands.
Reply expectations prevent silent drops.

### R-FLEET-018: Liveness Verification After Dispatch

After dispatching work, the lead SHALL read the target pane several times about 30 seconds apart to check for approval dialogs.
The lead SHALL re-check 5 to 10 minutes later comparing progress markers.
Silence SHALL be treated as non-receipt.

Rationale: Approval dialogs sit unseen if not polled.
Silence does not prove receipt.

## State Management Requirements

These requirements define how state is managed and validated.

### R-FLEET-019: No Status Mirror Files

The system SHALL NOT create or maintain fleet.yaml, fleet.py, roster files, or cached pane maps.
Liveness SHALL be read live from herdr.
Work SHALL live on the task-management board.
Doctrine SHALL live in AGENTS.md files.

Rationale: Status mirrors become stale when agents forget to stamp them or when reality drifts.
A second copy of state is always a stale copy.

### R-FLEET-020: One Validating Writer per Structured File

Each structured file SHALL have exactly one atomic validating writer.
Agents SHALL never edit state YAML files with text tools.
The writer SHALL fail loudly on ambiguity.
The writer SHALL be testable offline.

Rationale: Direct edits bypass validation and corrupt state.
Loud failures surface bugs early.

### R-FLEET-021: Scratch Directory Ban

Durable artifacts SHALL land in their final location incrementally.
Scratch directories SHALL be banned as staging areas for final deliverables.
The file is the source of truth, not agent context.

Rationale: Agents lose track of scratch staging and artifacts evaporate.

## Implementation Standards Requirements

These requirements define the quality and test standards for implementation.

### R-FLEET-022: Fleet Skill Coverage

A new skill under `skills/agent-fleet/` SHALL cover work-area and per-agent setup, inbox file drops, herdr agent lifecycle, the leader-wake daemon (systemd user service setup, policy YAML and CLI, state and decision log, wake reasons and preconditions), the lead wake procedure, tracking through the board, the kickoff ritual, the evergreen pool, and the operator decision queue.

### R-FLEET-023: Implementation Quality Standards

Later implementation SHALL meet the PR 10 and PR 11 standard:

- Python with thin entry point and logic in a package with `_lib` suffix
- type hints, and `Error:` lines instead of tracebacks
- one atomic validating writer per structured file
- offline tests with a fake herdr runner and 100 percent line and branch coverage
- radon MI grade A and xenon B
- wired into `just ci`, GitHub CI and GitLab CI
- no lint suppressions
- YAML config parsed with `ruamel.yaml` from requirements.txt, matching task-management's approach
- no exact version pins

Rationale: Consistent quality standards across the codebase.
High test coverage catches regressions.

### R-FLEET-024: Safe-Send Wrapper Path

Every send, including the daemon's wake prompts, SHALL go through `herdr_send.py`, never raw `herdr agent prompt`.
The skill text and scripts SHALL reference `herdr_send.py` by a path that works from an agent home or the fleet skill, not as herdr-relative `scripts/herdr_send.py`.

Rationale: A single send path ensures the gate is never bypassed.
Relative paths from skill context must work from agent working directories.

## Known Limits

These are known limitations that SHALL be documented but are not currently addressable.

### R-FLEET-025: Name-Based Addressing Limits

Name-based targeting requires the runtime's session-name reporting.
Panes without a name must be addressed by pane ID.

### R-FLEET-026: Screen-Based Detection Limits

Screen-based busy detection requires the input frame rendered.
Alt-screen scrollback-only apps or scrolled-back targets read as BUSY (safe but conservative).
The inbox path is the fallback.

### R-FLEET-027: Raw Herdr Audit Requirement

The gate enforces per-send hygiene but cannot stop an agent that shells out to raw herdr.
A periodic audit SHALL grep for `herdr agent prompt` and `send-text` outside the wrapper across agent homes.

Rationale: Shell escapes cannot be prevented, only audited.
