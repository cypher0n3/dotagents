# CAI Planning Workflow

## Native Contract

Use this workflow only for a requested CAI execution plan.
Load CAI's available `plan-creator` skill through `ingest_skill` and inspect the current schemas of its planning tools before creating or changing a plan.
Treat that native workflow and the workspace's requirements and specifications as authoritative; do not substitute the Cursor template from this package.
If the native skill or required planning tools are unavailable, report the missing capability and stop native authoring rather than inventing tool calls or presenting a prose checklist as an executable CAI plan.

A persisted CAI plan is a `.caip.md` artifact with native identity, title, lifecycle state, timestamps, and structured tasks containing steps.
Its Markdown body is explanatory text, not executable task state.
Do not convert Cursor `name`, `overview`, `todos`, or checkbox status into CAI task state merely by renaming the file.

## Scope and Task Quality

Read the relevant project instructions, requirements, specifications, current code, and any existing plan before decomposing work.
If sources disagree, record the gap and ask for direction; do not modify canonical requirements or specifications without authorization.

- Define the objective, exclusions, completion evidence, and validation commands.
- Give each task a clear purpose and references to the applicable source documents or identifiers.
- Give each step a concrete action and purpose, with exact commands, paths, test selectors, or a discovery action that identifies them.
- Include observable verification criteria and failure handling where needed.
- For code changes, include applicable behavior specifications, failing tests, minimal implementation, refactoring, and functional coverage.
  For research or documentation, use relevant evidence and validation rather than inventing a code-testing phase.
- Keep each task independently understandable and give it a validation gate and concise closeout.
- Express prerequisites as a dependency DAG; do not use array order as an execution constraint.
  Keep genuinely independent tasks independent unless the user requests a linear sequence.

## Create a Draft

1. Call `plan_init` with the title, objective, and idempotency key required by the current schema.
   Retain the returned string `plan_id`, artifact path, and version.
2. Call `plan_add_tasks` with the returned identity, the observed `expected_version`, an idempotency key, and bounded task batches accepted by the current schema.
   Supply task client keys, titles, purposes, references, and steps rather than hand-writing runtime-owned IDs or timestamps.
3. Use `depends_on_task_ids` for existing persisted task IDs and `depends_on_client_task_keys` for prerequisites in the same batch.
   Do not pass the persisted `depends_on` field as an authoring-tool argument.
4. Use returned versions for subsequent mutations and follow the tool's concurrency and idempotency contract.
   On validation or version errors, inspect the current artifact and correct the request rather than blindly retrying or duplicating tasks.
5. Read the resulting plan through the native plan inspection surface and verify its objective, complete task and step coverage, dependencies, references, and draft state.
   Report only the artifact and state actually returned by the tools.

Let CAI choose the artifact location and manage persistence.
Do not create `.cai/`, move a plan between project and XDG storage, or fabricate approval timestamps to force a desired lifecycle state.
Creating a draft does not authorize proposing, approving, activating, or executing it.
For ordinary non-goal plans, leave those transitions to the user; for an active goal, follow the native trusted goal workflow without claiming user approval or expanding its scope.

## Update an Existing Plan

Read the entire current plan and its observed version through the native inspection surface first.
Use the installed native update tools for supported mutations, preserving completed work and its evidence, exact plan identity, valid dependencies, and applicable references.
Do not reinitialize an existing plan to approximate an edit, invent unsupported update operations, or silently rewrite it as a Cursor plan.
If the installed tools cannot represent the requested change, explain the limitation and ask for direction.

Record completion only from observed execution evidence and successful per-task validation.
If a human-readable checklist is maintained in the body, keep it consistent with native task state without using it as the source of execution status.
Do not invoke `update-cursor-todos` for CAI.

## Final Verification

Read back the persisted plan after the final mutation and confirm every requested task, step, reference, dependency, and verification condition is represented.
Confirm the plan uses CAI's native schema and contains no Cursor `todos` substitution.
Report its path, observed state, validation results, and unresolved gaps; do not report planned tests as already passed or a saved draft as approved or running.
