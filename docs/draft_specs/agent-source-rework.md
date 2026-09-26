# Agent Source Rework

## Status

This is a working record of decisions for reworking the shared agent sources in [cypher0n3/dotagents#2](https://github.com/cypher0n3/dotagents/pull/2).
It is updated after each answer and is not yet a specification.

## Problem Statement

The owner asked for one source, defined in one place, that is easy to update and generates every output.
The implementation in the pull request does not meet that goal.
Changing one agent today can touch up to four kinds of files:

- `agent_sources/roles/<name>.yaml` holds the agent's description, model alias, skills, restrictions, and Claude color.
- `agent_sources/prompts/<name>.md` holds the agent's instructions.
- `agent_sources/targets/<tool>.yaml`, one per tool, holds how each tool spells each field and each tool's model aliases.
- `agent_sources/templates/<tool>.<ext>.j2`, one per tool, wraps the rendered pieces.

The generator code lives separately in `tools/agentgen/`.

## Decisions

1. One file per agent is the whole source for that agent.
   Its YAML frontmatter holds everything about the agent, including its description, model, skills, read-only intent, tool list, and any per-tool overrides, and its Markdown body holds the instructions.
   Editing that one file changes the agent for every tool.
   How each tool spells each field is built into the generator code, which is not edited to change an agent.
   The separate `roles/`, `prompts/`, and per-tool profile files are removed.

## Open Questions

- Where the per-agent source files live, and whether the Claude Code file is generated or is the source itself.
