# CI Scripts

## Overview

These are the validation helpers that [`justfile`](../justfile) recipes and CI call.
They are Python 3 standard library only, so they run without a virtual environment or any installed package.

## Scripts

- [`validate_skills.py`](validate_skills.py) - checks that every skill directory has a `SKILL.md` with well-formed frontmatter, a `name` matching its directory, valid boolean flags, an H1 body opening, no HTML comments outside fenced code blocks, and a complete `agents/openai.yaml` when one is present.
  Field names and length limits follow the [Agent Skills specification](https://agentskills.io/specification), and the specification's advisory size guidance of 500 lines and roughly 5000 tokens is reported as a warning rather than an error.
  Unrecognized frontmatter keys are warnings, because agent tools add fields over time.
- [`validate_agents.py`](validate_agents.py) - checks that every agent file under `agents/` has well-formed frontmatter, a `name` matching its filename, a `model`, `color`, `permissionMode`, `memory`, `isolation`, `maxTurns`, `effort`, and `background` that Claude Code accepts, tool lists without empty entries, preloaded `skills` that exist under `skills/`, an H1 body opening with instructions beneath it, no HTML comments, and an entry in the agent index.
  Field names and allowed values follow the [Claude Code subagent documentation](https://code.claude.com/docs/en/sub-agents), and unrecognized keys are warnings for the same reason as above.
  It imports its frontmatter and comment helpers from `validate_skills.py`, so the two stay in step.
- [`validate_skills_spec.py`](validate_skills_spec.py) - runs the Agent Skills reference validator from the `skills-ref` package on every skill, as an independent check of the specification.
  The PyPI release installs the validator as `agentskills` and the source tree as `skills-ref`; either works, and `agentskills` is preferred.
  The validator rejects every frontmatter field the specification does not define, so the client fields in `validate_skills.py`'s `CLIENT_KEYS` are accepted silently; every other problem it reports is an error, and so is output the script cannot parse.
  The script itself is dependency-free and calls the validator as a command.
  Install the validator with `uv tool install skills-ref==0.1.1` or `pipx install skills-ref==0.1.1`; 0.1.1 is the version CI pins.
  Without it, the check is skipped with a notice locally and is an error when the `CI` environment variable is set.
- [`validate_doc_links.py`](validate_doc_links.py) - checks that every relative Markdown link resolves on disk and that every heading anchor it carries exists in the target document.
  External links are not fetched.

## Tests

Each script has an offline unit test beside it, named `test_<script>.py`, using only `unittest`.
Run them with `just test-python`, which runs every `test_*.py` in this directory except the PowerShell installer tests.

Installer regression tests cover original settings preservation, timestamped backups, repeated runs, and dry runs using temporary homes rather than the real user configuration.
Hermes tests use an offline CLI double to cover profile selection, external-directory registration, read/write failures, and preservation of local skills and identity.
They also cover personality ownership: adding, updating an owned personality, refusing a foreign or edited one without `--force`, and reporting one whose role was removed.
Generated-agent tests cover per-file links for Codex, Cursor, and CAI, their skip switches, dry runs, whole-directory migration, and the PowerShell refresh of a stale installed file.
The Bash tests require Unix Bash; the PowerShell tests require PowerShell 7 (`pwsh`) and report a skip when that runtime is unavailable.
`just test-powershell` runs them with a local `pwsh` and is part of `just ci`; without `pwsh` it prints a notice and skips.
`just test-powershell-container` runs them in the pinned PowerShell image from [`powershell.Containerfile`](powershell.Containerfile), using `podman` or `docker`, so a Linux or macOS machine without `pwsh` can still run them.
GitHub CI runs them on a Windows runner, which also covers the junction-migration test; GitLab CI runs them in the Linux PowerShell image.
The junction-migration test only runs on Windows, since junctions do not exist elsewhere; it warns and skips itself on every other system, including inside the container.

## Conventions

Keep these scripts dependency-free, so that every check here runs with nothing installed but `just`, `python3`, and `markdownlint-cli2`.
A check that needs a third-party package belongs in a separate recipe that states its own prerequisite.
The agent generator is that case: it lives in [`tools/agentgen/`](../tools/agentgen/README.md) with its own locked dependencies, so `just ci` also needs [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for its `generate-agents` and `test-agentgen` recipes.
