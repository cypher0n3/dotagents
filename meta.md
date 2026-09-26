# `dotagents` - Project Meta

## Purpose of This File

My global [`AGENTS.md`](./AGENTS.md) tells agents to read a repository's `meta.md` first, so this file exists to orient one quickly.
It deliberately does not repeat the [README](./README.md); read that for what the project is, how to install it, and how it is laid out.

## Repository Boundaries

This repository owns skill definitions, the agents that preload them, written once in `agent_sources/` and generated for each tool, the standards that govern both, and the tooling that generates, validates, and installs them.

It does not own agent tool configuration, machine setup, project-specific instructions, or prompts that only make sense inside one codebase.
A skill that cannot be stated without naming a single private repository belongs in that repository instead, as a project-local skill.
The same boundary applies to an agent: one that only makes sense inside one codebase belongs in that repository's own agent directory, such as `.claude/agents/`, where it overrides the portable agent of the same name.

It also does not claim to be a neutral or authoritative standard.
A skill here is a considered opinion of mine, and a repository's own conventions outrank it.

## Where to Look

- Rules for working in this repository: [`AGENTS.override.md`](./AGENTS.override.md)
- What a skill must contain: [`docs/docs_standards/skill_authoring.md`](./docs/docs_standards/skill_authoring.md)
- What an agent must contain: [`docs/docs_standards/agent_authoring.md`](./docs/docs_standards/agent_authoring.md)
- How agents are generated for each tool: [`docs/specs/shared-agent-templates.md`](./docs/specs/shared-agent-templates.md)
- How Markdown is written and linted here: [`docs/docs_standards/markdown_conventions.md`](./docs/docs_standards/markdown_conventions.md)
- What gates a change: `just ci`
