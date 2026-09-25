# Agent Index

## Overview

Each Markdown file here is one Claude Code subagent, addressed by its filename and defined by the YAML frontmatter at the top of the file.
The agent files are generated from role sources in [`agent_sources/`](../agent_sources/README.md), along with each role's Codex, Cursor, Hermes, and CAI versions under `generated/`; edit the source, not the file, and run `just ci`.
This index is not generated and is maintained by hand.
`just install` links each of these files into `~/.claude/agents`, so an agent takes effect the next time a Claude Code session starts.
The files are linked one at a time rather than as a directory, because `~/.claude/agents` usually already holds agents of its own; a filename that is already taken there is reported as skipped and the local file keeps winning.
See [Agent Authoring Standards](../docs/docs_standards/agent_authoring.md) before adding or editing one.

These agents are templates in the sense the rest of this repository uses the word: opinionated starting points to fork and adapt.
Each one preloads the skills it needs from [`skills/`](../skills/README.md) rather than restating them, so the skill is the single place a rule is written.
Where a role's rules depend on what it is handed, such as the language of a test or the type of a document, the agent preloads only what always applies and loads the rest on match.
A project can override any agent by putting a file with the same name in its own `.claude/agents/` directory.

## Agents

- [`coder`](coder.md) - implements one scoped change end to end, with tests, and proves it against the repository's checks.
  Model `opus`; preloads `senior-developer`, `go-developer`, and `just-ci`; inherits every tool.
- [`reviewer`](reviewer.md) - performs adversarial review of a change in any language without editing anything, and runs the repository's checks as part of the review.
  Model `opus`; preloads `senior-developer` and `code-review-precision`; read-only tools plus the shell for lint and tests.
- [`reviewer-go`](reviewer-go.md) - performs the same review for Go, against modern Go practice and its concurrency and security risks.
  Model `opus`; preloads `senior-go-dev-reviewer` and `code-review-precision`; the same read-only tools.
  Both reviewers share the color `red`, because the color names the role and the suffix names the scope.
- [`test-runner`](test-runner.md) - runs the tests, diagnoses each failure down to a root cause, and writes or repairs tests when the task calls for it.
  Model `sonnet`; preloads `senior-developer` and `just-ci`, and loads the language's test skill on match.
- [`researcher`](researcher.md) - gathers facts from the repository and the web and reports them with exact references, without making changes.
  Model `sonnet`; no preloaded skills; read-only tools plus web fetch and search.
- [`planner`](planner.md) - turns a task into a detailed, test-gated execution plan as a Markdown checklist.
  Model `opus`; preloads `detailed-execution-planner`; read-only tools plus write access for the plan file.
- [`spec-author`](spec-author.md) - writes and revises requirements and technical specifications to the repository's standards, then lints them.
  Model `sonnet`; preloads `spec-authoring`, `requirements-authoring`, and `markdown-writer`.
- [`feature-author`](feature-author.md) - writes and revises Gherkin feature files that trace to requirements and specifications, then lints them.
  Model `sonnet`; preloads `feature-files-authoring` and `markdown-writer`.
- [`docs-writer`](docs-writer.md) - writes, revises, and audits Markdown documentation against the repository's own conventions and leaves it lint clean.
  Model `sonnet`; preloads `markdown-writer`, and loads the skill for the document type, or `code-review-precision` for an audit, on match.

## Model Selection

Each agent names a model alias rather than a dated model identifier, so it tracks the current release of that tier without an edit here.

- `opus` goes to the roles where judgment is the product: implementing against a specification, either kind of adversarial review, and planning.
  A missed defect or a wrong plan costs more than the difference in price.
- `sonnet` goes to the roles that are bounded by written conventions and a lint gate: research, test running, and the three authoring roles.
  Those agents follow rules the skills state and the repository's checks enforce, so the mid tier is enough and runs faster.
  Test running sits here rather than with `opus` because a test either passed or it did not, and the agent is told to report the real output rather than judge it.
- `haiku` is not used by default, because none of these roles is a pure lookup, but it is the right choice for a narrow agent you add that only searches or reformats.

Override a model on the command line or in a project-level copy of the agent when a task warrants it.
