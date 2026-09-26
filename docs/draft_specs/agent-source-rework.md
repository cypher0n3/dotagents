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

2. The per-agent source files live in a new folder, `agent_sources/<name>.md`, one Markdown file per agent.
   The generator writes the Claude Code agent to `agents/<name>.md`, and the Codex, Cursor, Hermes, and CAI outputs under `generated/`.
   `just install`, `validate_agents.py`, and the hand-maintained agent index `agents/README.md` keep using `agents/` unchanged.
   The Claude Code agent is generated output, never the source.

3. An agent's model is a tier word, such as `model: strong`, with optional per-tool overrides in the same file.
   The generator code maps each tier to each tool's model; a tool with no mapping for the tier, and no override, uses its session's model.
   An override names one tool and a model identifier that tool understands, and wins over the tier for that tool only.

   ```yaml
   model:
     tier: strong
     cursor: grok[high]
   ```

## Open Questions

- Which tier names exist, and what each maps to for each tool.
