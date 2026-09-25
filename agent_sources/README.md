# Agent Sources

## Overview

This directory holds the shared source for every agent role, which the generator in [`tools/agentgen/`](../tools/agentgen/README.md) renders into each tool's native format.
Edit these files, never the generated ones, then run `just ci`, which regenerates everything before its other checks.
[Shared Agent Templates](../docs/specs/shared-agent-templates.md) is the full specification.

## Layout

- `roles/<name>.yaml` - one role: its name, description, body path, targets, model, skills, restrictions, presentation, and overrides.
- `prompts/<name>.md` - the role's instructions, plain Markdown held to the [agent authoring standards](../docs/docs_standards/agent_authoring.md) and never rendered as a template.
- `targets/<target>.yaml` - one tool's profile: its evidence, output directory, model aliases, and how it renders each field.
- `templates/<target>.<extension>.j2` - the thin Jinja wrapper that places the rendered pieces for one tool.

## Outputs

- [`../agents/`](../agents/README.md) - Claude Code agents.
- `../generated/codex/agents/` - Codex custom agents, as TOML.
- `../generated/cursor/agents/` - Cursor agents.
- `../generated/hermes/personalities/` - Hermes personalities, one JSON string per line.
- `../generated/cai/personas/` - CAI personas.
- `../generated/manifest.yaml` - what each output was generated from, and every decision the generator made for it.

## Workflow

1. Edit a role, its body, or a target profile.
2. Run `just ci`, or `just generate-agents` for generation alone.
3. Review and commit the regenerated files together with the source change.

A generated file edited by hand stops generation with an error naming it.
Move the change into the source and restore the file, or run `just generate-agents-accept-source` to discard the edit, which is also how a merge conflict in generated files is resolved.
