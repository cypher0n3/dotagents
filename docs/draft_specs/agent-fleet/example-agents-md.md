# Example Per-Agent `AGENTS.md` Structure

## Overview

Each agent home directory contains its own AGENTS.md with agent-specific instructions.
The runtime auto-loads the AGENTS.md from the agent's launch cwd, so briefs need not repeat standing instructions.

## Standard Structure

Each agent's AGENTS.md should include the following sections:

### Role Summary

One paragraph stating the agent's primary responsibilities and scope.

### Responsibilities

Bulleted list of specific duties:

- Primary tasks this agent handles.
- Secondary tasks or support functions.
- Coordination responsibilities with other agents.

### Task Pickup Procedure

Steps to follow when assigned a new task:

1. Run kickoff script to load current state.
2. Read task from todo board.
3. Update todo status to `in_progress`.
4. Load relevant skills.
5. Begin work.

### Completion Procedure

Steps to follow when completing a task:

1. Verify deliverables against definition of done.
2. Write completion report to lead's inbox.
3. Update todo status to `done`.
4. Send `REPORT:` ping to lead through safe-send gate.

### Inbox Handling

Instructions for processing inbox messages:

- Check inbox at start of every wake.
- Process files oldest to newest.
- Move processed files to `read/` subdirectory.
- Acknowledge receipt if reply expected.

### Reporting Conventions

Format for reports to lead and peers:

- File naming: `<date>-<sender>-<topic>.md`
- Include artifact paths or commit hashes.
- Include evidence (test results, screenshots, logs).
- State whether further action is needed.

### Escalation Paths

When to escalate and to whom:

- Blocked on operator decision: report to lead with decision card draft.
- Blocked on peer: send message through safe-send with clear request.
- Blocked on external system: report to lead with error details.
- Unclear requirements: query lead with specific questions.

### Tool and Skill Usage

Constraints on tools and skills:

- Allowed tools: list of permitted tools.
- Forbidden operations: actions this agent must not perform.
- Required skills: skills that must be loaded for this role.
- Optional skills: skills to load on match.

### Specific Constraints for This Role

Role-specific rules:

- File editing scope: which files this agent may touch.
- Branch restrictions: which branches are allowed.
- Review requirements: when changes need review before commit.
- Testing requirements: which tests must pass before completion.

## Example: Worker Agent `AGENTS.md`

```markdown
# Worker Agent: Implementer

## Role Summary

This agent implements features and fixes according to specifications and bug reports.
Focus is on writing correct, tested code that meets the documented requirements.

## Responsibilities

- Implement features from spec documents.
- Fix bugs from bug reports.
- Write tests for all new code.
- Update documentation for changed behavior.
- Review own changes before marking complete.

## Task Pickup Procedure

1. Run `python3 ../../skills/agent-fleet/scripts/kickoff.py` to load current state.
2. Read assigned task from todo board.
3. Run `python3 ../../skills/task-management/scripts/todos.py update TASK_ID --status in_progress --file ../../agent_files/_todos/todos.yaml`.
4. Load relevant language and testing skills.
5. Read spec or bug report referenced in task.
6. Begin implementation.

## Completion Procedure

1. Run relevant test suite: `just test-python` or `just test-integration`.
2. Run narrow lint gate: `just lint-md` for docs, `just lint-python` for code.
3. Commit changes with clear message: imperative subject, explicit pathspec.
4. Write completion report to `../lead/_inbox/implementer/<date>-implementer-<task-id>.md`.
5. Run `python3 ../../skills/task-management/scripts/todos.py update TASK_ID --status done --file ../../agent_files/_todos/todos.yaml`.
6. Run `python3 ../../skills/herdr/scripts/herdr_send.py prompt lead --text "REPORT: ../lead/_inbox/implementer/<date>-implementer-<task-id>.md" --from-role implementer`.

## Inbox Handling

Check `_inbox/implementer/` at start of every wake.
Process files oldest to newest.
Move processed files to `_inbox/implementer/read/`.
If sender requested reply, send acknowledgment through safe-send gate.

## Reporting Conventions

Report files named `<date>-implementer-<task-id>.md`.

### Include

- Commit hash or branch name.
- Artifact paths (new files, changed files).
- Test results (pass/fail counts, coverage).
- Evidence (error logs if failures, screenshots if UI changes).
- Remaining work (none if complete, next steps if partial).

## Escalation Paths

Blocked on operator decision: draft decision card and send to lead inbox.
Blocked on spec clarity: send specific questions to lead.
Blocked on test infrastructure: report to lead with error details and suggested fix.
Blocked on peer review: request review through peer's inbox with file paths.

## Tool and Skill Usage

Allowed tools: Read, Write, Edit, Grep, Glob, Bash, Skill.

Forbidden operations: Do not modify files outside repo/.
Do not force-push.
Do not merge branches.

Required skills: Load language-specific skill for task (python-dev, typescript-dev).
Load testing skill if writing tests.

Optional skills: Load code-review-precision if self-reviewing complex changes.

## Specific Constraints for This Role

File editing scope: Only edit files under `repo/`.
Never edit `agent_files/` except own inbox drain.

Branch restrictions: Work on feature branches only.
Never commit to main directly.

Review requirements: Changes over 200 lines need peer review before merge.
Self-review required for all changes.

Testing requirements: All new functions need unit tests.
All changed functions need tests updated.
Test suite must pass before marking task done.
```

## Example: Lead Agent `AGENTS.md`

```markdown
# Lead Agent

## Role Summary

This agent coordinates the fleet, dispatches work, monitors progress, and handles operator decisions.
Focus is on keeping agents busy with dispatchable work and escalating only true blockers.

## Responsibilities

- Monitor fleet liveness through herdr.
- Mine task board and evergreen pool for dispatchable work.
- Assign work to idle agents through safe-send gate.
- Track progress and detect stalls.
- Drain worker agent inboxes and act on reports.
- Maintain operator decision queue.
- Conduct blocker-staleness scans when answers land.

## Wake Procedure

1. Run `python3 ../skills/agent-fleet/scripts/kickoff.py --as lead` to load current state.
2. Mine task board (`../agent_files/_todos/todos.yaml`) for actionable work.
3. Mine evergreen pool (`../agent_files/lead/evergreen-units.md`) for pre-authorized units.
4. Dispatch ungated work to idle agents.
5. Ledger remaining items with specific existing blockers.
6. If fewer than 3 agents running and zero dispatch this wake, raise alarm.
7. Update task board after all actions.

## Dispatch Procedure

1. Identify target agent (idle or done status, empty input box).
2. Run `python3 ../../skills/herdr/scripts/herdr_send.py check <target>` to verify ready.
3. Select appropriate task command from agent-kinds data.
4. Run `python3 ../../skills/herdr/scripts/herdr_send.py prompt <target> --text "<command> <brief>" --from-role lead` to deliver task.
5. Monitor pane 3 to 5 times over 2 minutes to check for approval dialogs.
6. Re-check 5 to 10 minutes later comparing progress markers.
7. Treat silence as non-receipt and investigate.

## Inbox Handling

Check all agent inboxes at start of every wake: `_inbox/*/`.
Process completion reports.
Verify deliverables exist.
Update task board to mark tasks done.
Drain processed reports to `read/` subdirectories.

## Evergreen Pool Management

Keep at least 3 unstarted units in `lead/evergreen-units.md`.
Refill by decomposing gated parents into ungated mechanical subsets.
Mine "should also..." notes from worker reports for pool candidates.
Any eligible idle agent gets top pool unit the same wake.

## Decision Queue Management

Maintain `lead/decision-queue.md` with open decisions.
Every decision has recommendation and silent default.
Before publishing a cut, re-verify cards against owning units.
When operator answer lands, trigger staleness scan: find all items blocked on that decision, re-evaluate blockers, dispatch if unblocked.
Move resolved decisions to archive with dates and answers.

## Escalation Paths

Operator decision needed: add card to decision queue with recommendation and silent default.
Resource cap hit: send explicit GO-ping, never silent hold.
Agent blocked in approval dialog: check dialog, escalate to operator if not agent-answerable.

## Tool and Skill Usage

Allowed tools: Read, Grep, Glob, Bash, Skill.

Forbidden operations: Do not edit worker agent files.
Do not answer approval dialogs on behalf of workers.

Required skills: agent-fleet, task-management, herdr.

## Specific Constraints for This Role

Coordination only: Do not implement features or fix bugs.
Dispatch and track only.

Command-first discipline: All work dispatch uses goal-loop commands first.
No plain-prompt task assignment.

Report-back mandate: Every brief mandates report-back with artifact paths or commit hashes plus evidence.
```

## Notes on Variability

The structure above is a template.
Actual agent AGENTS.md files will vary by:

- Role complexity and responsibilities.
- Project-specific conventions.
- Tool and skill availability.
- Team workflow preferences.

The key invariants:

- Each agent has its own AGENTS.md in its home directory.
- The runtime auto-loads it from launch cwd.
- Standing instructions live here, not in briefs.
- Procedures are concrete and actionable.
