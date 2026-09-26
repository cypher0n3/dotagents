# Shared Agent Templates

## Status and Scope

This specification describes how `dotagents` keeps one source per agent and turns it into what each agent tool reads.
Each agent is one file, `agent_sources/<name>.md`, and editing that file changes the agent for every tool.
A standard-library Python script generates Claude Code agents, Codex custom agents, Cursor agents, and Hermes personalities from those files whenever `just ci` or `just install` runs.
CAI reads the source files directly.
Nothing generated is committed.

The shared [`skills/`](../../skills/README.md) packages are not generated, and the [CAI integration](../../README.md#cai) still discovers `~/.agents/skills/` with no installation.

## Goals and Non-Goals

- Keep everything about an agent in one reviewable file: its description, model, skills, restrictions, per-tool settings, and instructions.
- Keep how each tool spells each field in the generator, never in the agent files.
- Produce every output from the same code on every platform, with no dependency beyond Python's standard library.
- Never drop a restriction a tool cannot enforce; state it where the tool will see it.

The generator does not change approval or sandbox policy, import native agent files, synchronize global instructions, or run agents.
It does not assume that any two tools use equivalent model names, skill loading, or tool restrictions.

## Agent Source Files

Each agent is one Markdown file, `agent_sources/<name>.md`, with YAML front matter and a Markdown body.
The body is the agent's instructions, written to be true for every tool, and is linted like every other Markdown file.
There is no templating: the body is ordinary Markdown, and the generator adds only the fixed text described under [Skills](#skills).
`agent_sources/README.md` is the hand-maintained agent index and is not an agent.

```yaml
---
schema: 1
name: reviewer
description: Performs adversarial review of a code change ...
model:
  tier: strong
  claude: opus
  cai:
    - ollama-local/qwen3.8:35b
    - ollama-local/qwen3.6:35b
  codex: gpt-6-astra
  cursor: grok4.7
effort: high
color: red
readonly: true
tools: [Read, Grep, Glob, Bash]
skills: [senior-developer, code-review-precision]
suggested_skills: []
exclude: []
cai:
  max_turns: 15
---
# Reviewer
```

The model identifiers above are illustrative and are not checked against any provider.

### Keys

- `schema` is required and is `1`, so a reader can refuse a format version it does not understand.
- `name` is required, lowercase kebab-case, at most 64 characters, and equal to the file name without `.md`.
- `description` is required and is one line of at most 1024 characters, rendered unchanged for every tool.
- `model` is optional and follows [Models](#models).
- `effort` is optional and is `low`, `medium`, `high`, `xhigh`, or `max`, following [Effort](#effort).
- `color` is required unless Claude Code is excluded, is one of `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, or `cyan`, and applies only to Claude Code.
- `readonly` is optional and states that the agent must not change files; a read-only agent must also list its `tools`, and they must not include `Write`, `Edit`, or `NotebookEdit`.
- `tools` is optional and lists Claude Code tool names: `Agent`, `Bash`, `Edit`, `Glob`, `Grep`, `NotebookEdit`, `Read`, `Skill`, `Task`, `TodoWrite`, `WebFetch`, `WebSearch`, and `Write`.
- `skills` lists the skills loaded before the agent starts, and `suggested_skills` those it loads when a task needs them; each must exist as `skills/<name>/SKILL.md`, and no skill may appear in both.
- `exclude` lists tools that should not get this agent, from `claude`, `codex`, `cursor`, `hermes`, and `cai`.
- A key named after a tool holds settings only that tool has, listed under [Per-Tool Settings](#per-tool-settings).

Any other key fails generation, as does a duplicate key, so a typo is never silently ignored.

### Front Matter Subset

The generator reads front matter with its own parser, so it needs no YAML library.
It accepts block mappings and block lists nested by indentation, inline lists such as `[a, b]`, plain, single-quoted, and double-quoted strings, integers, `true` and `false`, and full-line or trailing comments.
It rejects anchors, aliases, tags, block scalars, inline mappings, tabs in indentation, and ambiguous words such as `yes` or `null`, with an error naming the line.

## Generated Output

`just ci` and `just install` both run `.ci_scripts/generate_agents.py`, which writes the generated tree under `generated/`:

- Claude Code agents in `generated/claude/agents/<name>.md`.
- Codex custom agents in `generated/codex/agents/<name>.toml`.
- Cursor agents in `generated/cursor/agents/<name>.md`.
- Hermes personalities in `generated/hermes/personalities/<name>.yaml`.

`generated/` is ignored by Git, and nothing in it is committed or reviewed as a file.
Each run builds the whole tree beside the old one and swaps it into place, so a removed agent never leaves a stale output, and an invalid source leaves the previous tree untouched and fails with every problem listed.
Each generated file opens with a comment naming its source and saying not to edit it, because the next generation replaces it.

`just validate-agents` checks the generated Claude Code agents against the [agent authoring contract](../docs_standards/agent_authoring.md) and checks that `agent_sources/README.md` links every agent.
`just lint-md` skips `generated/`, and lints the sources instead.

## Target Semantics

Each tool receives the shared intent in its own native form where it has one, and as a comment or instruction where it does not.

### Models

`model` is either a tier, such as `model: strong`, or a block with an optional `tier` and one key per tool.

- A tool's own value wins.
- Otherwise the tier maps through the generator's tier table for that tool.
- Otherwise the tool uses its session's model: Claude Code and Cursor get `model: inherit`, and Codex gets no `model` key.

The tiers are `frontier`, `strong`, `standard`, and `fast`.
For Claude Code they map to `fable`, `opus`, `sonnet`, and `haiku`; Codex and Cursor have no mappings yet.
A tool's own value is one identifier, except for CAI, which takes a single identifier or an ordered preference list.
Hermes personalities cannot set a model, so a `model.hermes` value fails generation, and the Hermes explainer names the tier instead.

CAI identifiers follow CAI's model identifier format: a configured alias, a backend-qualified name such as `ollama-local/qwen3.8:35b`, or a provider-qualified name such as `ollama.qwen3.8:35b`.

### Effort

- Claude Code receives `effort` unchanged.
- Codex receives `model_reasoning_effort`, with `max` mapped to `xhigh`.
- Cursor has no agent setting for effort, so it receives the value as a commented key.
- Hermes receives it in the explainer paragraph.

### Skills

- Claude Code renders `skills` as its native preload list.
- Codex and Cursor cannot preload skills, so they receive `skills` as a commented key and a `## Skill Dependencies` section in the body telling the agent to load each skill before starting.
- Suggested skills become a body instruction to load them when relevant, in that same section, for Claude Code, Codex, and Cursor.
- Hermes names required and suggested skills in its explainer paragraph.

The `## Skill Dependencies` section is placed before the body's second H2, which keeps `## Role` first, or at the end when there is none; a body that already has that heading fails generation.

### Restrictions

- Claude Code enforces `tools`, which also carries `readonly`, since a read-only agent's tools exclude every file-writing tool; an allowlist that includes `Bash` leaves shell writes to host approvals.
- Codex renders `readonly` as `sandbox_mode = "read-only"`, which live overrides in the parent session can outrank, and receives `tools` as a commented key.
- Cursor renders `readonly` natively, which blocks edits and state-changing shell commands, and receives `tools` as a commented key.
- Hermes states both in its explainer paragraph, because a personality has no restriction field and applies to the whole session.

A commented key is followed by fixed wording saying the tool may not enforce it, and the body keeps every restriction as an instruction for every tool.

### Per-Tool Settings

- `claude` accepts `permissionMode`, `maxTurns`, `background`, `isolation`, and `memory`, with the values the agent authoring contract allows, rendered as native keys.
- `cursor` accepts `is_background`, rendered as a native key.
- `codex` and `hermes` accept no settings yet.
- `cai` accepts `selection` (`auto` or `lock`), `max_steps`, `max_turns`, `ingest_personas`, and `mcp_servers`; the generator validates them and CAI reads them.

A key outside a tool's list fails generation with the list of supported keys.

### Hermes Personalities

Hermes has no agent file format, so each agent becomes a personality under `agent.personalities.<name>`, holding `description` and a `system_prompt` that opens with an explainer paragraph and continues with the body.
The generated file is a header comment followed by two lines, `description:` and `system_prompt:`, each holding a JSON string, which is also valid YAML, so the installers read it without a YAML parser.

## CAI

CAI reads `agent_sources/` itself, and `dotagents` generates and installs nothing for it.
The CAI change is described in [CAI Native Agent Sources](../draft_specs/cai-native-agent-sources.md) and is tracked in CAI.
Until CAI ships it, CAI does not see these agents, and its built-in personas are unaffected.

## Installation

Both installers generate before any agent step, using the same Python script, so Windows, Linux, and macOS produce identical output.
Rendering never touches the home directory, and installing never renders anything itself.

- Claude Code, Codex, and Cursor agents are linked one file at a time into `~/.claude/agents`, `~/.codex/agents`, and `~/.cursor/agents`, whether or not the tool is installed, like the skill links.
- `--no-codex-agents` and `--no-cursor-agents`, or `-NoCodexAgents` and `-NoCursorAgents` in PowerShell, skip their step.
- Hermes personalities are set through `hermes config set` when the Hermes configuration exists and the `hermes` command is found; `--no-hermes-personalities` skips the step, and `--no-hermes` skips it and skill registration.
- Without Python, the installers skip only the agent steps and Hermes personalities, say why, and install skills, instructions, and settings as usual.
- An invalid agent source stops the install with the generator's error.
- A dry run still generates `generated/` in the clone, which installs nothing by itself, and changes nothing in the home directory.

Every destination stays a real directory the tool owns.
A link to the right file is reported as installed, a link elsewhere is skipped unless forced, a regular file in the way is skipped, and anything this repository does not provide is reported and never removed.
A link into this repository that points at an old location, such as the `agents/` directory of the previous layout, is ours and is relinked, and a whole-directory link into this repository is migrated to a real directory.

### Windows

The PowerShell installer matches the Unix one wherever Windows allows.
It uses a symbolic link for each file when this session can create one, which needs Developer Mode or an elevated shell; it tests this once and reports the link type.
Otherwise it falls back to a hard link on the same drive, then a copy, and never requires administrator rights.
Regenerating replaces files in the clone, which leaves a hard link or copy holding old content until the installer runs again.
The installer records the hash of every file it places in `install-state.json` under `%LOCALAPPDATA%\dotagents`, refreshes a file that still matches that record, and replaces a file the user changed only with `-Force`.
When symbolic links become available, a file it placed as a copy is replaced with a link.

### Hermes Ownership

Ownership of each personality is recorded per Hermes configuration in `install-state.json`, under `${XDG_STATE_HOME:-~/.local/state}/dotagents/` on Unix and `%LOCALAPPDATA%\dotagents\` on Windows, as a digest of the `description` and `system_prompt` the installer set.
The record is JSON because both installers must read and write it without a YAML parser.

- An absent personality is added, and one already equal to the generated value is left alone.
- A personality whose value still matches the recorded digest was set by the installer and is updated without `--force`.
- Any other personality of the same name, including one the user edited after installation, is skipped unless `--force` is passed.
- A personality with keys other than `description` and `system_prompt` is never treated as the installer's.
- Before its first change to `config.yaml` in a run, the installer takes one timestamped backup under the existing [backup contract](../../README.md#settings-backups).
- Each write is read back through the CLI, and a value that did not take effect fails the run with the backup kept.
- A recorded personality whose agent no longer exists is reported and left in place, and the installer never selects a personality.

## Adding a Target

A new tool is added in one reviewed change, with no change to any agent file:

1. Evidence of the tool's native agent or persona format, discovery locations, symlink handling, and each supported field, with the version that establishes it.
2. A renderer, an output path, a tier mapping, and a per-tool settings list in `.ci_scripts/generate_agents.py`, with tests in `.ci_scripts/test_generate_agents.py`.
3. Installer steps in both installers that follow [Installation](#installation), with tests.
4. Updates to the README and this specification.

A tool with no native agent or persona format is not a target, and agents are never written into global instruction files; Hermes is the deliberate exception.
Gemini, Grok, and GitHub Copilot in VS Code already receive shared skills or instructions and are candidates for later targets.

## Target Evidence

Each target's contract rests on these sources, which fix the design baseline rather than promise that later versions stay the same.

- Claude Code: the [subagent documentation](https://code.claude.com/docs/en/sub-agents) and the repository's [agent authoring contract](../docs_standards/agent_authoring.md), checked with Claude Code 2.1.282.
- Codex: the [subagent documentation](https://developers.openai.com/codex/subagents) and [configuration reference](https://developers.openai.com/codex/config-reference), checked against `codex-cli 0.155.1`, which loads a symlinked agent file.
  Whether web search stays available to a read-only custom agent is not yet verified.
- Cursor: the [subagent documentation](https://cursor.com/docs/subagents), as retrieved on 2026-09-25.
- Hermes: Hermes Agent v0.21.0 and its [personality](https://hermes-agent.nousresearch.com/docs/user-guide/features/personality/) and [delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation) documentation.
- CAI: the `usability_fixes` branch of `https://gitlab.com/cypher_zero/cai` at `b1db6c59bda7c77620380062fb67172bd0f1f190`, in `docs/tech_specs/personas.md`, `docs/tech_specs/inference/model_selection.md`, and `internal/personas/`.
