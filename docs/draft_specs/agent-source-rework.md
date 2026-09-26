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

4. There are four tiers, mapped for Claude Code as follows:
   - `frontier` maps to `fable`.
   - `strong` maps to `opus`, and is the tier for coder, reviewer, reviewer-go, and planner.
   - `standard` maps to `sonnet`, and is the tier for researcher, test-runner, spec-author, feature-author, and docs-writer.
   - `fast` maps to `haiku`.

   Codex, Cursor, and CAI have no tier mappings yet, so their agents use the session's model until mappings are added to the generator.
   Hermes personalities cannot set a model.
   The existing Claude Code agents therefore keep their current `model` values.

5. An agent source file uses flat keys that read like a Claude Code agent, plus one optional block per tool:

   ```yaml
   ---
   name: reviewer
   description: Performs adversarial review of ...
   model: strong
   color: red
   readonly: true
   tools: [Read, Grep, Glob, Bash]
   skills: [senior-developer, code-review-precision]
   suggested_skills: []
   codex:
     model_reasoning_effort: high
   ---
   # Reviewer
   ```

   - `color` applies only to Claude Code.
   - `readonly` and `tools` state intent; each tool enforces them where it can and states them as comments where it cannot.
   - `skills` are loaded before the agent starts, and `suggested_skills` when a task needs them.
   - A block named after a tool holds settings only that tool has.

   No tool reads a source file directly.
   The generator rejects any key it does not know, so a typo fails generation instead of being ignored.
   Each generated file carries only the keys its tool is known to accept, so a key one tool does not recognize never reaches that tool, and intent a tool cannot express appears there only as a comment.
   How each tool treats an unknown key is therefore not relied on, and has not been verified for Codex, Cursor, Hermes, or CAI.

6. Every agent is generated for every tool by default.
   An agent opts out of specific tools with an optional `exclude` list, such as `exclude: [hermes]`.
   Adding a new tool to the generator therefore needs no change to any agent file.

## Open Questions

- Whether output files are written by Jinja templates or directly by generator code.
