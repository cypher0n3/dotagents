# `dotagents`

[![License: MIT + CC BY 4.0](https://img.shields.io/badge/License-MIT%20%2B%20CC%20BY%204.0-blue.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-21-blueviolet)](skills/README.md)
[![Agents](https://img.shields.io/badge/agents-9-blueviolet)](agents/README.md)
[![Docs](https://img.shields.io/badge/docs-standards-informational)](docs/docs_standards/README.md)

## Overview

These are my agent skills and instructions, kept in one place and shared across every agent tool I use.
One directory under [`skills/`](skills/README.md) is one skill.
Claude Code, Codex, Cursor, Gemini, Grok, and GitHub Copilot in VS Code all read that same directory through symlinks, so I edit a skill once and it takes effect everywhere the next time a session starts.
One file under [`agents/`](agents/README.md) is one Claude Code subagent that preloads the skills its role needs, linked into `~/.claude/agents` the same way.

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

- 🧩 **One source of truth**: every agent tool reads the same `skills/` directory through symlinks; there are no per-tool copies to drift.
- 🤖 **Agents built on skills**: a coder, two reviewers, test runner, researcher, planner, spec author, feature author, and docs writer, each preloading the skills for its role, with a model chosen per role.
- 🔗 **One-command install**: `just install` creates the links each tool expects, and `just install-dry-run` shows the plan first.
- ✅ **Validated**: `just ci` checks skill frontmatter, naming, agent manifests, agent definitions, Markdown conventions, and internal links.
- 📐 **Documented conventions**: the frontmatter contract and prose rules live in [docs/docs_standards/](docs/docs_standards/README.md), not in reviewers' heads.
- 🪶 **No dependencies**: the checks are Python standard library plus `markdownlint-cli2`, so a fresh clone validates immediately.

## Quick Start

Install [`just`](https://github.com/casey/just) and [`markdownlint-cli2`](https://github.com/DavidAnson/markdownlint-cli2), then clone and install:

```bash
git clone https://github.com/cypher0n3/dotagents.git ~/.agents
cd ~/.agents
just setup            # fetch the custom markdownlint rules
just install-dry-run  # review the links that would be created, changing nothing
just install          # link skills, agents, and instructions into every agent tool
just ci               # run the full local check suite
```

To adapt this collection as your own, fork it on GitHub and clone the fork instead.
Enable Actions on the fork so a daily workflow can merge `main` from here; see [Keeping a GitHub Fork Current](CONTRIBUTING.md#keeping-a-github-fork-current).

I keep the clone at `~/.agents`, and the documentation assumes that path.
Nothing requires it: `just install` resolves the repository root at run time and points every link at wherever the clone actually lives.
If you move or re-clone it, run `just install --force` to repoint the links, because an existing link that points somewhere else is skipped rather than replaced.

Nothing is copied into the agent tools.
`just install` only creates symlinks back into this clone, so editing a file here changes what every tool reads, and deleting the clone breaks those links rather than leaving stale copies behind.

### Windows Setup With PowerShell

For Windows with PowerShell and GitHub Copilot in VS Code, follow the [Windows Setup Guide](WINDOWS_SETUP.md):

```powershell
git clone https://github.com/cypher0n3/dotagents.git ~/.agents
cd ~/.agents

# Run installation script (no admin rights or Developer Mode required)
.\scripts\install.ps1 -DryRun
.\scripts\install.ps1

# Run validation
python .ci_scripts/validate_skills.py skills
```

The Windows installer links the same way without requiring administrator rights or Developer Mode: directory junctions for `skills/` and per-skill targets, and hard links (or a hash-checked copy, when the clone and home directory are on different drives) for single files.
See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for full details including troubleshooting.

Use `just --list` to see every recipe.

## Installation Layout

`just install` creates four kinds of link, because the agent tools disagree about what a skills directory is and about where global instructions live.

- Whole-directory links, one symlink pointing at `skills/`: `~/.claude/skills`, `~/.cursor/skills`, `~/.gemini/config/skills`, and `~/.copilot/skills`.
- Per-agent links, one symlink per agent file inside `~/.claude/agents`.
  Only Claude Code reads this file format, so only its directory receives them, and linking file by file leaves any agent already sitting there untouched.
  Anything in that directory this repository does not provide is reported at the end of the run and never removed, so a renamed agent's dangling link is visible without putting your own agents at risk.
- Per-skill links, one symlink per skill inside a directory the tool manages itself: `~/.codex/skills` and `~/.grok/skills`.
- Instruction-file links, one symlink pointing at `AGENTS.md`: `~/.claude/AGENTS.md`, `~/.codex/AGENTS.md`, `~/.cursor/rules/AGENTS.md`, `~/.gemini/GEMINI.md`, and `~/.grok/AGENTS.md`.
  The Gemini link uses that tool's own filename, which is what it reads by default.

It also installs the Claude Code and Cursor status lines: `~/.claude/statusline-command.sh` is linked to [claude/statusline-command.sh](claude/statusline-command.sh), `~/.cursor/statusline-command.sh` is linked to [cursor/statusline-command.sh](cursor/statusline-command.sh), and each tool's settings file is pointed at its script, with the existing file backed up alongside first and every other setting left untouched.
Pass `--no-statusline` (`just install --no-statusline`) to skip that step entirely.

It then turns off agent commit and PR attribution in every tool that supports the setting:
`attribution.commit` and `attribution.pr` in Claude's `settings.json`, `commit_attribution` in Codex's `config.toml`, and `attribution.attributeCommitsToAgent` and `attribution.attributePRsToAgent` in Cursor's `cli-config.json`.
Gemini and Grok document no such setting, so nothing is changed for them.
Each file is backed up before it is written, every other setting is left alone, a tool that is not installed is skipped, and `--no-attribution` skips the step.

An existing path is never replaced silently.
A link that already points here is reported as installed, a link pointing elsewhere is skipped unless `--force` is passed, and a real directory or file in the way is always skipped with a notice.

## Repository Layout

- [skills/](skills/README.md) - the skills themselves, one directory per skill, indexed by category.
- [agents/](agents/README.md) - the Claude Code subagents, one file per agent, each preloading the skills for its role.
- [docs/](docs/README.md) - documentation for this repository.
- [docs/docs_standards/](docs/docs_standards/README.md) - skill, agent, and Markdown authoring standards.
- [.ci_scripts/](.ci_scripts/README.md) - dependency-free validation helpers and their unit tests.
- [scripts/](scripts/install.sh) - the symlink installer.
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
No new symlink is needed for a whole-directory target; run `just install` again to link a new skill into the per-skill targets.

## Adding an Agent

Create `agents/<agent-name>.md` with `name`, `description`, and `model` frontmatter, list the skills it preloads under `skills`, and write its system prompt under a single H1.
The `name` must match the filename, every preloaded skill must exist under `skills/`, and the agent must be linked from [agents/README.md](agents/README.md).

Read [Agent Authoring Standards](docs/docs_standards/agent_authoring.md) first, then run `just ci`.
No new symlink is needed, because `~/.claude/agents` points at the whole directory.

## Documentation

- [Skill Index](skills/README.md) - every skill, grouped by what it is for.
- [Agent Index](agents/README.md) - every Claude Code agent, with its model and the skills it preloads.
- [Skill Authoring Standards](docs/docs_standards/skill_authoring.md) - the rules a skill must follow.
- [Agent Authoring Standards](docs/docs_standards/agent_authoring.md) - the rules an agent must follow.
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
