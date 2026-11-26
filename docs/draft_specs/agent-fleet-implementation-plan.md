# Agent Fleet Coordination Implementation Plan

## Overview

This document outlines the phased implementation plan for the agent fleet coordination system specified in [Agent Fleet Coordination Technical Specification](agent-fleet-spec.md).
The plan breaks the work into independently testable phases, each delivering working functionality.

## Phase 1: Fleet Skill and Core Infrastructure

This phase creates the agent-fleet skill structure and documentation.

### Phase 1 Deliverables

- Create `skills/agent-fleet/` with SKILL.md following repository skill authoring standards.
  Extract the skill text from `docs/draft_specs/agent-fleet-skill-draft.md` (the fenced markdown block).
- Move draft reference files from `docs/draft_specs/agent-fleet/` to `skills/agent-fleet/references/`.
- Create `skills/agent-fleet/references/agent-kinds.yaml` with verified data for pi and unverified templates for other kinds.
- Document fleet setup in the skill: work-area creation, per-agent homes, inbox directories, lead directories.
- Document agent lifecycle commands: launch, relaunch with continuity, addressing, teardown.
- Document safe-send integration: referencing `skills/herdr/scripts/herdr_send.py` with correct relative paths.
- Document task delivery: goal-loop commands, command-first discipline, agent-kind-specific behavior.
- Document kickoff ritual invocation: when to run, what it prints, how to interpret output.

### Phase 1 Tests

- Skill loads without errors in all supported runtimes.
- Skill references resolve to existing files.
- Agent-kinds YAML at `skills/agent-fleet/references/agent-kinds.yaml` validates against its schema.
- Path references in SKILL.md work from agent home and fleet skill contexts.
  The draft skill text is in `docs/draft_specs/agent-fleet-skill-draft.md`.

### Phase 1 Quality Gates

- `just lint-md` passes on SKILL.md and all references.
- Skill YAML frontmatter validates per repository standards.
- All paths and commands in the skill are testable.

Traceability: Implements R-FLEET-022 (Fleet Skill Coverage), R-FLEET-024 (Safe-Send Wrapper Path).

## Phase 2: Kickoff Script

This phase implements the kickoff script for state recovery after compaction.

### Phase 2 Deliverables

- Create `skills/agent-fleet/scripts/` directory.
- Implement `kickoff.py` as a thin entry point.
- Implement `agent_fleet_lib/kickoff.py` with the kickoff logic.
- Support `--as <name>` flag and inference from cwd.
- Support `AGENT_WORK_ROOT` environment variable with fallback to inferred root.
- Print 7 sections: identity, liveness, todos, inbox, rules, repo status, lead block.
- Pure reads with truncation and "read the file" pointers.
- Type hints throughout.
- Error messages as `Error: <message>` lines, not tracebacks.

### Phase 2 Tests

- Offline unit tests with fake herdr runner (100 percent line and branch coverage).
- Test identity inference from cwd and `--as` flag.
- Test `AGENT_WORK_ROOT` override and fallback.
- Test each section's output independently.
- Test lead-only block appears only for lead agent.
- Test error handling: missing board file, unreadable inbox, herdr not available.
- Test truncation and file pointers.

### Phase 2 Quality Gates

- pytest with 100 percent line and branch coverage.
- mypy passes with no errors.
- radon MI grade A.
- xenon B.
- No lint suppressions.
- `just ci` passes.

Traceability: Implements R-FLEET-004 (Work Root Environment Variable), R-FLEET-015 (Mechanized Kickoff Ritual), R-FLEET-023 (Implementation Quality Standards).

## Phase 3: Leader-Wake Policy CLI

This phase implements the leader-wake policy management CLI.

### Phase 3 Deliverables

- Create `skills/agent-fleet/leader-wake/` directory.
- Implement `leader-wake-policy` as a thin entry point.
- Implement `leader_wake_lib/policy.py` with CRUD operations.
- Commands: `show`, `get <key>`, `set <key> <value>`, `prompt`, `check`.
- XDG-compliant config location: `~/.config/leader-wake/policy.yaml`.
- Seed `policy.schema.json` on first run.
- Hot-reload support: policy changes visible at next daemon tick.
- One atomic validating writer for policy.yaml.
- Type hints throughout.
- Error messages as `Error: <message>` lines, not tracebacks.

### Phase 3 Tests

- Offline unit tests with temporary config directories (100 percent line and branch coverage).
- Test each CRUD operation independently.
- Test schema validation on set.
- Test XDG location resolution.
- Test seeding of schema file.
- Test error handling: missing config, invalid YAML, schema violations.

### Phase 3 Quality Gates

- pytest with 100 percent line and branch coverage.
- mypy passes with no errors.
- radon MI grade A.
- xenon B.
- No lint suppressions.
- `just ci` passes.

Traceability: Implements R-FLEET-007 (Leader-Wake Daemon), R-FLEET-008 (Wake Reasons), R-FLEET-020 (One Validating Writer per Structured File), R-FLEET-023 (Implementation Quality Standards).

## Phase 4: Leader-Wake Daemon Core

This phase implements the leader-wake daemon core with tick loop and wake conditions.

### Phase 4 Deliverables

- Implement `leader-wake` as a thin entry point.
- Implement `leader_wake_lib/daemon.py` with tick loop.
- Implement `leader_wake_lib/conditions.py` with wake condition evaluators.
- XDG-compliant state location: `~/.local/state/leader-wake/state.yaml` and `wake_log.yaml`.
- One tick = read fleet from herdr, evaluate conditions, maybe prompt, always log.
- Wake preconditions: lead idle or done, empty input box, not compacting, at least one reason fires, subject to cooldown and rate-limit.
- Wake reasons: work-pending, stall-likely, blocked, backlog-review, running-review, stuck-input, board-blocked, hourly-duties.
- Failed prompt delivery does NOT consume cooldown.
- Append-only decision log.
- Type hints throughout.
- Error messages as `Error: <message>` lines, not tracebacks.

### Phase 4 Tests

- Offline unit tests with fake herdr runner and temporary state directories (100 percent line and branch coverage).
- Test each wake reason independently.
- Test wake preconditions.
- Test cooldown enforcement.
- Test rate-limit enforcement.
- Test failed prompt does not consume cooldown.
- Test decision log append.
- Test state persistence across ticks.
- Test policy hot-reload.

### Phase 4 Quality Gates

- pytest with 100 percent line and branch coverage.
- mypy passes with no errors.
- radon MI grade A.
- xenon B.
- No lint suppressions.
- `just ci` passes.

Traceability: Implements R-FLEET-007 (Leader-Wake Daemon), R-FLEET-008 (Wake Reasons), R-FLEET-020 (One Validating Writer per Structured File), R-FLEET-023 (Implementation Quality Standards).

## Phase 5: Leader-Wake Systemd Integration

This phase documents leader-wake systemd integration for production use.

### Phase 5 Deliverables

- Create `skills/agent-fleet/leader-wake/leader-wake.service` systemd user unit template.
- Document manual installation steps in `skills/agent-fleet/references/leader-wake-setup.md`.
- Unit file specifies `After=herdr.service`, `Restart=on-failure`.
- Document how to enable, disable, start, stop, and check status.
- Document log location and troubleshooting.

### Phase 5 Tests

- Manual test: install service, start it, verify it ticks, verify it stops.
- Manual test: restart herdr, verify service restarts after.
- Manual test: check logs show tick decisions.

### Phase 5 Quality Gates

- Service installs without errors on representative system (systemd-based Linux).
- Service starts and ticks successfully.
- Service respects After= dependency.
- Service restarts on failure.

Traceability: Implements R-FLEET-007 (Leader-Wake Daemon) systemd integration.

## Phase 6: Reference Templates and Examples

This phase creates reference templates and examples for fleet operation.

### Phase 6 Deliverables

- Create `skills/agent-fleet/references/policy-schema.yaml` with complete schema documentation.
- Document `skills/agent-fleet/references/agent-kinds.yaml` structure as the reference schema for agent-kinds data.
- Create `skills/agent-fleet/references/decision-queue-template.md` with example decision cards.
- Create `skills/agent-fleet/references/example-agents-md.md` with per-agent AGENTS.md structure.
- Create `skills/agent-fleet/references/kickoff-usage.md` with invocation examples and output interpretation.
- Create `skills/agent-fleet/references/leader-wake-setup.md` with daemon installation and operation.

### Phase 6 Tests

- All YAML schemas validate.
- All Markdown references pass `just lint-md`.
- All examples are internally consistent.

### Phase 6 Quality Gates

- `just lint-md` passes on all reference files.
- YAML validates against schemas.
- Cross-references between files resolve correctly.

Traceability: Implements R-FLEET-010 (Evergreen Dispatch Pool), R-FLEET-011 (Operator Decision Queue), R-FLEET-013 (Multi-Agent-Kind Support).

## Phase 7: Integration and Documentation

This phase integrates all components and creates end-to-end documentation.

### Phase 7 Deliverables

- Wire kickoff script into fleet skill SKILL.md with usage instructions.
- Wire leader-wake into fleet skill SKILL.md with setup and operation instructions.
- Update skill README to link all scripts and references.
- Create end-to-end setup guide in `skills/agent-fleet/references/setup-guide.md`.
- Document agent-kind verification process and compatibility matrix.
- Document known limits from R-FLEET-025, R-FLEET-026, R-FLEET-027.

### Phase 7 Tests

- End-to-end manual test: set up a minimal fleet, launch agents, run kickoff, start daemon, verify wake.
- Verify kickoff works from agent home and fleet skill contexts.
- Verify daemon prompts lead when conditions fire.
- Verify safe-send gate integration with file drops and pings.

### Phase 7 Quality Gates

- End-to-end test completes without errors.
- All documentation cross-references resolve.
- `just ci` passes on entire skill.

Traceability: Completes all requirements R-FLEET-001 through R-FLEET-027.

## Phase 8: CI and Quality Checks

This phase wires all tests into CI for automated quality enforcement.

### Phase 8 Deliverables

- Wire all Python tests into `just ci`.
- Add GitHub CI workflow for agent-fleet tests.
- Add GitLab CI job for agent-fleet tests.
- Ensure coverage reports aggregate across all test modules.
- Document CI setup in skill README.

### Phase 8 Tests

- CI runs all tests automatically on PR.
- Coverage enforcement blocks merge if below 100 percent for new code.

### Phase 8 Quality Gates

- GitHub CI passes.
- GitLab CI passes.
- `just ci` passes.
- No lint suppressions.

Traceability: Implements R-FLEET-023 (Implementation Quality Standards) CI integration.

## Phase 9: Agent-Kind Verification

This phase verifies agent-kind commands interactively across all supported runtimes.

### Phase 9 Deliverables

- Verify pi agent kind (already implemented and tested).
- Create test agents for claude, codex, cursor, agy, xorc.
- Verify task delivery commands for each kind interactively.
- Verify relaunch commands for each kind interactively.
- Update `skills/agent-fleet/references/agent-kinds.yaml` to mark verified kinds.
- Document verification results in compatibility matrix.
- Document unverified kinds as requiring confirmation.

### Phase 9 Tests

- Manual interactive test per kind: launch, deliver task, verify receipt, relaunch with continuity.
- Document test procedure and results.

### Phase 9 Quality Gates

- At least pi kind fully verified.
- Other kinds marked as unverified with instructions.
- Compatibility matrix documents verification status.

Traceability: Implements R-FLEET-013 (Multi-Agent-Kind Support) verification.

## Non-Goals for This Implementation

Items explicitly NOT part of this implementation:

- No `fleet.yaml` or `fleet.py` status files (per R-FLEET-019).
- No roster file (addressing from herdr session names).
- No cached pane map (liveness read live from herdr).
- No checksum-based sync tooling (decision queue verified against source, not synced).
- No automatic systemd service installation (manual per Q1 recommendation).
- No adaptive stall detection (fixed threshold per Q6 recommendation).
- No per-agent stall thresholds (single policy threshold per Q6 recommendation).
- No creation of `docs/requirements/` (requirements in `docs/draft_specs/` per layout guidance).

## Dependencies

Each phase depends on the previous phases completing:

- Phase 2 depends on Phase 1 (needs skill structure and agent-kinds data).
- Phase 3 depends on Phase 1 (needs skill structure).
- Phase 4 depends on Phases 1 and 3 (needs skill structure and policy CLI).
- Phase 5 depends on Phase 4 (needs daemon implementation).
- Phase 6 can run in parallel with Phases 2-5 (reference templates are independent).
- Phase 7 depends on Phases 1-6 (integration needs all components).
- Phase 8 depends on Phases 2-4 (needs Python code to test).
- Phase 9 depends on Phase 7 (needs complete working system to verify).

## Success Criteria

The implementation is complete when:

- All phases deliver their defined outputs.
- All quality gates pass.
- `just ci` passes on the entire codebase.
- End-to-end test completes successfully.
- All requirements R-FLEET-001 through R-FLEET-027 are implemented and tested.
- Open questions Q1 through Q14 are resolved with documented decisions, and Q15 is decided before Phase 3 ships the daemon.
- Compatibility matrix documents verification status for all agent kinds.

## Open Questions Resolutions (Q1-Q14 Resolved, Q15 Open, Q16 Optional)

Q1: Manual installation (Option B) - addressed in Phase 5.
Q2: Configurable with default 3 (Option C) - policy field documented in Phase 3.
Q3: Test agent verification (Option A) - executed in Phase 9.
Q4: Part of fleet skill package (Option B) - structure defined in Phase 2.
Q5: Single file for open, archive for resolved (Option C) - template in Phase 6.
Q6: Fixed time per policy (Option A) - policy field documented in Phase 3.
Q7: Python with ruamel.yaml from venv (Option B) - matching todos.py and task-management, in Phase 2-4.
Q8: Validate at both times (Option C) - policy CLI validates at write, daemon at start.
Q9: Hash of last N lines only (Option A) - stall algorithm in Phase 4.
Q10: Markdown with H3 headings (Option A) - evergreen pool format in Phase 6.
Q11: Plain text for agent reading (Option A) - kickoff output in Phase 2.
Q12: One fleet per repository (Option A) - single work-root design in Phase 1.
Q13: Skill default plus per-project override (Option B) - agent-kinds location in Phase 1.
Q14: Walk up from cwd to find agent_files/ (Option B) - kickoff and tools in Phase 2.
Q15: Daemon launch and herdr_send `HERDR_ENV` requirement (open) - addressed in Phase 3.
Q16: Pending message selector by sender or role (optional future work) - keep id-based drop (Option A).
