---
name: [Plan Title]
overview: |
  [One short paragraph on the intended outcome, scope, and major phases.]
todos:
  - id: [plan-slug]-step-001
    content: "[First checkbox step - same order as body.]"
    status: pending
  - id: [plan-slug]-step-002
    content: "[Second checkbox step.]"
    status: pending
    dependencies:
      - [plan-slug]-step-001
  # ... one todo per `- [ ]` line under ## Execution Plan, in order ...
---

# [Plan Title]

## Goal

[One short paragraph on the intended outcome.]

## References

- [Requirement documents]
- [Technical specifications]
- [Relevant implementation areas]

## Constraints

- [Key rule or constraint]
- [Key rule or constraint]

## Execution Plan

[Plan preamble]

### Task 1: [Name of This Task]

[Brief description of the task]

#### Task 1 Requirements and Specifications

- [Requirement or spec document]
- [Requirement or spec document]

#### Discovery (Task 1) Steps

- [ ] Read the requirements and specs relevant to this task (see above).
- [ ] Inspect the current implementation, tests, and docs that this task will change.
- [ ] Identify gaps or dependencies and resolve them before implementation.

#### Red (Task 1)

- [ ] Create or update the behavior definition and BDD scenarios for this task.
- [ ] Identify the unit, integration, and functional tests required for this task.
- [ ] Add or update automated tests, including functional tests for user-facing or API-facing behavior, so the new behavior fails for the right reason.
- [ ] Run `[exact command, e.g. go test ./path/... -run TestName]` and confirm the expected failures before implementation.
- [ ] Validation gate - do not proceed until those named tests fail for the expected reason.

#### Green (Task 1)

- [ ] Implement the smallest change set that satisfies the failing tests, with no unrelated refactors or speculative changes.
- [ ] Re-run the same command(s) from Red until they pass (name the command and package path).
- [ ] Validation gate - do not proceed until those same tests are green.

#### Refactor (Task 1)

- [ ] Improve structure, naming, or duplication where needed, without changing behavior.
- [ ] Re-run the same test command(s) from Green (name them); add lint if this refactor touched style or imports.
- [ ] Validation gate - do not proceed until refactor changes are verified.

#### Testing (Task 1)

- [ ] Run `[project lint command]` on changed packages or paths (name them).
- [ ] Run `[exact test command(s)]` covering this task (list package paths or `-run` patterns).
- [ ] If E2E or tagged tests apply, run `[e.g. just e2e scripts/.../module.py]` instead of "run all E2E".
- [ ] Confirm the implementation matches requirements and specs for this task.
- [ ] Validation gate - do not start the next task until all checks for this task pass.

#### Closeout (Task 1)

- [ ] Generate a **task completion report** for Task 1 - what was done (summary of changes and artifacts).
- [ ] Task completion report - what passed (tests, lint, validation).
- [ ] Task completion report - any deviations from the plan or notes for follow-up.
- [ ] Do not start Task 2 until this closeout is done.
- [ ] Mark every completed step in this task's section of the plan with `- [x]`. (Last step.)

[Repeat for each additional task: task heading, brief description, Task N Requirements and Specifications, Discovery (Task N) Steps, Red, Green, Refactor, Testing, **Closeout (task N)**.]

### Task N: Documentation and Closeout

- [ ] Update any required user-facing or developer-facing documentation.
- [ ] Verify no required follow-up work was left undocumented.
- [ ] Summarize completion criteria and any explicit remaining risks.
- [ ] Generate a **final plan completion report**: which tasks were completed, overall validation status, and any remaining risks or follow-up.
- [ ] Mark all completed steps in the plan with `- [x]`. (Last step.)
