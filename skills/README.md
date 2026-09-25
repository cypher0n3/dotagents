# Skill Index

## Overview

Each subdirectory here is one skill, addressed by its directory name and defined by its `SKILL.md`.
Agent tools read this directory through installed links, Hermes Agent external-directory registration, or CAI native discovery of `~/.agents/skills/`.
Changes take effect through each consumer's normal reload or session-start behavior; CAI watches its shared roots.
See [Skill Authoring Standards](../docs/docs_standards/skill_authoring.md) before adding or editing a skill.
The Claude Code agents in [`agents/`](../agents/README.md) preload skills from here by name, so renaming a skill also breaks any agent that lists it.

These skills are opinionated and reflect my own experience working with AI coding tools; see [Scope and Point of View](../README.md#scope-and-point-of-view) for the assumptions they carry and what to adapt before using them in another repository.
The skills are licensed under CC BY 4.0 and carry no per-file license notice; see [Licensing](../CONTRIBUTING.md#licensing) for how to attribute one you copy or adapt.

The *(user-invoked only)* label describes the intended invocation style; enforcement depends on the skill's `disable-model-invocation` metadata and the consuming tool.
Do not assume Hermes or CAI enforces another tool's invocation metadata; see [Hermes Agent](../README.md#hermes-agent) and [CAI](../README.md#cai).

## Design Notes

Notes explaining why a skill works the way it does are kept out of `SKILL.md`, because that file is loaded into the model's context on every invocation.

- [Why Grill Me Asks in Thread](grill-me/references/why-ask-in-thread.md) - why `grill-me` asks questions as ordinary text rather than through a harness question tool.

## Documentation and Specification Authoring

These skills carry the documentation, specification, and requirements conventions I use across my projects, along with the prose standards I hold a draft to.

- [`markdown-writer`](markdown-writer/SKILL.md) - Applies project documentation standards and markdownlint rules when writing or editing Markdown.
- [`spec-authoring`](spec-authoring/SKILL.md) - Applies repository-specific technical-specification standards to design and specification documents.
- [`requirements-authoring`](requirements-authoring/SKILL.md) - Applies repository-specific requirements standards to requirement documents.
- [`feature-files-authoring`](feature-files-authoring/SKILL.md) - Applies repository-specific Gherkin and BDD conventions to feature files.
- [`promote-specs-losslessly`](promote-specs-losslessly/SKILL.md) - Preserves every material detail when promoting drafts, design notes, or plans into canonical requirements and specifications.
- [`tech-specs-update`](tech-specs-update/SKILL.md) *(user-invoked only)* - Update the related tech specs and requirements as part of planned work.
- [`docs-only-convo`](docs-only-convo/SKILL.md) *(user-invoked only)* - Mark the current thread as only intended for updating documentation.
- [`strip-ai-tells`](strip-ai-tells/SKILL.md) - Rewrites AI-sounding prose until it reads as human-written.

## Software Development

These skills set the implementation and review bar for code changes.

- [`senior-developer`](senior-developer/SKILL.md) - Enforces senior developer coding standards: simple readable code, spec compliance, testability, and strict coverage.
- [`go-developer`](go-developer/SKILL.md) - Applies modern Go semantics, type safety, and secure secret handling when writing or refactoring Go.
- [`python-test-automation`](python-test-automation/SKILL.md) - Guides writing Python functional and end-to-end tests that validate application behavior.
- [`senior-go-dev-reviewer`](senior-go-dev-reviewer/SKILL.md) - Performs adversarial Go code review against specs, best practices, and production readiness.
- [`code-review-precision`](code-review-precision/SKILL.md) - Keeps a review to the findings that are real and worth acting on.
- [`just-ci`](just-ci/SKILL.md) - `just ci` final check must pass before execution is complete.

## Planning and Collaboration

These skills shape how an agent plans work and reports back on it.

- [`detailed-execution-planner`](detailed-execution-planner/SKILL.md) *(user-invoked only)* - Creates and updates test-gated Cursor plans or native CAI execution plans.
- [`update-cursor-todos`](update-cursor-todos/SKILL.md) *(user-invoked only)* - Updates Cursor plan and agent todo items; does not synchronize CAI plans.
- [`grill-me`](grill-me/SKILL.md) - Prompt me with questions, one at a time, until we have a shared understanding.
- [`agent-feedback`](agent-feedback/SKILL.md) *(user-invoked only)* - Quick prompt to indicate that the provided info was produced by another agent for consideration.

## Git Workflow

These skills cover the commit and merge steps at the end of a change.

- [`make-commit`](make-commit/SKILL.md) *(user-invoked only)* - Review staged changes and make a git commit.
- [`make-meta-commit`](make-meta-commit/SKILL.md) *(user-invoked only)* - Review staged changes in this repo and its submodules and make git commits.
- [`merge-prep`](merge-prep/SKILL.md) *(user-invoked only)* - Prepare for merge by cleaning up and consolidating commits.
