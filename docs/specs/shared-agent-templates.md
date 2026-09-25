# Shared Agent Templates

## Status and Scope

This specification describes the implemented agent generator.
Shared agent roles are authored once as YAML role data and Markdown bodies under [`agent_sources/`](../../agent_sources/README.md).
A generator renders them into target-native Claude Code agents, Codex custom agents, Cursor agents, Hermes personalities, and CAI personas.
Generation belongs to `dotagents`; each consuming application continues to load its own native format.
CAI's draft 470 runtime compatibility work is not a prerequisite.

Claude Code is a generation target like the others.
The files under [`agents/`](../../agents/README.md) are generated output, byte-identical to the hand-authored agents they replaced, and are installed exactly as before.
The shared [`skills/`](../../skills/README.md) packages are not generated.
The [CAI integration](../../README.md#cai) still needs no installation for shared skills at `~/.agents/skills/`.

## Goals and Non-Goals

The generator separates shared role intent from target-specific representation.

- Keep role instructions, descriptions, and skill dependencies in one reviewable source rather than maintaining independent prompt copies for each target.
- Render each target's native file format, Markdown with YAML frontmatter for most targets and TOML for Codex, with explicit target-specific model and capability choices.
- Make generation deterministic, offline, reviewable, and independent of live home-directory configuration.
- Detect unsupported semantics before publishing files rather than silently dropping required behavior.
- Keep generation separate from installation into application-owned directories.

The generator does not implement CAI runtime adapters, import foreign configuration, change approval or sandbox policy, convert executable plans, synchronize global instructions, or execute generated agents.
It does not assume that any two targets use equivalent model aliases, skill activation, or tool restrictions.
There is no importer that reads a native agent file and writes a role source.

## Current Target Evidence

Each target profile records, under `application`, the application version or documentation revision that establishes its contract, with evidence links and notes.
These references establish the design baseline, not a promise that future application versions remain identical.

- The [Claude Code subagent documentation](https://code.claude.com/docs/en/sub-agents) and the repository's [agent authoring contract](../docs_standards/agent_authoring.md) define the Claude Code target, checked with Claude Code 2.1.282.
  The agents use `name`, `description`, `model` as a Claude alias, `color`, a `tools` allowlist, and a `skills` preload list.
  Claude Code enforces `tools` and preloads `skills`, so it is the only target that carries both guarantees natively.
- The [Codex subagent documentation](https://developers.openai.com/codex/subagents) and [configuration reference](https://developers.openai.com/codex/config-reference) define custom agents, checked against `codex-cli 0.155.1`.
  Each custom agent is one standalone TOML file discovered from user `~/.codex/agents/` and project `.codex/agents/`.
  `name`, `description`, and `developer_instructions` are required; other `config.toml` keys may follow, including `model`, `model_reasoning_effort`, and `sandbox_mode`.
  `sandbox_mode = "read-only"` is host-enforced, except that live overrides made in the parent session, such as `/permissions` changes or `--yolo`, are reapplied to the child and outrank the file.
  Codex has no per-agent tool allowlist, and `skills.config` enables or disables skills by path rather than preloading them.
  A custom agent whose `name` matches a built-in agent (`default`, `worker`, or `explorer`) replaces it; none of the role names collide.
  `codex-cli 0.155.1` loads a symlinked agent file: in a throwaway `CODEX_HOME`, `codex doctor` reported the same startup warning for a malformed agent stored as a symlink as for one stored as a regular file, and neither warning once both were valid.
  Whether web search stays available to a read-only custom agent, which matters for `researcher`, is not yet verified.
- The [Cursor subagent documentation](https://cursor.com/docs/subagents) defines project `.cursor/agents/` and user `~/.cursor/agents/` discovery, Markdown with YAML frontmatter, and fields including `name`, `description`, `model`, `readonly`, and `is_background`.
  Cursor also documents foreign-directory compatibility; that does not establish equivalent treatment of every Claude frontmatter field.
  The profile records the documentation as retrieved on 2026-09-25, since no application version was pinned.
- Hermes Agent, checked against `Hermes Agent v0.21.0` and its [personality](https://hermes-agent.nousresearch.com/docs/user-guide/features/personality/) and [delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation) documentation, has no file-based agent or persona format.
  `delegate_task` spawns subagents from a per-call `goal`, `context`, and `role`, with no named predefined agents.
  The closest native concept is a personality: an entry under `agent.personalities.<name>` in `config.yaml` holding `system_prompt`, `description`, `tone`, and `style`, selected per session with `/personality` and applied as a system-prompt overlay for the whole session.
  A personality has no model, tool, sandbox, or skill field.
- CAI's native persona contract lives in its `docs/tech_specs/personas.md` and `internal/personas/persona.go`.
  The schema includes `name`, `description`, `model`, `preferred_models`, `required_skills`, `suggested_skills`, and runtime limits, but not a `tools` allowlist or `readonly` field.
  CAI discovers personas from project `.cai/personas/`, its configured global persona directory, and embedded definitions.
  Its persona reader must accept a symlinked persona file for the installer's links to load; that change is tracked in CAI.
- A parser accepting a file is not evidence that it enforced every supplied field.
  The generator therefore enforces its own per-target field allowlist and semantic validation.

## Authoring Model

Roles are structured YAML data, plain Markdown bodies, and thin Jinja target templates.
YAML holds role identity, dependency declarations, and target settings; Markdown holds the shared role instructions.
Bodies are plain Markdown and are never rendered as templates, so a body can contain Jinja delimiters as ordinary text.
Shared prompt fragments and include syntax are not part of schema 1; a later schema version can add them explicitly.

## Source Layout

Sources, generated artifacts, and generator tooling live in distinct directories:

```text
agent_sources/
  roles/<name>.yaml
  prompts/<name>.md
  targets/{claude,codex,cursor,hermes,cai}.yaml
  templates/{claude.md,codex.toml,cursor.md,hermes.yaml,cai.md}.j2
agents/<name>.md
generated/
  codex/agents/<name>.toml
  cursor/agents/<name>.md
  hermes/personalities/<name>.yaml
  cai/personas/<name>.md
  manifest.yaml
tools/agentgen/
  pyproject.toml
  uv.lock
  src/agentgen/
  tests/
```

Generated Claude Code agents are written to `agents/<name>.md`, the path the installer, `validate_agents.py`, and the [agent index](../../agents/README.md) already use.
The manifest, not the file, records which files are generated; a file it does not list is left alone, and `agents/README.md` is never an output.
The agent index stays hand-maintained, and `validate_agents.py` continues to check every file in `agents/`.

## Role Data Schema

Each role is one YAML file, `agent_sources/roles/<name>.yaml`; `reviewer` looks like this:

```yaml
schema: 1
name: reviewer
description: >-
  Performs adversarial review of a code change in any language against its
  specifications, the repository's conventions, and its own lint and test
  gates, without editing anything. Use proactively after a change is written
  and before it is committed, and whenever a review of a branch, diff, or pull
  request is requested.
body: prompts/reviewer.md
targets: [claude, codex, cursor, hermes, cai]
model:
  alias: strong
skills:
  required:
    - senior-developer
    - code-review-precision
restrictions:
  readonly: true
  tools: [Read, Grep, Glob, Bash]
presentation:
  claude:
    color: red
```

The keys are defined as follows:

- `schema` is required and is the integer schema version, currently `1`; the generator rejects a version it does not know.
- `name` is required, lowercase kebab-case, at most 64 characters, and must equal the file's base name; `readme` is reserved.
- `description` is required, a single line of at most 1024 characters, and is rendered unchanged to every target.
- `body` is required and is a path, relative to `agent_sources/`, to a Markdown file under `prompts/`; it must not pass through a symlink, must open with an H1, and must end with exactly one newline.
- `targets` is required and is a non-empty list of target profile names.
- `model` is optional and follows [Models](#models).
- `skills` is optional, with `required` and `suggested` lists; every name must exist as `skills/<name>/SKILL.md`, and a skill cannot appear in both lists.
- `restrictions` is optional; when absent, the role is unrestricted, as `coder` is.
  - `readonly` is a boolean.
    When `true`, `tools` must not list `Write`, `Edit`, or `NotebookEdit`, and a target that carries read-only only through its tool allowlist requires `tools` to be present.
  - `tools` is a list of Claude Code tool names from the generator's known list: `Agent`, `Bash`, `Edit`, `Glob`, `Grep`, `NotebookEdit`, `Read`, `Skill`, `Task`, `TodoWrite`, `WebFetch`, `WebSearch`, and `Write`.
- `presentation` is optional and maps a target name to display hints; `presentation.claude.color` is required for a role that targets `claude` and must be one of the eight colors the agent standard allows.
- `overrides` is optional and maps a target name to settings from that target's override allowlist; an override can never change a shared field.

Any other key, at any level, fails validation, and so does a duplicate key.
Source text must be UTF-8 with LF line endings, and printable apart from newlines in bodies.

## Target Profiles

Each target profile, `agent_sources/targets/<name>.yaml`, declares its format, template, output directory, model keys, and how it renders each piece of shared intent.
The generator emits no uncommented key the profile does not allow.

- `application` records the checked version or revision, evidence links, and notes.
- `format` is `markdown`, `toml`, or `hermes`, and fixes the output extension.
- `output` is a relative path under `agents` or `generated/`.
- `noun` is `agent`, `persona`, or `personality`, and is used in the fixed comment wording.
- `model` gives the native `key`, an optional `list_key` for a target that accepts a preference list, and an optional `inherit` value rendered when no model resolves.
- `alias_list` maps an alias to an ordered list of this target's model identifiers.
- `readonly`, `tools`, `required_skills`, and `suggested_skills` each give a `render` mode and, where needed, a native `key`.
- `presentation` lists the display hints the target renders, and `overrides` lists the settings a role may set with their types.

The render modes are these:

- `native` emits the native key.
- `commented` emits the key as a comment with a fixed explanation; for required skills it also adds a body instruction.
- `instruction` adds a body instruction only, for suggested skills.
- `tools` means read-only is carried by the tool allowlist and nothing else is emitted; it requires `tools` to render natively.
- `explainer` states the intent in the Hermes explainer paragraph, and only a `hermes` profile uses it.

The shipped profiles render as follows:

- `claude` renders `name`, `description`, `model`, `color`, `tools` as a comma-separated string, and `skills` natively.
  Read-only is carried by `tools`, suggested skills become a body instruction, and it accepts no overrides.
- `codex` renders `name`, `description`, `model`, `sandbox_mode = "read-only"` for a read-only role, and `developer_instructions` natively.
  A writable role omits `sandbox_mode`, so the child inherits the parent session's sandbox.
  It emits `tools` and `skills` as comments, instructs required and suggested skills in the body, and accepts only `model_reasoning_effort` as an override.
- `cursor` renders `name`, `description`, `model` with `inherit` as its fallback, and `readonly` natively.
  It emits `tools` and `skills` as comments, instructs skills in the body, and accepts no overrides.
- `hermes` renders `description` and `system_prompt` only, and states model, read-only, tools, and skills in an explainer paragraph at the start of `system_prompt`.
- `cai` renders `name`, `description`, `model` or `preferred_models`, `required_skills`, and `suggested_skills` natively, and emits `readonly` and `tools` as comments.
  A role with no resolved model omits `model`; runtime-limit overrides are not enabled until their names and types are recorded in the profile.

A profile changes only in a reviewed change that records the application version establishing the new support, and changing a render mode from `commented` to `native` needs no change to role sources.

## Target Override Contract

Target-specific settings use explicit, limited overrides rather than a generic layered configuration merge.
Shared role data owns identity, purpose, dependency intent, and restrictions; overrides cannot replace or weaken them.
A profile's override allowlist cannot name a shared field or a key the profile already renders.
Each override value is validated against its declared type: an enum, a string, a boolean, or an integer with an optional minimum.
Overrides render after the shared fields, sorted by key.
A different dependency guarantee or weaker restriction requires a reviewed change to the shared role or a distinct role, not an override.

## Rendering Contract

Generation takes the role sources, target profiles, and templates in a checkout and writes only under `agents/` and `generated/`.
It does not infer targets from installed applications or read the user's home directory.

1. Load every profile, then every role, collecting all problems before failing.
2. For each role and each target it lists, build an ordered list of native entries and fixed comment blocks.
3. Serialize each entry with the generator's own emitters rather than a whole-document serializer.
   A YAML scalar is emitted plain only when a strict parse proves it reads back identically, and double-quoted otherwise.
   Codex TOML uses basic strings and one multi-line basic string for `developer_instructions`.
   Hermes values are single-line JSON strings, which are valid YAML double-quoted scalars.
4. Pass the serialized text to the target's template in a sandboxed Jinja environment with `StrictUndefined`, a loader confined to `agent_sources/templates/`, and no globals, filters, or tests.
   Templates are trusted repository code and only place the pieces; role text is passed as data and is never compiled.
5. Parse every rendered file again and require it to read back as exactly the intended fields and body.
6. Build the manifest, then publish or check.

The comment and instruction wording are fixed generator strings, so role data cannot inject frontmatter through them.
No generated file carries a hidden provenance comment; provenance belongs in the manifest.

## Target Semantics

A target adapter is a semantic contract, not merely a different header template.

### Identity and Prompt Content

Every target receives the role name, the description unchanged, and the full body.
A target may gain instructions that restate a dependency or restriction it cannot enforce, but never loses a prohibition from the body.

### Models

A role's `model` block combines direct per-target values with an alias that each target profile maps to its own models.

```yaml
model:
  alias: strong
  cursor: grok[high]
```

Every key is optional, and any key other than `alias` must name a target the role lists.
Each profile holds its own `alias_list`, because model identifiers are target-native, and identifiers are opaque strings the generator does not check against a provider.
The Claude profile maps `strong` to `opus`, `standard` to `sonnet`, and `fast` to `haiku`; the other shipped profiles define no aliases yet.

For each target the model resolves in this order:

1. A direct value for that target wins.
2. Otherwise the role's alias is looked up in that target's `alias_list`.
3. Otherwise the target's inheritance form is rendered: `model: inherit` for Claude Code and Cursor, no model key for Codex and CAI, and an explainer line for Hermes, whose personalities always use the session's model.

A resolved list renders under the profile's `list_key` where one is declared; a target that takes one model receives the list's first entry.
A direct list is accepted only for a target with a `list_key`.
An alias that no profile defines fails validation, while an alias missing from one target's list falls back to inheritance there and is recorded in the manifest.

### Skill Dependencies

Role data declares required skills, which the role needs before it starts, and suggested skills, which it may load when relevant.
A role is never withheld from a target because the target cannot preload its skills.

- Claude Code renders required skills as its native `skills` preload list.
- CAI renders required and suggested skills as `required_skills` and `suggested_skills`.
- Codex and Cursor emit required skills as a commented `skills` key followed by a fixed explanation, and insert a `## Skill Dependencies` section into the body.
- Hermes names required and suggested skills in the explainer paragraph.
- A suggested skill with no native field becomes a body instruction to load it when relevant.

The inserted section goes immediately before the body's second H2, which keeps `## Role` first, or at the end when there is none, and a body that already has a `## Skill Dependencies` heading fails generation.
The load-on-match choices in `docs-writer` and `test-runner` stay in their bodies as prose rather than becoming `suggested` skills.

### Permissions and Capabilities

Restrictions are declared once as intent: `readonly` for a role that must not change files, and a tool allowlist where the role needs one.
Restrictions are best effort on every target, and a role is never withheld from a target because the target cannot enforce one.

- Claude Code enforces the `tools` allowlist, which carries read-only by excluding every file-writing tool; an allowlist that includes `Bash` leaves shell writes to host approvals.
- Codex enforces `sandbox_mode = "read-only"`, subject to live parent-session overrides, but has no per-tool allowlist.
- Cursor enforces `readonly`, which blocks file edits and state-changing shell commands, but has no per-tool allowlist.
- CAI enforces neither, so both are emitted as comments.
- A Hermes personality has no restriction field and applies to the whole session once selected, so its restrictions exist only in the explainer paragraph and the body.

A commented key is comment text in the target's own syntax, followed by a fixed explanation that the restriction may not be enforced.
The body keeps every restriction as a behavioral instruction on every target.
The manifest records each restriction rendered as a comment or explainer, per role and target.

### Presentation

Presentation hints are optional target-specific data, currently only `color` for Claude Code.
A hint a target does not list is dropped and recorded in the manifest.
The same omission rule never applies to model choice, dependencies, or restrictions.

## Generated Artifact Policy

Generated files and `generated/manifest.yaml` are committed alongside their sources, so reviewers can read the exact native prompts.
Sources are the only place to edit; a source change that affects output includes the regenerated files in the same change.

The manifest records the generator and schema versions, a digest of every template, profile, role, and body, and for every output its path, digest, the rule that selected its model, and notes on each comment, instruction, explainer, or dropped hint.
It has no timestamps or machine-specific paths, so identical inputs produce identical bytes.

`just generate-agents` is the first step of `just ci`, so the later checks see regenerated files.
Locally it publishes; when the `CI` environment variable is set to anything other than empty, `0`, or `false`, it runs in check-only mode.

- A managed file whose bytes match neither the digest recorded at the last generation nor the new rendering was edited by hand; generation writes nothing, names it, and fails.
- A file the manifest does not list that sits at an output path is not the generator's to replace, and fails the same way.
- A file that already matches the new rendering is current, so a run interrupted before the manifest moved into place recovers on the next run.
- `just generate-agents-accept-source` overwrites hand-edited or unlisted files at output paths and reports each one, which is how a merge conflict in generated files is resolved.
- An unchanged rebuild writes nothing and leaves modification times alone.
- Publication stages every changed file beside its destination, moves the files into place, removes obsolete managed files whose content is unchanged, and moves the manifest last.
- Outputs must be regular files under `agents/` or `generated/`, reached without a symlink, with no two paths equal after case folding.

Check-only mode fails on missing, stale, hand-edited, or obsolete outputs and on manifest drift, and never writes.

Generated Markdown must pass the repository's Markdown lint as rendered.
If `just lint-md` rewrites a generated file locally, the next `just ci` reports it as a hand edit, and the fix belongs in the source or the generator.

## Installation Boundary

Rendering and installation are separate operations, and installation consumes the committed files without Jinja, PyYAML, or `uv`.
Installing from uncommitted source edits requires running `just ci` first.

Both installers add these steps to `just install`, each with its own switch:

- Claude Code agents keep their per-file links into `~/.claude/agents`.
- Codex agents are linked into `~/.codex/agents/`; `--no-codex-agents` or `-NoCodexAgents` skips the step.
- Cursor agents are linked into `~/.cursor/agents/`; `--no-cursor-agents` or `-NoCursorAgents` skips the step.
- CAI personas are linked into `$XDG_CONFIG_HOME/cai/personas/`, falling back to `~/.config/cai/personas/`, only when that CAI configuration root exists; `--no-cai-personas` skips the step.
- Hermes personalities are set through `hermes config set` when the Hermes configuration exists and the `hermes` command is on `PATH`; `--no-hermes-personalities` or `-NoHermesPersonalities` skips the step, and `--no-hermes` or `-NoHermes` skips both Hermes steps.
- `--dry-run` reports every step and writes nothing.

The Codex and Cursor steps run whether or not the tool is installed, as the skill links already do, because the skill step creates `~/.codex` and `~/.cursor` on every run anyway.
The CAI step is gated because nothing else creates CAI's configuration root.
The PowerShell installer reports the CAI step as unsupported, since CAI's layout is Linux/XDG, and `-NoCaiPersonas` only silences that report.

Every destination stays a real directory the application owns, with one entry per generated file.
An existing whole-directory link to a repository output directory is migrated to a real directory, as for skills and Claude agents.
Links follow the existing rules: a link to the same file is reported as installed, a link elsewhere is skipped unless `--force` is passed, a regular file in the way is skipped, and a broken link or a file this repository does not provide is reported and never removed.

On Unix, per-file symlinks pick up regenerations without reinstalling.
On Windows, the PowerShell installer uses hard links or copies, and regenerating or checking out a file replaces it in the clone, leaving the installed file with the old content.
The PowerShell installer records the hash of every file it places in `install-state.json` under `%LOCALAPPDATA%\dotagents`, and refreshes an installed file that still matches that record, while a file the user changed stays unless `-Force` is passed.
Re-run the installer after regenerating on Windows.

CAI integration targets the XDG root, not an inferred sibling of `CAI_CONFIG`.
The installer does not read CAI's configuration, so it does not detect a CAI setup that configures a different persona directory.
Personas are linked rather than copied, and until CAI accepts symlinked persona files, CAI reports each linked persona as not a regular file.

Hermes personalities are installed by value, because a personality lives inside `config.yaml`.
The installer reads each generated personality with a line-oriented JSON reader, so neither installer needs a YAML parser.
Ownership is recorded per Hermes configuration in `install-state.json`, under `${XDG_STATE_HOME:-~/.local/state}/dotagents/` on Unix and `%LOCALAPPDATA%\dotagents\` on Windows, as a digest of the `description` and `system_prompt` the installer set.
The record is JSON rather than YAML because both installers must read and write it without a YAML parser.

- An absent personality is added, and one already equal to the rendered value is a no-op.
- A personality whose current value matches the recorded digest is owned and is updated without `--force`.
- Any other personality of the same name, such as the user's own or one the user edited after installation, is skipped unless `--force` is passed.
- A personality with keys other than `description` and `system_prompt` is never treated as owned.
- Before its first change to `config.yaml` in a run, the installer takes one timestamped backup under the existing [backup contract](../../README.md#settings-backups), shared with skill registration.
- Each write is read back through the CLI, and a value that did not take effect fails the run with the backup retained.
- A recorded personality whose role no longer exists is reported and left in place.
- The installer never selects a personality or touches `display.personality`.

## Adding a Target

A later target is added in its own reviewed change, and needs no change to role sources beyond listing the target name in each role's `targets`.

A change that adds a target includes all of the following:

1. Evidence: the application's native agent or persona concept, file format, discovery locations, symlink handling, and each supported field, recorded in the profile's `application` block and under [Current Target Evidence](#current-target-evidence).
2. A target profile, `agent_sources/targets/<target>.yaml`, and a template, `agent_sources/templates/<target>.<extension>.j2`.
3. Generator tests for the target's rendering in `tools/agentgen/tests/`.
4. A recorded manual smoke check that the application discovers and loads the rendered files, because consumer parsers are not available offline in CI.
5. Installer steps in both installers that follow [Installation Boundary](#installation-boundary), with tests.
6. Updates to the README, this specification, and any affected standards.

A harness with no native agent or persona format is not a target, and roles are never written into global instruction files.
Hermes is the deliberate exception, rendered as personalities.
Gemini, Grok, and GitHub Copilot in VS Code already receive shared skills or instructions from the installer and are candidates for later targets.

## Generator Tooling

The generator is a Python project in `tools/agentgen/`, managed with `uv`.
Its `pyproject.toml` declares Jinja2 and PyYAML, and the committed `uv.lock` pins every dependency with hashes.
TOML output uses the generator's own emitter, so no TOML library is needed.

- `just generate-agents` runs `uv run --locked --project tools/agentgen agentgen generate`, so a lock file that no longer matches `pyproject.toml` fails instead of being rewritten.
- `just test-agentgen` runs the generator's unit tests in the same locked environment, and is part of `just ci`.
- `just setup` prepares the environment, or reports a missing `uv` with install guidance.
- The hosted CI jobs install a pinned `uv` and run both recipes; `generate-agents` checks rather than writes there.
- Dependency updates run `uv lock` and commit the new lock file.
- [`.ci_scripts/`](../../.ci_scripts/README.md) stays standard-library only.

## Known Limits

These are open, recorded rather than hidden:

- CAI must accept symlinked persona files before linked personas load, and its runtime-limit overrides and exact inheritance form need recording against a CAI revision.
- The installer does not detect a CAI configuration that points personas elsewhere.
- Whether Codex web search works for a read-only custom agent is unverified.
- No profile other than Claude defines model aliases, so every other target inherits its session model until its `alias_list` is filled in.
