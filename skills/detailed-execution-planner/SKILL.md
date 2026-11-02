---
name: detailed-execution-planner
description: Creates and updates test-gated Cursor, Claude Code, or native Xorc execution plans. Invoke only when explicitly called by user.
user-invocable: true
disable-model-invocation: false
---
# Detailed Execution Planner

## Skill Purpose

Write execution plans that are specific, test-gated, and aligned with requirements and technical specifications, for work that needs a step-by-step sequence before coding starts.

## Before Building Plan

Ask the user about anything you are not certain of, one question at a time, until no ambiguity remains.

## Select the Plan Target

Determine the target from the user's request, any existing plan, and the available host tools.
If those signals conflict or establish no target, ask rather than guessing or combining schemas, and keep each target's fields and lifecycle operations out of the others' artifacts.

- Xorc `.xorcp.md`: follow [Xorc Planning Workflow](references/xorc-plans.md) with the [Core Rules](#core-rules) and the step naming rules in [Step Format](#step-format), but not the checklist, template, or frontmatter.
- Cursor `.plan.md`: follow every section below, including [Cursor Frontmatter](#cursor-frontmatter).
- Claude Code: follow [Claude Code Planning Workflow](references/claude-plans.md) and every section below except Cursor Frontmatter.

## Core Rules

1. Treat requirements as the source of truth, then technical specs, then current implementation, and read all three before planning.
2. If requirements or specs are missing, ambiguous, or contradictory, stop and call out the gap.
3. Plan only the work the user directed and the defects it discovers; a spec, review, or register entry is a finding, not a task, until the user directs it.
4. Give each task exactly one focus area or feature, sized as one red-green-refactor cycle: one failing test or gate, one production change in one package or symbol family, one cleanup, one landing.
5. Make each task self-contained, with its own Requirements and Specifications list, Discovery, Red, Green, Refactor, Testing, and Closeout, so it can be executed and validated on its own.
6. For code changes, use BDD/TDD: update behavior specs first, write failing tests, make the smallest change that passes them, refactor only when green, and add functional tests for user-facing or API-facing behavior.
7. End each phase with a validation gate and an explicit hold point, such as "do not start the next task until this passes".
8. Cite, for every acceptance or completion criterion, the owner decision or canonical requirement that sets it; add no criterion without one.
9. When updating a plan, read all of it first, keep completed steps and their evidence unless now invalid, place new steps in the right task and phase, and revise only what is pending or invalidated.
10. Leave out filler sections, generic advice, and narrative.

## Step Format

Write every step as a flat, top-level `- [ ]` / `- [x]` line under `## Execution Plan`.
Headings group steps; never nest a checkbox under another, and split a step with sub-steps into lines such as `- [ ] Higher-level step - sub-step 1 (concrete action).`

Each step must let an executor act without guessing, so it names, where applicable:

- the exact command, such as `go test ./pkg/... -run TestName` or `just e2e`, never "run the tests";
- the package paths, directories, or globs in scope, in backticks;
- the test names, files, tags, or BDD scenario titles, never "all 3 tests" or "the new tests";
- the files or symbols to change, and any output artifact such as a report path or migration name.

When names are unknown at plan time, the step says how they will be found, such as "list failing tests from `go test ./...` and add each as a step in the next revision".
Never rely on unstated context, as in "fix the handler" or "update as needed".

## Planning Workflow

1. Gather the goal, the requirement and spec documents, the code, tests, and docs likely to change, and the gaps, assumptions, dependencies, and risks.
2. Record what must change, what must not, what is deliberately excluded, any parity or migration constraints, the required test types, and the completion criteria.
3. Read [`assets/plan-template.md`](assets/plan-template.md) and draft from it unless the user asks for another structure; drop its frontmatter for Claude Code.
   Close each task with a completion report (what was done, what passed, deviations), then mark its completed steps `- [x]` as its last step.
   End with a documentation and closeout task that ends in a final plan completion report.
4. For Cursor, fill in the frontmatter after the body.
5. Check the finished plan against every rule above before handing it over.

## Cursor Frontmatter

A Cursor plan begins with YAML frontmatter so it can be imported and tracked as todos.

- `name`: a short plan title.
- `overview`: a `|` block summarizing goal, scope, and approach.
- `todos`: one entry per checkbox line under `## Execution Plan`, in the same order and with the same meaning; headings are not steps.

Each todo has these fields.

- `id`: a stable unique id, such as `my-plan-step-001`.
- `content`: as specific as its checkbox line, never shortened.
- `status`: `pending` or `completed`; `pending` for a new plan unless the user marks work done.
- `dependencies`: for a linear plan, the previous step's `id`; use parallel tracks only when the user asks.

Change `todos` in the same edit as every change to the checklist.
