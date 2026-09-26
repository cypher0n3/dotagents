# `dotagents`

[![License: MIT + CC BY 4.0](https://img.shields.io/badge/License-MIT%20%2B%20CC%20BY%204.0-blue.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-21-blueviolet)](skills/README.md)
[![Agents](https://img.shields.io/badge/agents-9-blueviolet)](agent_sources/README.md)
[![Docs](https://img.shields.io/badge/docs-standards-informational)](docs/docs_standards/README.md)

## Overview

These are my agent skills and instructions, kept in one place and shared across every agent tool I use.
One directory under [`skills/`](skills/README.md) is one skill.
Claude Code, Codex, Cursor, Gemini, Grok, and GitHub Copilot in VS Code read that directory through symlinks; Hermes Agent scans it as an external skill directory, and CAI discovers `~/.agents/skills/` natively.
I edit a skill once and consumers pick it up through their normal reload or session-start behavior.
One file under [`agent_sources/`](agent_sources/README.md) is one agent that preloads the skills it needs, and is the only place that agent is written.
`just ci` and `just install` generate it as a Claude Code subagent, a Codex agent, a Cursor agent, and a Hermes personality, each installed the way its tool expects, and CAI reads the file directly.

They are personal and opinionated; see [Scope and Point of View](#scope-and-point-of-view) before adopting them wholesale.

## Scope and Point of View

These come from my own experience working with AI coding tools across documentation-heavy, spec-first Go, Python, and Markdown projects.
They encode the working style those projects settled on rather than a neutral summary of industry practice.

Concretely, they assume things like these:

- Requirements and technical specifications are canonical, and code follows them rather than the reverse.
- Documentation is linted like code, one sentence per line, with the repository's own standards taking precedence over any general rule.
- A task runner (`just`, or `make`) is the entry point for building, linting, and testing, and agents call its recipes rather than the underlying tools.
- Linter suppressions and lowered coverage thresholds are not acceptable ways to make a check pass.
- Plans are explicit, test-gated, and written down before implementation starts.

None of that is universal, and some of it will be wrong for your repository.
Treat these as a starting point to fork and adapt: expect to change trigger phrases, tooling assumptions, and thresholds to match how your team actually works.
Where a skill can discover a convention from the repository it is running in, I have written it to do that and to prefer what it finds over its own defaults.

## Highlights

- 🧩 **One source of truth**: every agent tool reads the same `skills/` directory through links or external-directory registration; there are no per-tool copies to drift.
- 🤖 **Agents built on skills**: a coder, two reviewers, test runner, researcher, planner, spec author, feature author, and docs writer, each preloading the skills for its role, with a model chosen per role.
- 🧬 **One file per agent**: each agent is written once in `agent_sources/` and generated for Claude Code, Codex, Cursor, and Hermes, which CAI reads directly, with every restriction a tool cannot enforce stated rather than dropped.
- 🔗 **One-command install**: `just install` creates the links each tool expects and registers the skills and personalities with an existing Hermes setup; `just install-dry-run` shows the plan first.
- ✅ **Validated**: `just ci` generates the agents, then checks skill frontmatter, naming, agent manifests, agent definitions, Markdown conventions, and internal links.
- 📐 **Documented conventions**: the frontmatter contract and prose rules live in [docs/docs_standards/](docs/docs_standards/README.md), not in reviewers' heads.
- 🪶 **No dependencies**: the checks and the agent generator are Python standard library plus `markdownlint-cli2`, so a fresh clone validates immediately.

## Quick Start

Install [`just`](https://github.com/casey/just), [`markdownlint-cli2`](https://github.com/DavidAnson/markdownlint-cli2), and Python 3, then clone and install:

```bash
git clone https://github.com/cypher0n3/dotagents.git ~/.agents
cd ~/.agents
just setup            # fetch the custom markdownlint rules
just install-dry-run  # generate the agents and review the links that would be created
just install          # generate the agents, install supported links, and register with Hermes
just ci               # run the full local check suite
```

To adapt this collection as your own, fork it on GitHub and clone the fork instead.
Enable Actions on the fork so a daily workflow can merge `main` from here; see [Keeping a GitHub Fork Current](CONTRIBUTING.md#keeping-a-github-fork-current).

I keep the clone at `~/.agents`, and the documentation assumes that path.
For link-based consumers, `just install` resolves the repository root at run time and points every link at wherever the clone actually lives.
If you move or re-clone it, run `just install --force` to repoint the links, because an existing link that points somewhere else is skipped rather than replaced.
CAI is different: its automatic global shared-skill discovery uses `~/.agents/skills/`, and this installer does not redirect CAI to a clone elsewhere.

On Unix, skill content stays in this clone.
`just install` creates symlinks for the other tools and registers the skills directory with Hermes, so edits stay shared rather than leaving stale copies behind.
Deleting the clone breaks the links and leaves Hermes pointing at a missing external directory.

### Windows Setup With PowerShell

For Windows with PowerShell 7 or higher (`pwsh`) and GitHub Copilot in VS Code, follow the [Windows Setup Guide](WINDOWS_SETUP.md):

```powershell
git clone https://github.com/cypher0n3/dotagents.git ~/.agents
cd ~/.agents

# Run installation script (no admin rights or Developer Mode required)
.\scripts\install.ps1 -DryRun
.\scripts\install.ps1

# Run validation
python .ci_scripts/validate_skills.py skills
```

The Windows installer links the same way without requiring administrator rights or Developer Mode: directory junctions for each skill, and hard links (or a hash-checked copy, when the clone and home directory are on different drives) for single files.
See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for full details including troubleshooting.

Use `just --list` to see every recipe.

## Installation Layout

`just install` creates three kinds of link, because the agent tools disagree about what a skills directory is and about where global instructions live.

- Per-agent links, one symlink per generated agent file: `generated/claude/agents/` into `~/.claude/agents`, `generated/codex/agents/` into `~/.codex/agents`, and `generated/cursor/agents/` into `~/.cursor/agents`.
  The installer first generates them from `agent_sources/` with `.ci_scripts/generate_agents.py`, the same code `just ci` runs; `generated/` is never committed, and without Python the agent steps are skipped.
  Each tool gets the files generated in its own format, because another tool's compatibility reader does not establish support for every field.
  Linking file by file leaves any agent already sitting there untouched, and an older install that linked a whole agent directory is migrated to a real directory the same way skills are.
  Anything in those directories this repository does not provide is reported at the end of the run and never removed, so a renamed agent's dangling link is visible without putting your own agents at risk.
  `--no-codex-agents` and `--no-cursor-agents` skip their step, and a link left by the older `agents/` layout is relinked without `--force`.
- Per-skill links, one symlink per skill inside a real directory the tool manages itself: `~/.claude/skills`, `~/.cursor/skills`, `~/.gemini/config/skills`, `~/.copilot/skills`, `~/.codex/skills`, and `~/.grok/skills`.
  A tool can write its own skills next to yours (Claude Code syncs vendored ones into `~/.claude/skills`), and a symlink to `skills/` as a whole would land that content in this repository.
  An older install that linked `skills/` as a whole is migrated to a real directory, a `skills/` entry without a `SKILL.md` is never linked, and a link to a skill that no longer exists is reported and left in place.
  Migration does not move out anything a tool already wrote through the old link, so every `skills/` directory without a `SKILL.md` is reported for you to remove.
- Instruction-file links, one symlink pointing at `AGENTS.md`: `~/.claude/AGENTS.md`, `~/.codex/AGENTS.md`, `~/.cursor/rules/AGENTS.md`, `~/.gemini/GEMINI.md`, and `~/.grok/AGENTS.md`.
  The Gemini link uses that tool's own filename, which is what it reads by default.

It also installs the Claude Code and Cursor status lines: `~/.claude/statusline-command.sh` is linked to [claude/statusline-command.sh](claude/statusline-command.sh), `~/.cursor/statusline-command.sh` is linked to [cursor/statusline-command.sh](cursor/statusline-command.sh), and each tool's settings file is pointed at its script, with the existing file backed up alongside first and every other setting left untouched.
Pass `--no-statusline` (`just install --no-statusline`) to skip that step entirely.

It then turns off agent commit and PR attribution in every tool that supports the setting:
`attribution.commit` and `attribution.pr` in Claude's `settings.json`, `commit_attribution` in Codex's `config.toml`, and `attribution.attributeCommitsToAgent` and `attribution.attributePRsToAgent` in Cursor's `cli-config.json`.
Gemini and Grok document no such setting, so nothing is changed for them.
Each existing settings file is backed up once per install before its first change, every other setting is left alone, a tool that is not installed is skipped, and `--no-attribution` skips the step.

An existing path is never replaced silently.
A link that already points here is reported as installed, a link pointing elsewhere is skipped unless `--force` is passed, and a real directory or file in the way is always skipped with a notice.

### Hermes Agent

Install and configure Hermes first, then run `just install` (or `scripts/install.ps1` on Windows).
The installer uses `hermes config get` and `hermes config set` to append this clone's absolute `skills/` path to `skills.external_dirs` in the selected Hermes `config.yaml`.
It requires a Hermes CLI with JSON config reads and structured list writes, and skips Hermes with a notice when the command or existing configuration is missing.
Use `--no-hermes` on Unix or `-NoHermes` in PowerShell to skip this step independently of status-line and attribution settings.

- The selected home is a nonblank `HERMES_HOME`, or the platform default: `~/.hermes` on Unix and `%LOCALAPPDATA%/hermes` on native Windows (falling back to `~/AppData/Local/hermes` when `LOCALAPPDATA` is unset).
  CLI calls are pinned to that home; the installer does not follow a sticky active-profile selection or enumerate other profiles.
- Existing external directories are retained as returned by Hermes's CLI, which can expand environment-variable placeholders when a write is needed.
  Equivalent paths are not appended again; relative entries are interpreted against the Hermes home.
- A changed configuration receives the same timestamped original backup as the other settings files, and the installer reads the setting back after writing it.
  Hermes's own serializer controls YAML formatting; the backup preserves the original bytes.
- Dry runs report the planned registration without invoking Hermes, so they cannot trigger CLI startup side effects.
  Because they do not read the effective setting, the preview says the path will be appended only if absent.
- Hermes's bundled and learned skills, `SOUL.md`, memories, credentials, and other settings are not replaced by the installer.
  Local skills take precedence in the index, but current Hermes versions can reject a bare-name load when local and external skills share that name.
  Use an unambiguous categorized path when available or resolve the naming collision yourself; the installer never renames or deletes skills.
- External skills are shared, not read-only: Hermes can modify or delete them in this clone when its skill-management tools are used.
  Review those changes in Git, or use filesystem permissions if the shared skills must be protected.

Start a new Hermes session after installation and load a shared skill by name, for example `/make-commit`.
For the default Unix profile, check the registered directories without starting a model session:

```bash
HERMES_HOME="$HOME/.hermes" hermes config get skills.external_dirs --json
```

For a custom home or profile, substitute the same `HERMES_HOME` used during installation so a sticky profile cannot redirect the check.

Hermes has no agent files, so each agent is also set as a personality under `agent.personalities.<name>`, through `hermes config set`, from `generated/hermes/personalities/`.
Personalities apply to a whole session once selected with `/personality`, and the installer never selects one.

- An absent personality is added, and an unchanged one is left alone.
- The installer records a digest of each personality it sets in `${XDG_STATE_HOME:-~/.local/state}/dotagents/install-state.json`, and updates a personality without `--force` only while its value still matches that record.
- A personality of the same name that the installer did not set, or that you edited after it did, is skipped unless you pass `--force`; the previous value survives in the configuration backup.
- A personality whose agent no longer exists is reported and left in place.
- `--no-hermes-personalities` skips this step; `--no-hermes` skips it and the skill registration.

This integration does not share Claude Code's status-line implementation.
The installer does not create `~/.hermes/AGENTS.md`, which is not a global instruction file for Hermes, and does not replace `SOUL.md` with this repository's instructions.
Hermes reads project context files independently; an `AGENTS.override.md` replaces the adjacent `AGENTS.md` rather than supplementing it.
Tool-specific invocation metadata such as `disable-model-invocation` is not a portable enforcement boundary.
See the [Hermes skills documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) and [project context documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files).

### CAI

CAI (Cypher's Agent Interface) discovers `~/.agents/skills/` directly, with no installer link, package copy, or YAML setting required for a clone at `~/.agents`.
Neither installer changes CAI configuration, instructions, personas, or native skills.
This integration targets CAI's Linux/XDG layout; it does not imply native Windows support.

For a single project, skill-name precedence is:

1. Project `.cai/skills/`.
2. Project `.agents/skills/`.
3. CAI's configured native global skills directory, defaulting to `$XDG_CONFIG_HOME/cai/skills/`.
4. Global `~/.agents/skills/`.
5. CAI built-in skills.
6. Enabled product-specific foreign skills, currently project `.cursor/skills/`.

The first valid candidate wins; definitions do not merge.
Multi-project workspaces also include their member-project roots before global roots.
CAI watches shared skill roots for changes, while active skills remain bound to their selected source rather than silently switching to a new same-name winner.

The supported CAI global configuration root for this integration is `$XDG_CONFIG_HOME/cai`, falling back to `~/.config/cai` when `XDG_CONFIG_HOME` is unset.
`CAI_CONFIG`, when present, selects a custom configuration file, primarily for testing and custom configurations; it is not a fully supported relocation mechanism for all global artifacts.
Current instruction discovery can follow that file's directory while other artifacts retain their XDG root.
Do not infer skill, persona, or instruction installation destinations from `CAI_CONFIG`; this integration writes none of them.

In a running CAI session, inspect the shared catalog without activating skills:

```text
/skills --all ~/.agents/skills
```

Check the displayed source, winning or shadowed state, and compatibility markers rather than treating a successful `just install` as proof of CAI loading.
To exercise direct activation without requesting a commit or another external effect, use a shared review skill with a read-only task:

```text
$code-review-precision Review the current diff without changing files.
```

Current compatibility boundaries are deliberate:

- The tracked regular skill packages match CAI's package layout; symlinked child packages such as locally linked system skills are skipped by its scanner.
- CAI does not automatically read `~/.agents/AGENTS.md` as global instructions and rejects symlinked instruction files.
  The shared repository's `AGENTS.override.md` is repository-specific, not a global instruction source.
- CAI is meant to read the agents in `~/.agents/agent_sources/` directly, as it reads `~/.agents/skills/`, so nothing is generated or installed for it; see [CAI Native Agent Sources](docs/draft_specs/cai-native-agent-sources.md) for the CAI change this needs.
  Until CAI ships it, CAI does not see these agents.
- CAI does not enforce `user-invocable` or `disable-model-invocation` as activation policy, and `allowed-tools` declarations do not grant or restrict authority.
  Skill prose does not replace host-side approvals or sandbox policy.
- [`detailed-execution-planner`](skills/detailed-execution-planner/SKILL.md) selects a native CAI planning workflow separately from Cursor's plan format.
  [`update-cursor-todos`](skills/update-cursor-todos/SKILL.md) remains Cursor-only.

CAI's shared-configuration proposal, draft 470, is deferred; this integration does not depend on its proposed runtime adapters or configuration keys.
[Shared Agent Templates](docs/specs/shared-agent-templates.md) specifies how each tool's agents come from the shared sources.

### Cursor CLI Configuration Location

Both installers resolve Cursor's `cli-config.json` using the same directory precedence as the CLI:

1. `CURSOR_CONFIG_DIR`, when set to a nonblank value.
2. `cursor` under `XDG_CONFIG_HOME`, when set to a nonblank value.
3. `~/.cursor` otherwise.

Status-line and attribution settings use this resolved file, and backups are saved beside it.
A normal status-line install creates the selected configuration directory if needed; a dry run does not.
The status-line script and the skill and instruction links remain under `~/.cursor`; these environment variables only change where the installer writes CLI settings.

### Settings Backups

Both installers save one backup per changed, pre-existing settings file per install, beside the original file.
The backup preserves the file before either the status line or attribution is changed; a second change in the same run does not replace it.

Backup names use `<filename>.<timestamp>.bak`, with a shared local ISO 8601 basic timestamp for the run: `yyyyMMddTHHmmss.ffffff+HHmm` (or `-HHmm` for a negative UTC offset).
For example, `settings.json.20260920T041530.123456-0400.bak` uses a filename-safe timestamp with no colons, including on Windows.
A later install that changes settings creates new backups and retains earlier ones, including legacy `.bak` files.
A filename collision aborts the affected change instead of overwriting a backup.
Dry runs, unchanged files, and files first created by the current install produce no backups.

## Repository Layout

- [skills/](skills/README.md) - the skills themselves, one directory per skill, indexed by category.
- [agent_sources/](agent_sources/README.md) - one file per agent, the only place an agent is written, and the agent index.
- `generated/` - each tool's agents, generated from `agent_sources/` by `just ci` and `just install` and never committed.
- [docs/](docs/README.md) - documentation for this repository.
- [docs/docs_standards/](docs/docs_standards/README.md) - skill, agent, and Markdown authoring standards.
- [docs/specs/](docs/specs/README.md) - specifications for implemented designs.
- [.ci_scripts/](.ci_scripts/README.md) - dependency-free validation helpers, the agent generator, and their unit tests.
- [scripts/](scripts/install.sh) - the installers.
- [claude/](claude/statusline-command.sh) - Claude Code configuration kept in this repository and linked into `~/.claude`.
- [cursor/](cursor/statusline-command.sh) - Cursor CLI configuration kept in this repository and linked into `~/.cursor`.
- [justfile](justfile) - setup, install, lint, and validation entry points.
- [AGENTS.md](AGENTS.md) - my global instructions for coding agents, distributed with the skills.
- [AGENTS.override.md](AGENTS.override.md) - agent instructions specific to this repository.
- [CONTRIBUTING.md](CONTRIBUTING.md) - how to report problems and propose changes or new skills.
- [meta.md](meta.md) - orientation for agents, and this repository's boundaries.

## Adding a Skill

Create `skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter, then write the instructions under a single H1.
The `name` must match the directory.
The `description` opens with one short line saying what the skill is for, and adds a single "Use this skill when ..." sentence only when the model may invoke it on its own.

Read [Skill Authoring Standards](docs/docs_standards/skill_authoring.md) first, then run `just ci`.
Run `just install` again to link the new skill into every tool's skills directory.

## Adding an Agent

Create `agent_sources/<agent-name>.md` with `schema`, `name`, `description`, `model`, and `color` front matter, list the skills it preloads under `skills`, and write its instructions under a single H1.
The `name` must match the filename, every skill must exist under `skills/`, and the agent must be linked from [the agent index](agent_sources/README.md).
Copy an existing agent for the shape, and see [Shared Agent Templates](docs/specs/shared-agent-templates.md#agent-source-files) for every key.

Read [Agent Authoring Standards](docs/docs_standards/agent_authoring.md) first, then run `just ci`, which generates and validates every tool's version; commit only the source.
Run `just install` again to link the new agent into each tool, since agents are linked one file at a time.

## Documentation

- [Skill Index](skills/README.md) - every skill, grouped by what it is for.
- [Agent Index](agent_sources/README.md) - every agent, with its model tier and the skills it preloads.
- [Skill Authoring Standards](docs/docs_standards/skill_authoring.md) - the rules a skill must follow.
- [Agent Authoring Standards](docs/docs_standards/agent_authoring.md) - the rules an agent must follow.
- [Shared Agent Templates](docs/specs/shared-agent-templates.md) - how each agent is generated and installed for every tool.
- [Markdown Conventions](docs/docs_standards/markdown_conventions.md) - the prose and lint conventions.
- [meta.md](meta.md) - orientation for agents, and this repository's boundaries.

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
[AGENTS.md](AGENTS.md) holds my global agent instructions; rules specific to this repository live in [AGENTS.override.md](AGENTS.override.md).

## License

This repository uses a split license, recorded in [LICENSE](LICENSE).
Scripts, just recipes, CI helpers, and linter configuration are MIT licensed.
The skill definitions under `skills/` and the project documentation are licensed under CC BY 4.0.

Skill files carry no per-file license notice, because a `SKILL.md` is loaded into the model's context in full on every invocation.
See [Licensing](CONTRIBUTING.md#licensing) for how to attribute a skill you copy or adapt into your own project.
