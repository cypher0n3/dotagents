# Skill Authoring Standards

## Overview

This document defines what a skill in this repository must contain, how it is named, and how it is validated.
It follows the [Agent Skills specification](https://agentskills.io/specification) and adds this repository's own conventions on top of it; where the two differ, the difference is called out.
Every rule here is enforced by `just ci` unless the text says otherwise.

## Directory Layout

Each skill is one directory under [`skills/`](../../skills/README.md) whose name is the skill's address.
Agents invoke the skill by that directory name, so the name is a stable public identifier and renaming one is a breaking change for anyone who has typed it into a workflow.

- `skills/<skill-name>/SKILL.md` is required and holds the frontmatter and the instructions.
- `skills/<skill-name>/agents/openai.yaml` supplies the OpenAI skill interface metadata and is present for every skill in this repository, so a new skill adds one too.
- `skills/<skill-name>/references/` is the place for supporting files a skill tells the agent to read on demand.
- `skills/<skill-name>/scripts/` and `skills/<skill-name>/assets/` are the specification's other optional directories, for executable code and for templates or data files.

Skill directory names use lowercase kebab-case.
Prefer a verb or role phrase that reads naturally after "use the" in a sentence, such as `make-commit` or `senior-go-dev-reviewer`.

## Frontmatter Contract

Every `SKILL.md` opens with YAML frontmatter delimited by `---` lines.

- `name` is required and must exactly match the containing directory name.
- `description` is required and tells the agent when to load the skill.
- `user-invocable` is optional and must be `true` or `false`.
  Set it to `true` for a skill the user calls deliberately by name, such as `/make-commit`.
- `license`, `compatibility`, and `metadata` are specification fields.
  `compatibility` is capped at 500 characters and should appear only when the skill has real environment requirements; `metadata` is the specification's home for arbitrary extra keys.
- `disable-model-invocation` prevents the model from invoking the skill on its own.
  Set it together with `user-invocable: true`, since a skill with neither route available cannot be reached at all.
  Use the pair for any skill that should run only when the user asks for it by name, such as one that commits, rewrites history, or sets the terms of a whole conversation.
- `allowed-tools`, `license`, `model`, and `version` are recognized when a target tool supports them.

Any other key is reported as a warning rather than an error, because agent tools add frontmatter fields on their own schedules.
Treat a warning as a prompt to check for a typo before assuming the key is a new upstream field.

## Writing the Description

The description opens with a label for the user.
That first line is what a person reads when scanning a list of skills, and its only job is to make clear what this skill is used for.

- Write one short line.
- Write it in the voice the user would use, first person included: "Prompt me with questions, one at a time, until we have a shared understanding."
- Name the distinguishing detail when it fits in the same breath, and leave it out when it does not.
- Do not turn the label into model-routing text, and do not pack it with trigger lists or comparisons to sibling skills.

A skill the model may invoke on its own adds exactly one more short sentence, in the form "Use this skill when ...", to say when it should fire.

```yaml
description: Applies modern Go semantics, type safety, and secure secret handling when writing or refactoring Go. Use this skill when writing or changing Go code.
```

A skill that only the user invokes carries the label alone, because the routing sentence would have nothing to route.

## No Comments in `SKILL.md`

A `SKILL.md` carries no HTML comments.

An HTML comment hides content from a Markdown viewer, not from the model: the file is injected into the model's context as raw text with its comments intact, so a comment costs context on every invocation while hiding nothing.
`just validate-skills` reports any comment in a skill body as an error, except inside a fenced code block, where a comment is sample content rather than a note.

Skill files also carry no per-file author or license line.
Authorship comes from version control, and the licensing that applies to a skill is stated in [LICENSE](../../LICENSE) and summarized in [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Keep Human-Only Material out of `SKILL.md`

Everything in a `SKILL.md` is loaded on every invocation, so the file should contain only what the agent needs in order to act.

Design rationale, history, alternatives that were rejected, and notes aimed at people reading or forking the skill do not belong there, whether as prose or as an HTML comment.
Put that material in one of these places instead:

- `skills/<skill-name>/references/` when it belongs with the skill and should travel with a copy of its directory.
  A file there is read only when something explicitly opens it, so it costs no context.
- The repository documentation under `docs/` when it explains a convention that spans several skills.

Reference the note from `skills/README.md` or the repository docs rather than from `SKILL.md`, so that reading it stays a human choice.

## Body Structure

The body opens with a single H1 that names the skill in title case, directly under the frontmatter, then goes straight into instruction content.

- Write instructions as imperative statements aimed at the agent, not as narration about the skill.
- Prefer short sections with an H2 per decision the agent has to make.
- Keep a `SKILL.md` under 500 lines and its body under roughly 5000 tokens, which is the size guidance in the Agent Skills specification.
  Move long checklists, templates, and examples into `references/` and tell the agent when to read them.
  `just validate-skills` warns when a skill passes either threshold; the thresholds are advisory, so a warning is a prompt to look rather than a failure.
- State the non-negotiable rules explicitly, including the ones that forbid an action, because an agent follows a stated prohibition far more reliably than an implied one.

Skill bodies are exempt from the heading and prose rules that govern the rest of this repository's documentation, because their formatting is written for agent attention.
They are still held to one sentence per line so that edits produce readable diffs.

## Portability Across Agent Tools

The same directory is read by Claude Code, Codex, Cursor, Gemini, Grok, and GitHub Copilot in VS Code through the symlinks that `just install` creates.
Write skills so that nothing breaks when a tool that lacks a given feature loads them.

- Do not hardcode absolute paths, machine names, or a single tool's directory layout.
- Refer to repository files by repository-relative paths so the skill works in any checkout.
- Describe tool actions in plain terms, such as "run the repository lint recipe", rather than naming one tool's built-in command.
- Put tool-specific presentation metadata in `agents/openai.yaml`, which needs `display_name`, `short_description`, and `default_prompt` under its `interface` key.

## Validation

Run the full local gate before committing a skill change.

- `just validate-skills` checks frontmatter, naming, and agent manifests.
- `just lint-md skills/<skill-name>/SKILL.md` applies Markdown fixes and reports what it cannot fix.
- `just validate-skills-spec` runs the upstream [skills-ref](https://github.com/agentskills/agentskills) validator when it is installed, and skips with a notice when it is not.
- `just ci` runs every check that CI runs.
