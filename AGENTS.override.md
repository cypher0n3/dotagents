# Agent Instructions for This Repository

## Required Reading

- Read [`meta.md`](./meta.md) and [`README.md`](./README.md) before making changes.
- Follow [`docs/docs_standards/skill_authoring.md`](./docs/docs_standards/skill_authoring.md) for anything under [`skills/`](./skills/README.md).
- Follow [`docs/docs_standards/agent_authoring.md`](./docs/docs_standards/agent_authoring.md) for anything under [`agent_sources/`](./agent_sources/README.md).
- Follow [`docs/docs_standards/markdown_conventions.md`](./docs/docs_standards/markdown_conventions.md) for any Markdown.

## Rules

- Renaming a skill directory is a breaking change; update every reference, including [`skills/README.md`](./skills/README.md).
- Add a new skill to the correct category in [`skills/README.md`](./skills/README.md) in the same change that creates it.
- Renaming an agent is likewise a breaking change; add a new agent to [`agent_sources/README.md`](./agent_sources/README.md) in the same change that creates it, and do not restate a skill's rules inside an agent that preloads it.
- Each agent is written only in `agent_sources/<name>.md`; `generated/` is rebuilt by `just ci` and `just install`, is never committed, and must not be edited.
- Do not modify [`.markdownlint.yml`](./.markdownlint.yml), [`.markdownlint-cli2.jsonc`](./.markdownlint-cli2.jsonc), [`.flake8`](./.flake8), [`.pylintrc`](./.pylintrc), or [`bandit.yaml`](./bandit.yaml), and do not add lint suppressions to make a check pass.
- Keep [`.ci_scripts/`](./.ci_scripts/README.md) and `scripts/` Python standard library only, with an offline unit test beside each `.ci_scripts/` script; third-party lint tools belong only in `.ci_scripts/requirements-lint.txt`.
- Put Python only under `.ci_scripts/` or `scripts/`, where `just lint-python` checks it; split a file rather than weaken a lint threshold.
- Keep [`.gitlab-ci.yml`](./.gitlab-ci.yml) and [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) in sync.
- Do not run [`scripts/install.sh`](./scripts/install.sh) without direction; it changes symlinks in the user's home directory.

## Validation

- All changes must pass `just ci`.
