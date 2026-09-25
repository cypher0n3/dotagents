# Shared Agent Templates

## Status and Scope

This is a proposal for review, not an implemented generator, supported install mode, or change to the current [agent authoring contract](../docs_standards/agent_authoring.md).
The goal is to author shared agent roles once using Jinja templates and structured data, then generate target-native Claude Code agents, Cursor agents, and CAI personas.
Generation belongs to `dotagents`; consuming applications continue to load their own native formats.
CAI's draft 470 runtime compatibility work remains deferred and is not a prerequisite for this proposal.

Claude Code is a generation target from the first implementation, not a later migration.
The hand-authored Claude Code agents under [`agents/`](../../agents/README.md) become generated output once their roles are ported and pass the parity check in [Migration and Validation](#migration-and-validation); until then, they and their installer behavior remain unchanged.
The shared [`skills/`](../../skills/README.md) packages are not generated and remain unchanged.
The current [CAI integration](../../README.md#cai) continues to require no installation for shared skills at `~/.agents/skills/`.

## Goals and Non-Goals

The proposed generator separates shared role intent from target-specific representation.

- Keep role instructions, descriptions, and skill dependencies in one reviewable source rather than maintaining independent Claude Code, Cursor, and CAI prompt copies.
- Render native Markdown files with validated YAML frontmatter and explicit target-specific model and capability choices.
- Make generation deterministic, offline, reviewable, and independent of live home-directory configuration.
- Detect unsupported semantics before publishing files rather than silently dropping required behavior.
- Keep generation separate from optional installation into application-owned directories.

The initial proposal does not implement CAI runtime adapters, import foreign configuration, change approval or sandbox policy, convert executable plans, synchronize global instructions, or execute generated agents.
It does not assume that Claude Code, Cursor, and CAI use equivalent model aliases, skill activation, or tool restrictions.
The existing Claude Code agents are ported into role sources by hand, one reviewed role at a time; there is no automatic importer that reads `agents/*.md` and writes sources.

## Current Target Evidence

Target contracts need a recorded application version or source revision when implementation begins.
These references establish the design baseline, not a promise that future application versions remain identical.

- The [Claude Code subagent documentation](https://docs.claude.com/en/docs/claude-code/sub-agents) and the repository's [agent authoring contract](../docs_standards/agent_authoring.md) define the Claude Code target.
  The current agents use `name`, `description`, `model` as a Claude alias (`opus` or `sonnet`), `color`, a `tools` allowlist, and a `skills` preload list.
  Claude Code enforces `tools` and preloads `skills`, so it is the only current target that can carry both guarantees natively.
- The [Cursor subagent documentation](https://cursor.com/docs/subagents) defines project `.cursor/agents/` and user `~/.cursor/agents/` discovery, Markdown with YAML frontmatter, and fields including `name`, `description`, `model`, `readonly`, and `is_background`.
  Cursor also documents foreign-directory compatibility; that does not establish equivalent treatment of every Claude frontmatter field.
- CAI's native persona contract lives in its `docs/tech_specs/personas.md` and `internal/personas/persona.go`.
  The current schema includes `name`, `description`, `model`, `preferred_models`, `required_skills`, `suggested_skills`, and runtime limits, but not a native persona `tools` allowlist or `readonly` field.
- CAI discovers native personas from project `.cai/personas/`, its configured global persona directory, and embedded definitions.
  Its native persona reader currently requires regular files and rejects leaf symlinks (`readRegularPersonaFile` in `internal/personas/persona.go`, covered by `TestParseRejectsInvalidUTF8AndNonRegularFiles`).
  Installing personas as links depends on changing that, as described in [Installation Boundary](#installation-boundary).
- A parser accepting a file is not evidence that it enforced every supplied field.
  The generator therefore needs its own target-field allowlist and semantic validation in addition to consumer-parser checks.

## Selected Authoring Model

The selected model is structured YAML role data, mostly Markdown role bodies, and thin Jinja target templates.
YAML holds role identity, dependency declarations, and target settings; Markdown holds shared role instructions.
Jinja assembles target-native files with small target-specific fragments where native behavior differs.
Ordinary prompt edits should remain readable without following a template inheritance hierarchy.
Per-role target conditionals and pervasive Jinja block inheritance are not the primary authoring model.
The schema is defined in [Role Data Schema](#role-data-schema); all nine current roles are ported in the first implementation, and target overrides follow the selected limited-override contract below.

## Proposed Source Layout

Source data, shared Markdown prompts, target adapters, generated artifacts, and generator tooling live in visibly distinct directories.
The rest of this draft uses these paths:

```text
agent_sources/
  roles/
    coder.yaml
    reviewer.yaml
  prompts/
    coder.md
    reviewer.md
    shared/
      repository-context.md
  targets/
    claude.yaml
    cursor.yaml
    cai.yaml
  templates/
    claude.md.j2
    cursor.md.j2
    cai.md.j2
agents/
  coder.md
  reviewer.md
generated/
  cursor/agents/
  cai/personas/
  manifest.yaml
tools/agentgen/
  pyproject.toml
  uv.lock
  agentgen/
```

Generated Claude Code agents are written directly to `agents/<name>.md`, the path the installer, `validate_agents.py`, and the [agent index](../../agents/README.md) already use, so none of them changes.
Because every current role is ported in the first implementation, there is no period in which ported and hand-authored roles share the directory; the manifest, not the file, records which files are generated, and any file it does not list is left alone.
The agent index stays hand-maintained, and `validate_agents.py` continues to check every file in `agents/` whether generated or not.
Once a role is generated, its `agents/<name>.md` is edited only through its source; a hand edit fails `just ci` rather than being overwritten, as described in [Generated Artifact Policy](#generated-artifact-policy).
Implementation must add that rule to the [agent authoring contract](../docs_standards/agent_authoring.md), which this draft does not change.

Role data supplies a stable lowercase kebab-case identity, routing description, Markdown body path, supported targets, and explicit skill and capability intent.
Target profiles supply native model selections and supported field mappings without embedding credentials, local absolute paths, or provider secrets.
Shared prompt fragments hold role behavior; target adapters supply native invocation instructions rather than scattering application-name conditionals throughout every role.
Skills remain separate packages; templates refer to them rather than copying their complete bodies into generated prompts by default.

## Role Data Schema

Each role is one YAML file, `agent_sources/roles/<name>.yaml`; `reviewer` looks like this:

```yaml
schema: 1
name: reviewer
description: >-
  Performs adversarial review of a code change in any language against its
  specifications, the repository's conventions, and its own lint and test
  gates, without editing anything. Use proactively after a change is written
  and before it is committed, and whenever a review of a branch, diff, or
  pull request is requested.
body: prompts/reviewer.md
targets: [claude, cursor, cai]
model:
  alias: strong
  claude: opus
skills:
  required: [senior-developer]
  suggested: []
restrictions:
  readonly: true
  tools: [Read, Grep, Glob, Bash]
presentation:
  claude:
    color: red
overrides:
  cai: {}
```

The keys are defined as follows:

- `schema` is required and is the integer schema version, currently `1`; the generator rejects a version it does not know.
- `name` is required, lowercase kebab-case, and must equal the file's base name; it becomes each target's `name` and output file name.
- `description` is required, is rendered unchanged to every target, and keeps the routing text Claude Code uses to choose the agent.
- `body` is required and is a path, relative to `agent_sources/`, to the role's Markdown prompt; it must stay inside `agent_sources/prompts/`.
- `targets` is required and is a non-empty list of target profile names; a role is generated only for the targets it lists.
- `model` is optional and follows [Models](#models); when absent, every target renders its native inheritance form.
- `skills` is optional, with `required` and `suggested` lists that follow [Skill Dependencies](#skill-dependencies); every name must exist under `skills/`, and a skill cannot appear in both lists.
- `restrictions` is optional; when absent, the role is unrestricted, as `coder` is today.
  - `readonly` is a boolean.
    When `true`, `tools` must not list a file-writing tool (`Write`, `Edit`, or `NotebookEdit`); `Bash` stays allowed, and per [Permissions and Capabilities](#permissions-and-capabilities) its presence means the role is described as technically read-only only on a target that also blocks state-changing shell commands, such as Cursor.
  - `tools` is a list of Claude Code tool names, because Claude Code is the only target with a tool allowlist; other targets receive it only as a commented key.
- `presentation` is optional and maps a target name to display hints, currently only `color` for `claude`; hints a target does not support are dropped and recorded under [Presentation](#presentation).
- `overrides` is optional and maps a target name to settings from that target's override allowlist; an override can never change `name`, `description`, `body`, `skills`, or `restrictions`.

Any other key, at any level, fails validation.
The schema is versioned so a later change can add keys under a new `schema` value without guessing at old files.

## Target Field Allowlists

Each target profile lists the frontmatter fields it renders natively, and the generator emits no other uncommented key.
Shared intent that a target cannot render natively becomes a commented key under the best-effort rules, or is dropped as presentation.

- `claude` renders `name`, `description`, `model`, `color`, `tools`, and `skills` natively.
  It has no commented keys; `readonly` is carried by the `tools` allowlist, and it accepts no `overrides`.
- `cursor` renders `name`, `description`, `model`, and `readonly` natively.
  It emits `tools` and `skills` as commented keys, drops `color`, and accepts no `overrides` in schema version 1.
- `cai` renders `name`, `description`, `model` or `preferred_models`, `required_skills`, and `suggested_skills` natively.
  It emits `readonly` and `tools` as commented keys and drops `color`.
  Its `overrides` accept only the persona runtime limits its native schema defines for the recorded CAI version, each validated against that schema's type.

A target profile changes these lists only in a reviewed change that records the application version establishing the new support.

## Target Override Contract

Target-specific settings use explicit, limited overrides rather than a generic layered configuration merge.
Shared role data owns identity, purpose, dependency intent, and restrictions; target overrides cannot replace or weaken those shared requirements.
Target profiles supply defaults for an allowlisted set of native settings, such as model selection and supported runtime limits.
Explicit role-target settings take precedence over those defaults only for fields permitted by the target schema.
An omitted role-target setting retains the target-profile default; a required setting left unresolved fails generation.
Unknown fields, prohibited overrides, and settings incompatible with the shared role contract fail generation before publication.
There is no generic recursive merge of nested objects or lists; any structured field needs an explicit schema-defined resolution rule.
The per-target field allowlists are defined in [Target Field Allowlists](#target-field-allowlists) rather than inferred from parser tolerance.
Target adapters translate shared requirements into native representations without using overrides to change their meaning.
A different dependency guarantee or weaker restriction requires an explicitly reviewed change to the shared role contract or a distinct role, not a target-setting override.

## Rendering Contract

Generation takes explicit role sources, selected target profiles, a pinned template environment, and an output directory.
It does not infer targets from installed applications or mutate files under the user's home directory.

1. Validate source schemas, unique role names, declared target support, template paths, and referenced shared skills.
2. Normalize each role into a target-independent record and resolve explicit target overrides.
   Missing or conflicting required values stop generation; there is no implicit provider choice or permission widening.
3. Use Jinja with `StrictUndefined`, a repository-contained template loader, and an explicit minimal filter set.
   Do not expose environment variables, credentials, filesystem helpers, subprocesses, or network access to templates.
4. Serialize frontmatter through a YAML serializer with deterministic ordering and quoting; do not concatenate unescaped YAML scalars in templates.
   Render the body once, with UTF-8, LF endings, and a final newline.
   Role text containing Jinja delimiters is data, not a second template pass.
5. Validate rendered frontmatter, prompt structure, skill references, target semantics, output paths, and collisions before publishing the requested output set.
6. Produce a manifest recording generator and schema versions, target profiles, relative source identities, input digests, output paths, and output digests.
   Exclude wall-clock timestamps, credentials, and machine-specific paths so identical inputs produce identical bytes.

Templates are trusted repository code and require review; restricting the template context is not a claim that arbitrary third-party Jinja is safe.
Reject template and output path escapes, symlink escapes, duplicate outputs, and case-folded filename collisions.
In the shared `agents/` directory, publication writes or removes only files the manifest lists, and never touches `README.md` or any agent file the manifest does not list.
A role's first render replaces its hand-authored file only in the change that records its passing parity check and adds it to the manifest.
No generated prompt contains a hidden attribution comment or machine-local provenance block; provenance belongs in the manifest.

A check-only mode renders in isolation and reports missing, changed, and obsolete managed outputs without editing them.
Any generation or validation error leaves the previously published output set unchanged.
The implementation should stage a complete output set and retain the previous generation until publication succeeds, rather than exposing partially rendered targets.
Cleanup is restricted to the generator's own temporary artifacts.

## Target Semantics

A target adapter is a semantic contract, not merely a different header template.

### Identity and Prompt Content

Preserve the role name, description intent, task boundaries, and reporting requirements.
Target-specific prompt fragments may name native tools or skill-loading operations, but may not silently remove a prohibition or broaden the role's authority.
A role unavailable on a target is reported as unsupported rather than emitted with a different meaning.

### Models

A role's `model` block combines direct per-target values with a model alias, a named tier such as `strong` that each target profile maps to its own models.

```yaml
# Role data
model:
  alias: strong
  claude: opus
  cursor: grok[high]
```

```yaml
# Target profile, for example targets/cai.yaml
alias_list:
  strong:
    - qwen3.8:35B
    - qwen3.6:27B
  strong-uncensored:
    - qwen3.8-abliterated:35B
```

Every key in the role's `model` block is optional, and any key other than `alias` must name a target listed in the role's supported targets.
Each target profile holds its own `alias_list`, because model identifiers are target-native; there is no shared alias file.
The example above is a CAI profile; the Claude profile would map `strong` to `[opus]`, and the Cursor profile to `[grok[high]]`.
Each list therefore holds only identifiers its own harness understands, and an alias's meaning can differ per target by design.
An alias is a lowercase kebab-case name, and each entry maps it to an ordered, non-empty list of that target's model identifiers, most preferred first.
Model identifiers are opaque strings to the generator, such as `grok[high]` for Cursor, which is not validated against a provider.

For each target, the adapter resolves the model in this order:

1. A direct value for that target in the role's `model` block wins.
2. Otherwise, the role's `alias` is looked up in that target's `alias_list`.
3. Otherwise, the target's native inheritance form is rendered: `model: inherit` for Cursor, and the inheritance representation verified for the recorded CAI version, rather than a literal copied from another target.

A resolved list renders natively where the target accepts one, such as CAI's `preferred_models`; a target that takes one model receives the list's first entry.
A direct value is a single identifier, or a list only for a target whose profile declares list support.
An alias that no target profile defines fails validation as a likely typo, while an alias defined for some targets and missing from another falls back to inheritance on that target and is recorded in the generation report.
The report and manifest record, per role and target, which rule selected the model and the value rendered.

For Claude Code, the current `opus` and `sonnet` values are native, and the parity check requires each ported role to render its current value, whether through a direct `claude` key or its alias.
A Claude alias such as `opus` is never reused as a Cursor model or a CAI provider selection; it reaches another target only through that target's own direct value or `alias_list`.
Generation does not contact providers, download models, or validate credentials; live model availability remains a separate preflight.

### Skill Dependencies

Role data declares skill dependencies once, in two lists: required skills the role needs loaded before it starts, and suggested skills it may load when relevant.
Every current agent has only required skills, taken from its `skills` preload list.

Dependencies follow the same best-effort rule as restrictions: a role is never withheld from a target because the target cannot preload its skills.

- Claude Code renders required skills as its native `skills` preload list and adds nothing to the body, which keeps the parity check exact.
- CAI renders required skills as `required_skills` and suggested skills as `suggested_skills`, when the target profile lists both as supported for the recorded version.
- Cursor has no documented subagent preload field, and discovering Claude agent files does not make Claude's `skills` field one.
  The Cursor adapter emits the list as a commented-out `skills` key, followed by a comment explaining that this harness does not preload the listed skills.
  It also opens the body with a fixed instruction to load each listed skill before starting work.

For a role with required skills `senior-developer` and `go-developer`, the Cursor frontmatter includes:

```yaml
# skills: [senior-developer, go-developer]
# This agent depends on the listed skills, but this harness does not
# preload them; the agent is instructed to load them before starting.
```

A suggested skill with no native field on a target becomes a body instruction to load it when relevant, with no commented key.
The comment and instruction wording are fixed generator strings, and skill names are validated against `skills/` before rendering.
The generation report and manifest record every dependency a target receives only as an instruction.
When a target gains a preload field, updating its target profile switches the rendering on the next generation, with no change to role sources.
Missing required shared packages fail validation; external or built-in dependencies need an explicit target declaration and separate runtime verification.

### Permissions and Capabilities

Separate behavioral instructions such as "do not edit" from runtime-enforced restrictions.
Shared role data declares restrictions once, as target-independent intent: `readonly` for a role that must not change files, and a tool allowlist where the role needs one.
Claude Code enforces a `tools` allowlist, so it represents both natively; for example, `reviewer` renders its current `tools: Read, Grep, Glob, Bash`.
Claude Code has no `readonly` key, so a read-only role is expressed there only through an allowlist that validation confirms excludes every file-writing tool, and no commented key is added; this keeps the parity check exact.
Cursor enforces its documented `readonly` field, which blocks file edits and state-changing shell commands, but has no per-tool allowlist.
The current CAI persona schema supports neither.

Restrictions are best effort on every target, and a role is never withheld from a target because the target cannot enforce one.
For each declared restriction, the adapter chooses one of two renderings from its target profile:

1. Supported: the target profile lists the field as enforced for the recorded application version, so the adapter emits the native key, such as Cursor's `readonly: true`.
2. Unsupported: the adapter emits the same key commented out in the frontmatter, followed by a comment explaining that the agent or persona is meant to be read-only, or limited to the listed tools, and that this harness may not enforce it.

For a read-only role, the unsupported rendering in a CAI persona looks like this:

```yaml
# readonly: true
# This persona is meant to be read-only, but this harness may not enforce
# that restriction; host approvals and sandbox policy remain the only limit.
```

A commented-out key is YAML comment text, not an unsupported field left for the parser to ignore, and the generator never emits an uncommented key the target profile does not list.
The key names and explainer wording are fixed generator strings, not role text, so role data cannot inject frontmatter through them; the tool list inside a commented `tools` key is validated against the shared allowlist before rendering.
The generation report and manifest record every unsupported restriction per role and target.
The role body keeps the restriction as a behavioral instruction on every target, since that is all an unsupported target has.

When a target gains enforcement, such as a future CAI `readonly` field, updating its target profile turns the commented key into a real key on the next generation, with no change to role sources.
Shell access is never labeled technically read-only solely because the body forbids writes.
On Cursor, `readonly: true` is host-enforced for shell commands as well as edits, so a read-only role with shell access is enforced there; on Claude Code, an allowlist that includes `Bash` leaves shell writes to host approvals.
Hooks, permission modes, background scheduling, MCP declarations, and other execution-affecting fields require individual target support rather than blind copying.

### Presentation

Presentation fields are optional target-specific data.
Unsupported color or display hints may be omitted only when classified as presentation-only, with the omission recorded in the generation report.
The same omission rule does not apply to model choice, dependencies, or permission restrictions.

## Generated Artifact Policy

Generated Claude Code agent files, Cursor agent files, CAI persona files, and the deterministic generation manifest are committed to Git alongside their shared sources.
Shared YAML, Markdown, and Jinja files remain the authoring source of truth; generated files must not be edited directly.
A source change that affects rendered output must include the regenerated artifacts in the same change so reviewers can inspect the exact native prompts.
Local `just ci` rebuilds the generated artifacts in place as its first step, the same way its Markdown lint already applies fixes, so a source edit followed by `just ci` leaves the checkout regenerated and validated.
The rebuild runs before the other checks, so `validate_agents.py`, link validation, and Markdown lint see the regenerated files.

The rebuild protects hand edits instead of overwriting them.
Before writing, it compares each managed file on disk with the output digest the manifest recorded at the last generation.
If any managed file differs from that digest, or a file the manifest does not list occupies a managed path, the rebuild writes nothing, names each such file, and fails `just ci`.
The author then moves the change into the role source, or restores the file, and runs `just ci` again.
Otherwise it publishes the complete output set atomically under the rendering contract above, removes obsolete managed files, and reports each file it created, changed, or removed.
An unchanged rebuild writes nothing and leaves file timestamps alone.

The hosted CI jobs in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) and [`.gitlab-ci.yml`](../../.gitlab-ci.yml) call the same recipe, with pinned dependencies.
Like `just lint-md`, the recipe switches to check-only mode when the `CI` environment variable is set to anything other than empty, `0`, or `false`, so hosted CI needs no separate recipe and no `git diff` step.
In check-only mode it fails on missing, changed, or obsolete managed artifacts and on manifest drift, because a committed change must already contain its regenerated output.
Neither local nor hosted CI installs anything.

Installation consumes the artifacts in the checkout without requiring Jinja or running the renderer.
Installing from uncommitted source edits requires running `just ci` first; installation is not a substitute for regeneration.
This selects the artifact policy for the proposed implementation and does not introduce a generator or alter current installation behavior.

## Installation Boundary

Rendering and installation are separate operations.
Rendering alone does not invoke an application, activate a persona, create global instructions, or change application configuration.
Claude Code agents keep the existing per-file links into `~/.claude/agents`; generation changes where those files come from, not how they are installed.

Both installers install the new targets by default as further steps of `just install`, following the existing Hermes pattern of acting only when the application is present and offering a switch to skip it:

- Cursor agents are linked into `~/.cursor/agents/` when `~/.cursor/` exists; `--no-cursor-agents` skips the step.
- CAI personas are linked into `$XDG_CONFIG_HOME/cai/personas/`, falling back to `~/.config/cai/personas/`, when that CAI configuration root exists; `--no-cai-personas` skips the step.
- The PowerShell installer offers `-NoCursorAgents` and `-NoCaiPersonas`; since the CAI target is Linux/XDG only, it reports the CAI step as unsupported on Windows rather than guessing a path.
- An absent application is reported as skipped, and neither step creates the application's configuration root.
- `--dry-run` reports every link either step would make, and writes nothing.

Every destination stays a real directory the application owns, and installation places one entry per generated file inside it.
Installation never links a whole output directory, such as `agents/` or `generated/cursor/agents/`, into an application's directory, because an application or user that writes its own agent there would land that file in this repository.
An existing whole-directory link to a repository output directory is migrated to a real directory, as the current installers already do for `~/.claude/skills` and `~/.claude/agents`.
Claude Code agents, Cursor agents, and CAI personas are all installed as per-file symlinks, so edits and regenerations take effect without reinstalling.

CAI integration targets the XDG root, not an inferred sibling of `CAI_CONFIG`.
The override can identify a custom config file during explicit diagnostics, but it is not fully supported for relocating all global artifacts and must not silently retarget generated persona installation.
If an existing CAI setup configures a different persona directory, report the mismatch and require an explicit destination decision rather than rewriting its configuration.

CAI personas are linked rather than copied, which requires a CAI change: its persona reader must accept a symlinked persona file instead of rejecting it.
That change belongs to CAI, not this repository, and should keep the reader's current protection by resolving the link once, reading the resolved target as a regular file, and confirming the opened file is the one it resolved.
The installer links personas regardless of the installed CAI version and does not detect or work around a CAI that still rejects symlinks; until the CAI change ships, CAI reports each linked persona as "not a regular file" and loads none of them.
There is no copy fallback and no version gate in the target profile.
Because personas are links, the installer never holds a copy that could drift, so it needs no ownership record, update step, or backup for them.
Links follow the same rules as every other per-file link: an existing link to the same file is reported as installed, a link elsewhere is skipped unless `--force` is passed, and a regular file in the way is always skipped with a notice.
Unrelated personas in the directory are never touched.
Removing a source role leaves a broken link that the installer reports and never removes, as it already does for skills and Claude Code agents.
Dry runs perform no writes or application startup, and repeated unchanged installations remain no-ops.
The Linux/XDG CAI target does not imply Windows support.

## Migration and Validation

The first implementation ports all nine current roles in one change: coder, docs-writer, feature-author, planner, researcher, reviewer, reviewer-go, spec-author, and test-runner.
That change ships the generator, the three target profiles and templates, every role source, the regenerated `agents/*.md`, the Cursor and CAI outputs, the manifest, the installer steps, and the documentation updates together.
The existing agents are the reference for testing the Claude Code adapter.
Port each role by hand into a role source, render it for Claude Code, and compare the result with the current `agents/<name>.md`.
A role passes the parity check when its rendered file keeps the same `name`, `description`, `model`, `color`, `tools`, `skills`, and body text as the hand-authored file, with any difference listed and approved in the change that ports it.
The change is not merged until all nine roles pass, so `agents/` switches from hand-authored to generated at once.
Its description lists every approved parity difference by role, so a schema mistake that affects several roles is visible in one place.
Porting never changes a role's public name or skill dependencies.
Render Cursor and CAI outputs for a role only after its Claude Code parity passes, and review them before installation.

Proposed acceptance evidence includes:

- Repeated generation produces byte-identical outputs and manifests; check-only mode never writes.
- Undefined variables, invalid YAML, missing skills, unresolved model mappings, restrictions with neither a native nor a commented rendering in the target profile, and filename collisions fail before publication.
- Malicious-looking role strings remain scalar data, and template includes or output paths cannot escape their approved roots.
- Consumer-parser fixtures and target allowlists agree on every emitted field; unknown-field tolerance cannot hide semantic loss.
- Cursor and CAI fixtures preserve role intent, dependency intent, target-specific loading instructions, and model inheritance behavior without asserting identical permissions.
- Each target's parser accepts frontmatter containing commented-out restriction and `skills` keys, and a restriction or dependency switches between commented and native rendering only through its target profile.
- All nine roles pass the Claude Code parity check, and adding or removing a target does not rewrite unrelated outputs.
- Disposable installation tests cover XDG defaults and overrides, the partial `CAI_CONFIG` boundary, user-file collisions, broken-link reports, no-op runs, and CAI discovery of symlinked personas.
- Application smoke checks verify discovery and loading separately from rendering, without model calls or executing the role where a local inspection surface is available.
- Local `just ci` regenerates in place before its other checks, refuses to overwrite a hand-edited or unlisted file at a managed path, and writes nothing when outputs are current.
- Hosted CI check-only mode rejects missing, changed, or obsolete committed artifacts and manifest drift without weakening existing lint or validation rules.
- Installer tests cover the default Cursor and CAI steps, both skip switches, absent applications, dry runs, and the Windows CAI report.

## Generator Tooling

The generator is a Python project in `tools/agentgen/`, managed with `uv`.
Its `pyproject.toml` declares the runtime dependencies, Jinja2 and PyYAML, and a `requires-python` range that includes the Python version the hosted CI jobs use.
The committed `uv.lock` pins every dependency, including transitive ones, with hashes.
TOML is used only for these two files, because `uv` and Python packaging accept no other format; every file the generator reads or writes, including role data, target profiles, alias lists, and the manifest, is YAML.

- Local `just ci` runs the generator with `uv run --locked --project tools/agentgen`, so a lock file that no longer matches `pyproject.toml` fails the run instead of being rewritten.
- The hosted CI jobs install `uv`, keep the GitHub and GitLab definitions in sync, and run the same recipe, which the `CI` environment variable switches to check-only mode.
- Dependency updates are deliberate changes that run `uv lock` and commit the new lock file, reviewed like any other change.
- The generator never installs packages into the system Python or the user's environment; `uv` manages its isolated environment.
- [`.ci_scripts/`](../../.ci_scripts/README.md) stays standard-library only, and the generator's own unit tests live under `tools/agentgen/` and run through the same locked environment.
- The installers do not need `uv`, Jinja, or PyYAML, because they consume committed artifacts.

Adopting the generator changes two current promises, and the implementation must update both in the same change: `.ci_scripts/README.md` states that a fresh clone runs `just ci` with only `just`, `python3`, and `markdownlint-cli2`, and the README's "No dependencies" highlight says the same.
Both gain `uv` as a required tool, and `just setup` should report a missing `uv` with install guidance rather than failing later inside `just ci`.

## Decisions Still Open

None; every decision is recorded above.
The CAI changes this design relies on, accepting symlinked persona files and a native `readonly` persona field, are tracked in CAI rather than here.

No template engine, renderer, native agent output, or install behavior is introduced by this draft.
