# Agent Authoring Standards

## Overview

This document defines what a Claude Code subagent in this repository must contain, how it is named, how its model and tools are chosen, and how it is validated.
It follows the [Claude Code subagent documentation](https://code.claude.com/docs/en/sub-agents) and adds this repository's own conventions on top of it.
Every rule here is enforced by `just ci` unless the text says otherwise.

The files under `agents/` are generated, together with the Codex, Cursor, Hermes, and CAI versions of each role, from role sources under [`agent_sources/`](../../agent_sources/README.md).
Every rule below describes the generated Claude Code agent, and is met by editing the role's source: the frontmatter comes from `agent_sources/roles/<agent-name>.yaml` and the body from `agent_sources/prompts/<agent-name>.md`.
[Shared Agent Templates](../specs/shared-agent-templates.md) specifies how each field maps to every tool.

An agent is a role with a system prompt, a model, a tool allowance, and a set of preloaded skills.
A skill is a rule set that any agent tool can load.
Keep that division: an agent says who is acting and with what, and the skills it preloads say how.

## Directory Layout

Each agent is one generated file, `agents/<agent-name>.md`, and the filename without its extension is the agent's address.
Its role source is `agent_sources/roles/<agent-name>.yaml`, and its body is `agent_sources/prompts/<agent-name>.md`.

- Do not edit a generated file directly: `just ci` regenerates every agent first, and fails, naming the file and writing nothing, when a generated file was edited by hand.
- Commit the regenerated files under `agents/` and `generated/`, with `generated/manifest.yaml`, in the same change as the source edit; hosted CI checks rather than regenerates.
- After a merge conflict in generated files, resolve the sources and run `just generate-agents-accept-source`, which rewrites every generated file from the sources.
Claude Code addresses the agent by that name, so renaming the file is a breaking change for anyone who has typed it into a workflow or a project-level override.

- [`agents/README.md`](../../agents/README.md) is the index and must link every agent; `just validate-agents` fails when one is missing.
- `just install` links each file into `~/.claude/agents` one at a time, so a new file needs no installer change and any agent already in that directory is left alone.
  An agent whose filename matches one already sitting there is reported as skipped rather than replaced, because the local file is the one Claude Code will use.
  Linking file by file cannot clean up after itself, so `just install` also reports anything else it finds in that directory, including the link a renamed agent leaves dangling, and removes none of it; a leftover and an agent you added on purpose look the same from the installer.
- A project overrides an agent by placing a file with the same name under its own `.claude/agents/`, which is where a version that names one codebase's recipes and identifiers belongs.

Agent names use lowercase kebab-case and read as a role: `reviewer`, `spec-author`.

## Frontmatter Contract

Every agent file opens with YAML frontmatter delimited by `---` lines.
The role source supplies each field: `name` and `description` directly, `model` through `model.claude` or the `model.alias` the Claude profile maps, `color` through `presentation.claude.color`, `tools` through `restrictions.tools`, and `skills` through `skills.required`.
The fields the generator does not render, such as `permissionMode` or `hooks`, cannot be set until the Claude target profile allows them.

- `name` is required and must exactly match the filename without its extension.
- `description` is required and is the routing text Claude Code uses to decide when to delegate to the agent.
- `model` is required by this repository, though Claude Code treats it as optional, and must be `sonnet`, `opus`, `haiku`, `fable`, `inherit`, or a full `claude-*` model identifier.
  Prefer an alias so the agent tracks the current release of its tier.
- `tools` is a comma-separated allowlist of tool names, and `disallowedTools` a denylist that Claude Code ignores when `tools` is set; omit both to inherit every tool.
- `skills` is a YAML list of skill names, each of which must exist as `skills/<name>/SKILL.md`.
  Claude Code preloads the full text of each named skill into the agent's context at start, so every entry is paid for on every run.
- `color` is required by this repository so an agent is identifiable at a glance, and must be one of `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, or `cyan`.
- `permissionMode`, `memory`, `isolation`, `maxTurns`, `effort`, `background`, `initialPrompt`, `experimental`, `mcpServers`, and `hooks` are recognized and checked against the values Claude Code documents.

Any other key is reported as a warning rather than an error, because Claude Code adds frontmatter fields on its own schedule.
Treat a warning as a prompt to check for a typo before assuming the key is a new upstream field.

## Preloading Versus Loading on Match

A preloaded skill is paid for on every run of the agent, whether or not the run needs it.
That is the right trade when the skill applies to everything the role does, and the wrong one when it applies to a fraction of the work.

- Preload a skill the role always needs, such as `markdown-writer` for an agent that only writes Markdown.
- Load a skill on match when which one applies depends on what the agent is handed, such as the language of a test or the type of a document.
  Give the agent the `Skill` tool, list the choices under their own H2, and tell it to load at most one and leave the rest unloaded.
- Do not do both for the same skill, and do not offer a choice so long that the agent has to reason about it; more than about six options means the role is really two roles.

An agent with no `Skill` tool cannot load anything beyond its preloads, which is the point for a role whose rules are fixed.

## Writing the Description

The description is read by the model, not by a person scanning a list, so it is routing text and is written as such.

- Open with one sentence saying what the agent produces.
- Add one sentence beginning "Use this agent when ..." that says the situation it is for.
- Write "Use proactively ..." instead when the main session should delegate without being asked, as the reviewer does after a change is written.
- Keep it under three sentences, and do not compare the agent to its siblings; distinct descriptions route better than descriptions that argue.

## Choosing the Model

Choose the model by what a mistake costs, not by what the agent is called.

- `opus` for roles where judgment is the product and a miss is expensive: implementation against a specification, adversarial review, and planning.
- `sonnet` for roles bounded by written conventions and a lint gate that catches drift: research, test running, and the authoring roles.
- `haiku` for a narrow agent that only searches or reformats and whose output is checked by something else.

Record the choice and its reason in [`agents/README.md`](../../agents/README.md), so a reader can disagree with the reasoning rather than guess at it.

## Choosing the Tools

Give an agent the smallest tool allowance its role needs, and state the prohibition in the body as well, because a tool list limits what the agent can call but the shell can still write files.

- A role that must not change the workspace, such as the reviewer or the researcher, lists read tools plus `Bash` for running checks, and its body says not to use the shell to edit.
- A role that writes only one kind of file, such as the planner or an author, lists read tools plus `Write` and `Edit`, and its body names the files it may touch.
- A role that chooses a skill from what it is handed adds `Skill` to that list, and no role gets `Skill` without a stated choice to make.
- A role that implements code omits `tools` and inherits the full set.

## Body Structure

The body is the agent's system prompt and is held to the repository's documentation conventions, including a single H1 with no content beneath it before the first H2, content under every heading, and one sentence per line.

- Open with an H2 that states the role in one or two sentences.
- Follow with the steps to take before starting, the working rules, and how to finish and report, each under its own H2.
- Write imperative instructions aimed at the agent, and state prohibitions explicitly, because an agent follows a stated prohibition far more reliably than an implied one.
- Tell the agent to read the repository's `meta.md`, `AGENTS.md`, and `AGENTS.override.md` first and to follow them over the prompt, so the portable agent defers to the codebase it is running in.
- Do not restate a rule that lives in a preloaded skill; if the rule is missing from the skill, add it there so every tool that reads the skill sees it.
- Keep the body under about eighty lines; an agent that needs more is carrying content that belongs in a skill.

An agent file carries no HTML comments and no per-file license line, for the same reasons a skill file carries none: the file is loaded as raw text, and licensing is stated in [LICENSE](../../LICENSE).

## Portability Across Repositories

An agent here must work in any repository it is started in.

- Discover the task runner and its recipes rather than naming one repository's `just` recipes as fact; name a recipe only as an example.
- Refer to documentation by the places repositories conventionally keep it, and defer to the repository's own instruction files for the authoritative locations.
- Do not name a private repository, a machine, or an absolute path.
- Claude Code loads the project's instruction files into a subagent automatically, so the body need not repeat them.

## Validation

Run the full local gate before committing an agent change.

- `just generate-agents` validates the role source and regenerates every agent from it.
- `just validate-agents` checks frontmatter, naming, model, color, effort and tool values, preloaded skills, the body opening, comments, and the index.
- `just lint-md agent_sources/prompts/<agent-name>.md` lints the body; fix what it reports in the source, because a fix applied to a generated file is reported as a hand edit.
- `just ci` runs every check that CI runs, starting with generation.
