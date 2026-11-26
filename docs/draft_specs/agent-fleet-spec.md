# Agent Fleet Coordination Technical Specification

## Overview

This specification defines the design for an autonomous agent fleet system where a supervisor (lead) coordinates multiple worker agents in herdr panes through file-based coordination.
The system builds on `skills/herdr/scripts/herdr_send.py` for safe sends and `skills/task-management` for work tracking.
It introduces a new `agent-fleet` skill covering fleet setup, the leader-wake daemon, kickoff ritual, and dispatch protocol.

Traces To: R-FLEET-001 through R-FLEET-027 in [Agent Fleet Coordination Requirements](agent-fleet-requirements.md)

## Directory Layout

Traces To: R-FLEET-002, R-FLEET-003, R-FLEET-004, R-FLEET-006, R-FLEET-010, R-FLEET-011, R-FLEET-019

A project work area using the agent fleet system organizes files as:

```text
<work-root>/
  AGENTS.md                       fleet-wide rules (auto-loaded by every agent)
  repo/                           the git repository
  agent_files/
    <agent-name>/                 per-agent home: AGENTS.md + runtime dir
    _todos/todos.yaml             task board (THE work source, managed by task-management CLI)
    _inbox/<target>/              inbox for file drops, one directory per agent
      read/                       drained inbox items
    lead/
      evergreen-units.md          dispatch pool of pre-authorized units
      decision-queue.md           operator decision queue with silent defaults
      dispatch-protocol.md        standing dispatch mechanics for lead
```

Durable agent material lives in `agent_files/`, never in the repo and never in `/tmp`.
Agents are launched with cwd set to their home directory so the runtime auto-loads that agent's AGENTS.md.
Briefs carry only current state plus task; doctrine lives in AGENTS.md files and skill references.

The system deliberately does NOT create or maintain `fleet.yaml`, `fleet.py`, roster files, or cached pane maps:

- Liveness comes from `herdr agent list` and `herdr agent get`, read live.
- Work comes from `agent_files/_todos/todos.yaml`, managed by `skills/task-management`.
- Doctrine comes from AGENTS.md files, skill references, and `dispatch-protocol.md`.
- Pane addressing comes from herdr session names and pane IDs.

The `AGENT_WORK_ROOT` environment variable specifies the project work root.
When not set, tools walk up from cwd to find `agent_files/`, then require `AGENT_WORK_ROOT` if the search fails.

## Skill Structure

Traces To: R-FLEET-022, R-FLEET-024

A new skill under `skills/agent-fleet/` covers the complete fleet lifecycle.
The skill name `agent-fleet` describes its purpose: coordinating a fleet of autonomous agents.
The skill DEPENDS ON but does NOT duplicate `skills/herdr` and `skills/task-management`.

The skill covers:

- Fleet and per-agent setup (work-area layout, agent homes with AGENTS.md, inbox directories).
- Agent lifecycle in herdr (launch, relaunch with continuity, addressing, teardown).
- Leader-wake daemon (setup as systemd user service, policy file and CLI, wake reasons and preconditions).
- Lead wake procedure (order of operations, evergreen pool, dispatch mechanics).
- Kickoff ritual (task-start script invocation, state recovery after compaction).
- Tracking work through the task board (task-management CLI usage).
- Operator decision queue (queue index structure, silent defaults, staleness checks).
- Multi-agent-kind support (agent-kind-specific task delivery and relaunch).

The skill's SKILL.md follows repository skill authoring standards: imperatives, one H1, no bold lead-ins, no fragments, no embedded examples.
The proposed skill text is in `docs/draft_specs/agent-fleet-skill-draft.md` as a fenced markdown block.
Supporting material (policy schema, agent-kinds data, example AGENTS.md, decision queue template, kickoff usage) goes in references under the draft spec directory during the draft phase, then moves to `skills/agent-fleet/references/` when implemented.

## Safe-Send Integration

Traces To: R-FLEET-005, R-FLEET-016, R-FLEET-024

The system uses the existing `skills/herdr/scripts/herdr_send.py` for all agent-to-agent sends.
The herdr skill already implements:

- Busy detection: empty input box verified from visible screen.
- Fail-closed policy: unverifiable input frame, unsubmitted text, or blocked dialog all refuse the send.
- Working target handling: working targets are allowed by default and the message is queued; only `--disable-working` refuses them with exit 12.
- Multi-line refusal: only single-line sends are allowed; long content goes to file drops.
- Wait and retry: `--wait SECONDS` retries while busy up to a timeout.

The agent-fleet skill REFERENCES the herdr skill's safe-send capability but does NOT reimplement it.
Agents use the wrapper as `python3 skills/herdr/scripts/herdr_send.py` or `python3 ../../skills/herdr/scripts/herdr_send.py` depending on working directory context.

The wrapper's commands are `check`, `prompt`, `run`, `pending list`, and `pending drop`.

The `check` and `prompt` commands accept `--wait SECONDS` (default: 0 for `check`, 180 for `prompt`).
On a refusal, the command backs off and retries with exponential delays: starting from `--interval` (default 2s), doubling up to 30s, with +/-20% jitter.
Exits 10 (except `no_profile` reason), 11, and 12 trigger retries; exits 13, 14, 20, 21, and the `no_profile` reason stop immediately.
Once environment, validation, and target resolution succeed, `prompt` saves the message first, then waits for delivery.
On timeout or refusal, the message stays saved and `prompt` returns the last refusal code (not 0).
A later `prompt` to the same target delivers saved messages oldest first.

Exit codes are:

- 0: delivered (not merely saved)
- 2: usage error (fix the command)
- 10: unsubmitted input, missing TUI profile, input frame or prompt row, state change during checks, or another caller is sending this message now (missing TUI profile fails at target resolution before the save; other cases save before waiting; on timeout the exit is the last refusal's code; check with `pending list`)
- 11: blocked dialog (ask the user)
- 12: working target with `--disable-working`, `unknown` state, missing state field, or `interactive_ready` false (message saved if applicable)
- 13: missing, ambiguous, own-pane, wrong-kind, or agent-owned `run` target, or another caller dropped or expired the message (already dead, nothing to drop) (fix the target or resend)
- 14: not inside herdr (stop)
- 20: herdr command failure (inspect the error)
- 21: invalid message text, missing header part, unreadable `--file`, or `pending drop` usage error (fix the input)

For reports: write the file to `agent_files/_inbox/<target>/<date>-<sender>-<topic>.md`, then send one `REPORT: <path>` ping through the wrapper.
The target drains the inbox by moving read files to `_inbox/<target>/read/`.

## Task Delivery

Traces To: R-FLEET-012, R-FLEET-013, R-FLEET-014, R-FLEET-017

Work dispatch uses goal-loop commands, not plain prompts.
Plain prompts are reserved for non-work traffic such as acknowledgments, coordination, and close-outs.
The system enforces command-first discipline: slash commands must be the first characters of the send.

The system supports multiple agent kinds (pi, claude, codex, cursor, agy, xorc).
Agent-kind-specific behavior is defined in a configuration file at `skills/agent-fleet/references/agent-kinds.yaml`.
During the draft phase, the reference template is at `docs/draft_specs/agent-fleet/agent-kinds.yaml`.

Each agent kind defines:

- Task commands: templates for new precise brief, new draft, redirect running goal, resume idle goal.
- Relaunch command: template for relaunch with continuity (session preservation).
- State field: which herdr field holds the agent state.

Every non-pi delivery or relaunch command is marked as UNVERIFIED and must be confirmed per kind during implementation.

Agent-to-agent messages include a header:

```text
FROM: <role> (<pane>) - AGENT INPUT - REPLY: <yes/no>

<message body>
```

The header states that the message is agent input, not an operator instruction, and whether a reply is expected.

Every work brief mandates report-back: artifact paths or commit hashes plus evidence.
Briefs in spec or ground-truth-bound lanes carry a definition-of-done citation.

## Kickoff Ritual

Traces To: R-FLEET-015

A task-start script is run at the START of every task and after any compaction instead of trusting memory.
The script is a reference template during the draft phase at `docs/draft_specs/agent-fleet/kickoff-usage.md`.
When implemented, it will be part of the agent-fleet skill.

The kickoff script prints:

1. Agent identity (from launch cwd `agent_files/<name>/` or `--as <name>`)
2. Live fleet liveness from `herdr agent list` (authoritative; never cached)
3. The agent's todo-board items from `agent_files/_todos/todos.yaml`
4. Unread lead briefs in `agent_files/_inbox/<name>/`
5. Standing rules: submitted messages, todo hygiene, reporting and pane-send gate, persistence, commit style, plus a pointer to the fleet rules and dispatch-protocol
6. In-flight repo work (git status summary) so agents don't collide
7. EVERGREEN block: for the lead only, pool pointer plus wake-discipline summary

The script reads work root by walking up from cwd to find `agent_files/`, then falls back to `AGENT_WORK_ROOT` if the search fails.
The script is pure reads, with truncation and explicit "read the file" pointers.

## Leader-Wake Daemon

Traces To: R-FLEET-007, R-FLEET-008

A standalone daemon watches the fleet through herdr and prompts the lead only when conditions say it should act.
Detection is deterministic; every prompt tells the lead to verify before acting.

Two executables plus a config CLI:

- `leader-wake`: the daemon.
  One tick = read the fleet, evaluate wake conditions, maybe deliver one prompt, always log the decision.
- `leader-wake-policy`: CRUD for the policy file (show, get, set, prompt, check); every knob documented in the policy schema; the daemon hot-reloads the policy at the next tick.

XDG layout:

- Config: `~/.config/leader-wake/policy.yaml` (plus seeded `policy.schema.json`)
- State: `state.yaml` (per-pane output hashes, cadence timestamps) and append-only decision log `wake_log.yaml` under `~/.local/state/leader-wake/`
- Systemd user unit (`After=herdr.service`, `Restart=on-failure`), not enabled at boot by default.

The policy names a `work_area`; the todos path is relative to it, so the installed daemon needs nothing from any checkout.

Wake preconditions (all must hold):

- Lead is herdr `idle` or `done`.
- Lead's input box is empty (or holds only a recognized stuck draft).
- Lead is not compacting.
- At least one wake reason fires.
- Subject to `cooldown_seconds` and `max_prompts_per_hour`.

Wake prompts are delivered through `python3 skills/herdr/scripts/herdr_send.py prompt <lead-name> --text "<prompt>" --from-role leader-wake --wait 0 --disable-working`.
The `--wait 0` flag ensures the daemon does not block for the default 180s wait.
The `--disable-working` flag ensures the daemon does not queue a message for a lead that is already working.
By default, `prompt` allows working targets and saves messages for later delivery.

On any non-zero exit where a message was saved, the daemon parses `message_id` from the JSON report and runs `python3 skills/herdr/scripts/herdr_send.py pending drop <message_id>` to prevent stale wakes from being delivered later.
The `message_id` appears in the stdout report on successful saves.
Failures before the save (exit 10 no_profile, most exit 13 cases, exit 14, exit 21) produce no `message_id` and nothing to drop.
An exit 13 where the message was dropped or expired elsewhere carries a `message_id`, but the message is already dead.
The `pending drop <message_id>` command drops exactly that one message and does not call the `HERDR_ENV` check.

The daemon handles `herdr_send.py` exit codes as follows (derived from `skills/herdr/scripts/herdr_lib/checks.py` and `commands.py` on commit `0adab33`):

- Exit 0 (`EXIT_SUCCESS`): Prompt delivered successfully.
  The daemon starts the cooldown timer and continues ticking.
- Exit 2 (`EXIT_USAGE_ERROR`): The command is misconfigured.
  The daemon logs a fatal error and exits.
  Operator action: fix the command in the daemon or policy configuration.
- Exit 10 (`EXIT_BUSY`): One of: unsubmitted input text in the target pane, missing input frame, missing input prompt row, state sequence changed during checks, another caller is sending this message now, or missing TUI profile.
  Missing TUI profile fails at target resolution before the save and carries no `message_id`.
  The daemon logs a config error and stops without dropping anything.
  Other exit 10 cases save the message before waiting.
  On timeout the exit is the last refusal's code (10, 11, or 12).
  The daemon parses `message_id` from the report, runs `pending drop <message_id>` to remove the saved wake, logs the skip, does NOT consume the cooldown, and retries at the next tick.
  Operator action: check the lead pane for stuck input or scrolled screen, or add missing TUI profile.
- Exit 11 (`EXIT_BLOCKED`): Target is showing an approval dialog.
  The message is saved before waiting.
  The daemon parses `message_id`, runs `pending drop <message_id>`, logs it, does NOT consume the cooldown, and retries at the next tick.
  Operator action: answer the dialog in the lead pane.
- Exit 12 (`EXIT_WORKING_REFUSED`): One of: working target with `--disable-working`, `unknown` agent status, `interactive_ready` is `False`, missing `state_change_seq` field, or missing `agent_status` field.
  The message is saved before waiting (working check runs after save).
  The daemon parses `message_id`, runs `pending drop <message_id>`, logs the skip, does NOT consume the cooldown, and retries at the next tick.
  Operator action: none needed if working; investigate if `unknown` or missing fields persist.
- Exit 13 (`EXIT_TARGET_ERROR`): One of: no agents found, target not found, target ambiguous, cannot send to own pane, wrong agent kind, agent-owned `run` target, or another caller dropped or expired the message.
  Most failures happen before save and carry no `message_id`.
  When another caller dropped or expired the message (commands.py:425-431), the message is already in `dead/` and the report carries a `message_id`; there is nothing to drop.
  For the dropped/expired case the daemon logs the skip and retries at the next tick.
  For other exit 13 cases the daemon logs a fatal error and exits.
  Operator action: for dropped/expired, nothing to do (resend if still needed); for other cases, fix the target name in policy configuration or restart the lead agent.
- Exit 14 (`EXIT_NOT_IN_HERDR`): `HERDR_ENV != 1`.
  Failure before save; no `message_id` and nothing to drop.
  The daemon logs a fatal error and exits.
  Operator action: see Q15 for options to run the daemon outside herdr panes.
- Exit 20 (`EXIT_HERDR_ERROR`): The `herdr` CLI call failed: agent list, agent get, pane read, or other herdr command.
  May be before or after save depending on which call failed.
  If `message_id` is present in the report, the daemon runs `pending drop <message_id>`.
  The daemon logs the error, does NOT consume the cooldown, and retries at the next tick.
  Operator action: check herdr server status and daemon logs for the herdr error message.
- Exit 21 (`EXIT_INVALID_INPUT`): The prompt template is misconfigured, the message file is unreadable, or `pending drop` usage error.
  Failure before save; no `message_id` and nothing to drop.
  The daemon logs a fatal error and exits.
  Operator action: fix the prompt template in policy configuration.

A failed prompt delivery (any exit other than 0) does NOT consume the cooldown.
Unsubmitted input in the target pane is busy (exit 10), not working.
This is the same rule the safe-send gate enforces, so the daemon and the send-gate never fight the operator.

Wake reasons (each tick may carry several):

- `work-pending`: actionable work exists with fewer than `min_other_agents_working` workers running, or a stall is suspected.
- `stall-likely: <agent>`: a working pane's output tail is unchanged for `stall.seconds` (hash of tail lines); evidence ships inside the prompt.
- `blocked: <agent>`: any agent sits in herdr `blocked` (approval or question dialog).
- `backlog-review`: actionable-work count is zero; on the transition, then per `backlog_review_seconds`.
- `running-review`: lead idle while few agents (at least 1, under `running_review_max_agents`) run; per `review_seconds`.
- `stuck-input`: the lead's input box holds the SAME unsubmitted draft for `stuck_input_ticks` consecutive ticks.
- `board-blocked`: board todos with status `blocked`; listed with reasons in the prompt.
- `hourly-duties`: duties checklist appended to any wake per `duty_seconds`; never fires alone.

Actionable work = agent-assigned todos on the board.
Queued work is a board item with status `pending`.
A todo with no explicit status counts as `pending`.
The open-status set is policy (`work.statuses`).

The policy schema reference is at `docs/draft_specs/agent-fleet/policy-schema.yaml` during the draft phase.

The daemon logs every tick (wake or skip, with reasons) to `wake_log.yaml` so "why didn't the lead move for two hours" is answerable.

## Lead Wake Procedure

Traces To: R-FLEET-009, R-FLEET-010, R-FLEET-018

A wake may end "no action" only after this order:

1. Mine the task board plus markers plus the evergreen pool FIRST.
2. Decompose gated parents; dispatch the ungated parts (mechanical subsets under established rules, pre-staged manifests or decision packets).
3. Ledger, as proof of empty: each remaining item must name a specific existing blocker (an operator letter that exists in the queue index, or a named artifact).
   An unnamable blocker is not a blocker: dispatch now.
4. Alarm threshold: fewer than N eligible agents running plus zero dispatch this wake.
5. Resource caps get explicit GO-pings, never silent holds.
6. Every operator answer landing re-opens a scan: blockers go stale.

Evergreen pool (`lead/evergreen-units.md`):

- Pre-authorized, ungated, useful units.
- Keep at least 3 unstarted.
- Any eligible idle agent gets the top unit the same wake.
- Refill by decomposing gated parents and mining "should also..." notes in reports.

Liveness after dispatch:

- Read the pane 3 to 5 times about 30 seconds apart (approval dialogs sit unseen).
- Re-check 5 to 10 minutes later comparing progress markers.
- Silence is not receipt.

## Operator Decision Queue

Traces To: R-FLEET-011

A versioned queue index (`lead/decision-queue.md`):

- One card per open operator decision.
- Each with a recommendation and a silent default (what happens if the answer never arrives).
- Silence must never strand work silently.

Every cut re-checks cards against landed work before publishing.
An audit that copies a NEEDS-OWNER verdict without grepping the owning unit for a RESOLVED section ships phantom decisions.

Every landed answer triggers the blocker-staleness scan.

The decision queue template reference is at `docs/draft_specs/agent-fleet/decision-queue-template.md` during the draft phase.

## Per-Agent `AGENTS.md` Structure

Traces To: R-FLEET-003

Each agent home contains its own AGENTS.md with agent-specific instructions.
The structure reference is at `docs/draft_specs/agent-fleet/example-agents-md.md` during the draft phase.

Each agent's AGENTS.md includes:

- Role summary
- Responsibilities
- Task pickup and completion procedures
- Inbox handling
- Reporting conventions
- Escalation paths
- Tool and skill usage
- Specific constraints for the role

The runtime auto-loads the AGENTS.md from the agent's launch cwd, so briefs need not repeat standing instructions.

## Failure Modes and Mechanisms

Traces To: R-FLEET-001, R-FLEET-005, R-FLEET-009, R-FLEET-015, R-FLEET-016, R-FLEET-019, R-FLEET-021

This table maps failure classes to the mechanisms that prevent them:

- Send collides with operator typing: safe-send visible-screen busy check, fail closed, multi-line ban.
- Prompt sent but never submitted: submitted-only rule; `herdr agent prompt` (auto-Enter) as only send path.
- Report floods a pane or gets lost: inbox file-drop plus one-line `REPORT:` ping; drain on wake.
- Wake ends "no action" while work is queued: wake procedure plus written ledger plus evergreen pool at least 3.
- Silent hold at a resource cap: caps require explicit GO-pings.
- Rules re-forgotten after compaction: kickoff script replaces memory.
- Prose rule ignored under pressure: the rule lives in the send/start scripts, not only in AGENTS.md.
- Half-remembered fleet state: kickoff prints live truth (herdr plus board); no cached status file.
- Status mirror file goes stale: fleet-style status files retired (liveness from pane manager, work from board, doctrine from AGENTS.md).
- Work dispatch invisible in history: goal-loop-only dispatch, COMMAND FIRST.
- Stale "blocked on owner" parking: per-wake ledger with quotable blockers; staleness scan.
- Phantom queue items from audits: re-verify against the owning unit's RESOLVED sections.
- Fixes that break ground truth: definition-of-done citation in bound-lane briefs.
- Durable artifacts evaporating: scratch dirs banned as staging; artifacts land in final location incrementally.

## Known Limits

Traces To: R-FLEET-025, R-FLEET-026, R-FLEET-027

Name-based targeting requires the runtime's session-name reporting.
Panes without a name must be addressed by pane ID.

Screen-based busy detection requires the input frame rendered.
Alt-screen scrollback-only apps or scrolled-back targets read as BUSY (safe but conservative).
The inbox path is the fallback.

The gate enforces per-send hygiene but cannot stop an agent that shells out to raw herdr.
Audit periodically: greps for `herdr agent prompt` and `send-text` outside the wrapper across agent homes should only ever show the wrapper.

## Open Questions

The following questions require resolution before or during implementation.

### Q1: Leader-Wake Systemd Integration

Should the leader-wake daemon be automatically installed as a systemd user service during fleet setup, or should it be a manual step documented in the skill?

#### Q1 Options

- A: Automatic installation with `systemctl --user enable --now leader-wake.service` during setup.
- B: Manual installation with documented commands in the skill reference.
- C: Optional installation with a setup script flag.

Q1 Recommendation: B (manual installation).
Reason: Systemd user services persist across sessions and auto-starting a daemon should be an explicit operator choice, not a side effect of skill setup.

### Q2: Evergreen Pool Minimum Size

Should the evergreen pool minimum size be hardcoded at 3 or configurable per policy?

#### Q2 Options

- A: Hardcoded at 3 units minimum.
- B: Configurable in `policy.yaml` as `evergreen.min_units`.
- C: Configurable with 3 as the default.

Q2 Recommendation: C (configurable with default 3).
Reason: Different fleet sizes and workload patterns may need different thresholds, but most cases work well with 3.

### Q3: Agent-Kind Verification Process

How should non-pi agent kinds be verified during implementation?

#### Q3 Options

- A: Create a test agent of each kind and verify commands interactively.
- B: Document commands as unverified and rely on user reports.
- C: Add kind-specific tests to the wrapper with mock TUI profiles.

Q3 Recommendation: A (test agent verification).
Reason: Interactive verification catches integration issues early.
Document verified kinds in a compatibility matrix in the skill.

### Q4: Kickoff Script Distribution

Should the kickoff script be a standalone file or part of the fleet skill Python package?

#### Q4 Options

- A: Standalone `agent_files/_bin/kickoff.py` copied during setup.
- B: Part of the fleet skill package, invoked as `python3 -m agent_fleet_lib.kickoff`.
- C: Standalone script generated from a template in skill references.

Q4 Recommendation: B (part of the fleet skill package).
Reason: Package distribution ensures version consistency and reduces setup steps.
The package can still be invoked from any working directory via `python3 -m`.

### Q5: Decision Queue Workflow

Should the decision queue be a single versioned file or separate files per decision?

#### Q5 Options

- A: Single `decision-queue.md` with all decisions, versioned by date.
- B: Separate files per decision in `lead/decisions/<id>.md`.
- C: Single file for open decisions, archive for resolved.

Q5 Recommendation: C (single file for open, archive for resolved).
Reason: One file is easier to review and grep.
Archiving resolved decisions prevents the file from growing unbounded.

### Q6: Stall Detection Threshold

Should the stall detection threshold be a fixed time or adaptive based on the agent's typical response time?

#### Q6 Options

- A: Fixed time configurable per policy (default 1800 seconds).
- B: Adaptive per agent based on historical average plus margin.
- C: Fixed time with per-agent overrides in policy.

Q6 Recommendation: A (fixed time per policy).
Reason: Simpler to implement and reason about.
Adaptive thresholds add complexity and require state tracking.
Operators can tune the fixed threshold if needed.

### Q7: Daemon Implementation Language

Should the leader-wake daemon be implemented in Python (matching the kickoff script and herdr_send wrapper) or another language?

#### Q7 Options

- A: Python with stdlib only, matching the kickoff script and herdr_send wrapper.
- B: Python with dependencies for YAML parsing and schema validation.
- C: Go or Rust for performance and single-binary distribution.

Q7 Recommendation: B (Python with ruamel.yaml dependency).
Reason: Matches the todos.py and task-management approach.
The policy YAML includes comments and multiline strings that stdlib `json.loads()` cannot parse.
Using `ruamel.yaml` from the project venv keeps YAML parsing consistent across fleet tools and task-management.
R-FLEET-023 is relaxed to allow ruamel.yaml and jsonschema from requirements.txt, matching task-management's dependency set.

### Q8: Policy Validation Timing

When should policy validation occur?

#### Q8 Options

- A: Only at write time with `leader-wake-policy set`.
- B: Only at daemon start.
- C: At write time and at daemon start.

Q8 Recommendation: C (validate at both times).
Reason: Catch errors early at write time, but also validate at start in case the file was hand-edited.
Fail fast with clear error messages.

### Q9: Stall Detection Algorithm

What data should the stall detection algorithm use?

#### Q9 Options

- A: Hash of the last N lines of output only.
- B: Hash of last N lines plus total output length.
- C: Hash of last N lines plus output length plus agent state changes.

Q9 Recommendation: A (hash of last N lines only).
Reason: Simplest and catches actual stalls (no new output).
Adding length detects appends, but that is progress.
State changes are already monitored separately.

### Q10: Evergreen Pool Format

What format should the evergreen pool use?

#### Q10 Options

- A: Markdown with H3 headings per unit.
- B: YAML with structured unit definitions.
- C: Markdown for human editing with YAML frontmatter for metadata.

Q10 Recommendation: A (Markdown with H3 headings).
Reason: Human-editable, greppable, no schema needed.
The lead parses it by splitting on H3 and extracting text.

### Q11: Kickoff Output Format

Should the kickoff script output plain text or structured data?

#### Q11 Options

- A: Plain text formatted for agent reading.
- B: JSON for programmatic parsing.
- C: Markdown with sections as H2 headings.

Q11 Recommendation: A (plain text formatted for agent reading).
Reason: The script's purpose is to load state into agent context, not to produce machine-readable output.
Plain text is easier for agents to understand.

### Q12: Multi-Repo Fleet Support

How should the fleet handle multiple repositories?

#### Q12 Options

- A: One fleet per repository, no cross-repo coordination.
- B: Single fleet work area with multiple `repo/` subdirectories.
- C: Single fleet with repository paths in task metadata.

Q12 Recommendation: A (one fleet per repository).
Reason: Simplest model, matches current work-root design.
Cross-repo coordination can use separate fleets that coordinate through external channels if needed.

### Q13: Agent-Kinds Configuration

Where should agent-kinds configuration live?

#### Q13 Options

- A: Single file in skill: `skills/agent-fleet/references/agent-kinds.yaml`.
- B: Skill default plus optional per-project override at `agent_files/agent-kinds.yaml`.
- C: Only per-project file at `agent_files/agent-kinds.yaml`.

Q13 Recommendation: B (skill default plus optional per-project override).
Reason: Common kinds work out of the box, projects can override for custom runtimes or commands.
Skill default provides verified pi config and templates for others.

### Q14: Work Root Inference

When `AGENT_WORK_ROOT` is not set and the kickoff script is part of the fleet skill package, how should it infer the work root?

#### Q14 Options

- A: Require `AGENT_WORK_ROOT` environment variable, fail if not set.
- B: Walk up from current directory to find `agent_files/` directory.
- C: Use a config file in the agent home that points to the work root.

Q14 Recommendation: B (walk up from cwd to find `agent_files/`).
Reason: Works when invoked from any agent home without requiring env var.
Falls back to requiring `AGENT_WORK_ROOT` if search fails.
Matches how tools commonly find project roots.

### Q15: Leader-Wake Daemon Launch and `HERDR_ENV` Requirement

How should the leader-wake daemon satisfy `herdr_send.py`'s `HERDR_ENV=1` requirement when running as a systemd user service outside herdr?

The guard at `skills/herdr/scripts/herdr_lib/checks.py:26-29` on commit `0adab33` checks `os.environ.get("HERDR_ENV") != "1"` and raises exit 14 when false.
Per `skills/herdr/SKILL.md`, this variable confirms the caller is running inside a herdr pane.
The guard does not check herdr server reachability; a `herdr` CLI failure is exit 20.
The current implementation has no `--external-caller` or similar flag to bypass this check.

#### Q15 Options

- A: Run the daemon inside a dedicated herdr pane, launched at fleet setup, instead of systemd.
  The pane stays open and the daemon runs in the foreground.
- B: Extend `herdr_send.py` with an explicit `--external-caller` flag that skips the `HERDR_ENV` check for legitimate external callers like the daemon.
  Document this mode and require the flag so the guard stays in place for normal use.
- C: Document that systemd sets `Environment=HERDR_ENV=1` in the service unit, accepting that the daemon runs outside a herdr pane.

Q15 Recommendation: B (add `--external-caller` flag to `herdr_send.py`).
Reason: The `HERDR_ENV` guard confirms the caller is inside a herdr pane where the environment is controlled.
The daemon is a legitimate external caller that explicitly invokes the `herdr` CLI, which finds its server independently.
An explicit `--external-caller` flag documents the exception and keeps the guard in place for normal agent-to-agent use.
Option A works but ties the daemon to a herdr pane, which is fragile for a background service that should restart automatically.
Option C sets the variable without being inside a pane, which sidesteps the guard's intent.

Q15 remains open: the `--external-caller` flag does not exist in commit `0adab33`.

### Q16: Pending Message Selector by Sender or Role

Should `pending drop` gain a first-class selector by sender or role, or is id-based drop sufficient?

#### Q16 Options

- A: Keep id-based drop only.
  The daemon parses `message_id` from the `prompt` report and drops by id.
  Works today and is recommended.
- B: Add `--from-role` or sender filter to `pending list` and `pending drop`.
  Would allow `pending drop --target <lead> --from-role leader-wake`.
  Requires storing role (not just `sender_pane`) in saved messages.
  A systemd daemon has no `HERDR_PANE_ID`, so `sender_pane` matching won't work.
- C: Add target plus index selector: `pending drop --target <lead> --index 0` for the oldest waiting message.
  Fragile if other senders exist.

Q16 Recommendation: A (keep id-based drop).
Reason: The current `message_id`-based approach works, requires no changes to `herdr_send.py`, and avoids `HERDR_ENV` checks.
Parsing `message_id` from JSON is straightforward.
Options B and C are future enhancements if other use cases emerge, but the daemon's needs are met today.

Q16 is optional future work and does not block the fleet implementation.

## Traceability

Each section above traces to its requirements.
Every requirement from R-FLEET-001 through R-FLEET-027 is covered by at least one specification section.
