# Agent Index

## Overview

Each Markdown file here is the one source for one agent: its YAML front matter says everything about the agent, and its body is the agent's instructions.
Edit an agent only here.
`just ci` and `just install` generate every tool's version of it under `generated/`, which is not committed; see [Shared Agent Templates](../docs/specs/shared-agent-templates.md) for how each field maps to each tool.
This index is maintained by hand.
See [Agent Authoring Standards](../docs/docs_standards/agent_authoring.md) before adding or editing an agent.

These agents are templates in the sense the rest of this repository uses the word: opinionated starting points to fork and adapt.
Each one preloads the skills it needs from [`skills/`](../skills/README.md) rather than restating them, so the skill is the single place a rule is written.
Where a role's rules depend on what it is handed, such as the language of a test or the type of a document, the agent preloads only what always applies and loads the rest on match.
A project can override any agent by putting a file with the same name in its tool's project agent directory, such as `.claude/agents/`.

## Where Each Tool Gets Them

- Claude Code, Codex, and Cursor read the generated agents that `just install` links into `~/.claude/agents`, `~/.codex/agents`, and `~/.cursor/agents`, one file at a time.
- Hermes gets each agent as a personality that `just install` sets in its configuration.
- CAI reads this directory directly, so its personas need no generation or installation.

## Agents

- [`coder`](coder.md) - implements one scoped change end to end, with tests, and proves it against the repository's checks.
  Tier `strong`; preloads `senior-developer`, `go-developer`, and `just-ci`; inherits every tool.
- [`reviewer`](reviewer.md) - performs adversarial review of a change in any language without editing anything, and runs the repository's checks as part of the review.
  Tier `strong`; preloads `senior-developer` and `code-review-precision`; read-only, with read tools plus the shell for lint and tests.
- [`reviewer-go`](reviewer-go.md) - performs the same review for Go, against modern Go practice and its concurrency and security risks.
  Tier `strong`; preloads `senior-go-dev-reviewer` and `code-review-precision`; the same read-only tools.
  Both reviewers share the color `red`, because the color names the role and the suffix names the scope.
- [`test-runner`](test-runner.md) - runs the tests, diagnoses each failure down to a root cause, and writes or repairs tests when the task calls for it.
  Tier `standard`; preloads `senior-developer` and `just-ci`, and loads the language's test skill on match.
- [`researcher`](researcher.md) - gathers facts from the repository and the web and reports them with exact references, without making changes.
  Tier `standard`; no preloaded skills; read-only, with read tools plus web fetch and search.
- [`planner`](planner.md) - turns a task into a detailed, test-gated execution plan as a Markdown checklist.
  Tier `strong`; preloads `detailed-execution-planner`; read tools plus write access for the plan file.
- [`spec-author`](spec-author.md) - writes and revises requirements and technical specifications to the repository's standards, then lints them.
  Tier `standard`; preloads `spec-authoring`, `requirements-authoring`, and `markdown-writer`.
- [`feature-author`](feature-author.md) - writes and revises Gherkin feature files that trace to requirements and specifications, then lints them.
  Tier `standard`; preloads `feature-files-authoring` and `markdown-writer`.
- [`docs-writer`](docs-writer.md) - writes, revises, and audits Markdown documentation against the repository's own conventions and leaves it lint clean.
  Tier `standard`; preloads `markdown-writer`, and loads the skill for the document type, or `code-review-precision` for an audit, on match.

## Model Selection

Each agent names a tier rather than a model, and the generator maps the tier to each tool's model, so an agent tracks the current release of its tier without an edit here.
For Claude Code, `frontier` maps to `fable`, `strong` to `opus`, `standard` to `sonnet`, and `fast` to `haiku`; a tool with no mapping for a tier uses its session's model.

- `strong` goes to the roles where judgment is the product: implementing against a specification, either kind of adversarial review, and planning.
  A missed defect or a wrong plan costs more than the difference in price.
- `standard` goes to the roles that are bounded by written conventions and a lint gate: research, test running, and the three authoring roles.
  Those agents follow rules the skills state and the repository's checks enforce, so the mid tier is enough and runs faster.
  Test running sits here rather than with `strong` because a test either passed or it did not, and the agent is told to report the real output rather than judge it.
- `frontier` is not used by default; reserve it for a role whose mistakes are costlier than any of these.
- `fast` is not used by default, because none of these roles is a pure lookup, but it is the right choice for a narrow agent you add that only searches or reformats.

Set a tool's own model inside an agent's `model` block when one agent needs something other than its tier, or override a model on the command line or in a project-level copy of the agent when a task warrants it.
