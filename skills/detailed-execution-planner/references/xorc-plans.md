# Xorc Planning Workflow

## Native Contract

Load Xorc's `plan-creator` skill through `ingest_skill` and inspect the current schemas of its planning tools before creating or changing a plan.
That native workflow and the workspace's requirements and specifications are authoritative, and this package's template does not apply.
If the native skill or planning tools are unavailable, report that and stop rather than inventing tool calls or presenting a prose checklist as an Xorc plan.

A persisted Xorc plan is a `.xorcp.md` artifact with native identity, title, lifecycle state, timestamps, and structured tasks containing steps.
Its Markdown body is explanatory text, not task state, so renaming a Cursor plan does not turn its `todos` or checkboxes into Xorc tasks.

## Task Shape

These apply on top of the skill's core rules.

- Give each task a purpose and references to its source documents or identifiers.
- Give each step an action, a purpose, and observable verification criteria, with failure handling where needed.
- For research or documentation, validate with evidence rather than inventing a code-testing phase.
- Express prerequisites as a dependency DAG, not array order, and keep independent tasks independent unless the user asks for a linear sequence.
- Do not modify canonical requirements or specifications without authorization.

## Create a Draft

1. Call `plan_init` with the title, objective, and idempotency key the current schema requires, and keep the returned string `plan_id`, artifact path, and version.
2. Call `plan_add_tasks` with that identity, the observed `expected_version`, an idempotency key, and bounded task batches.
   Supply task client keys, titles, purposes, references, and steps, never runtime-owned IDs or timestamps.
3. Use `depends_on_task_ids` for persisted task IDs and `depends_on_client_task_keys` for prerequisites in the same batch, never the persisted `depends_on` field.
4. Use each returned version for the next mutation; on a validation or version error, inspect the artifact and correct the request rather than retrying blindly or duplicating tasks.
5. Read the plan back through the native inspection surface, check its objective, task and step coverage, dependencies, references, and draft state, and report only what the tools returned.

Let Xorc choose the artifact location; do not create `.xorc/`, move a plan between project and XDG storage, or fabricate approval timestamps.
A draft does not authorize proposing, approving, activating, or executing it.
Leave those transitions to the user for an ordinary plan, and for an active goal follow the native trusted goal workflow without claiming user approval or widening its scope.

## Update an Existing Plan

Read the plan and its observed version through the native inspection surface, then use only the installed native update tools, preserving plan identity, dependencies, and references.
Do not reinitialize a plan to approximate an edit, invent unsupported operations, or rewrite it as a Cursor plan; if the tools cannot represent the change, explain the limit and ask.
Record completion only from observed evidence, as `update-todos` does, and keep any checklist in the body following native task state rather than serving as its source.

## Final Verification

After the last mutation, read the plan back and confirm that every requested task, step, reference, dependency, and verification condition is present in the native schema with no Cursor `todos`.
Report its path, observed state, validation results, and unresolved gaps, never a planned test as passed or a draft as approved or running.
