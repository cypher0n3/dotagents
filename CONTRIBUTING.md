# Contributing

## Overview

Contributions are welcome, including bug reports, factual corrections, portability fixes, new skills, and new agents.
This is a personal, opinionated collection, so read [Scope and Point of View](README.md#scope-and-point-of-view) first to understand the assumptions the skills carry.

## What is Most Useful

- Factual corrections to a skill: an example that does not compile, a version claim that is wrong, an API that has changed, a command that does not do what the skill says it does.
- Portability fixes: a skill that assumes a directory layout, tool, or filename it should discover instead.
- Routing improvements: a description that fails to fire when it should, or fires when it should not.
- New skills, subject to the vetting described below.

A correction that comes with the evidence behind it is worth several that do not.
Say what you ran and what it produced.

## Keeping a GitHub Fork Current

Forks of this repository on GitHub get a daily Actions workflow that merges `main` from the parent into the fork's `main`, the same operation as the Sync fork button.
The workflow is [`.github/workflows/sync-fork.yml`](.github/workflows/sync-fork.yml).
It does not run on this repository, only on a fork.

Scheduled workflows stay disabled on a new fork until you turn Actions on from the Actions tab.
Use **Sync fork** on that same tab if you want an update before the next daily run.

A conflict with commits of your own on `main` fails the job.
Resolve it with GitHub's Sync fork button, or merge `upstream/main` locally.

The default `GITHUB_TOKEN` cannot apply upstream commits that change workflow files.
If a sync fails with a workflows-permission error, add a `SYNC_FORK_TOKEN` repository secret whose personal access token has contents and workflows write permission, then re-run the workflow.

## New Skills

New skills are welcome, and they are subject to additional vetting by me before they are merged.

Because this collection reflects practice I can vouch for, a new skill is reviewed not only for correctness but for whether it fits the collection and earns its place in it.
Expect questions about where you used the skill, what problem it solved, and how it behaves when its assumptions do not hold.
A skill may be declined as a poor fit even when it is well written, and that is not a judgment about its quality.

Before opening a request that adds a skill:

- Read [Skill Authoring Standards](docs/docs_standards/skill_authoring.md) and follow it.
- Include one skill per request, so it can be evaluated on its own.
- Say where you actually used the skill and what it changed about the outcome.
- Confirm that it does not duplicate an existing skill, or explain why the overlap is worth having.

## New Agents

An agent is held to the same vetting as a skill, and to one more test: it must preload existing skills rather than restate them.
Agents are authored as role sources under [`agent_sources/`](agent_sources/README.md) and generated into `agents/` and `generated/`, so change the source and commit the regenerated files that `just ci` writes.
If the rule you want the agent to follow is not in a skill, add or extend the skill first and have the agent preload it, so the rule is written once and every tool that reads the skill sees it.
Read [Agent Authoring Standards](docs/docs_standards/agent_authoring.md) before opening the request, and say which model you chose and why.

## Before Opening a Request

Run the full local gate and make sure it passes:

```bash
just setup
just ci
```

That regenerates the agents from `agent_sources/`, then runs Markdown lint, internal link validation, skill frontmatter and manifest validation, agent frontmatter and index validation, the offline unit tests, the agent generator's tests, and shell lint.
See [`.ci_scripts/README.md`](.ci_scripts/README.md) for what each validator checks.

Do not modify [`.markdownlint.yml`](.markdownlint.yml) or [`.markdownlint-cli2.jsonc`](.markdownlint-cli2.jsonc), and do not add lint suppressions, to make a check pass.
If a rule is genuinely wrong for a case, raise that as its own discussion.

## Reporting a Problem

Open an issue that names the skill, quotes the instruction at fault, and describes what the agent did with it.
Include the agent tool and version when the behavior is tool-specific, because these skills are used from several different tools.

## Licensing

This repository uses a split license, and [LICENSE](LICENSE) is the authoritative statement of it.

- Scripts, just recipes, CI helpers, and linter configuration are licensed under the **MIT License**.
- The skill definitions under `skills/`, their reference files and agent manifests, the agent definitions under `agents/`, and the project documentation are licensed under the **Creative Commons Attribution 4.0 International Public License (CC BY 4.0)**.

Skill files carry no per-file license notice, because everything in a `SKILL.md` is loaded into the model's context on every invocation and a notice there would cost context without doing any work.
The license travels with the repository, not with the individual file, so anyone copying a skill out is responsible for carrying the attribution with it.

### Using a Skill in Your Own Project

Copying, adapting, and redistributing the skills is allowed under CC BY 4.0, including commercially, provided you give attribution.
An attribution line like this satisfies it:

```text
Adapted from "dotagents" (c) G. Andre Vaillancourt, used under CC BY 4.0.
https://creativecommons.org/licenses/by/4.0/
```

Put it wherever your project records third-party attributions, such as a `NOTICE` file, a credits section in your README, or the documentation for your own skills directory.
State that you changed the skill when you have adapted it, which CC BY 4.0 requires.
Do not add the attribution as a comment inside the `SKILL.md` itself, for the same context reason described above.

### Licensing of Contributions

By contributing you agree that your contribution is licensed under the terms in [LICENSE](LICENSE), under whichever of the two licenses above covers the files you touched.
