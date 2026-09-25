# Agent Generator

## Overview

`agentgen` renders the role sources in [`agent_sources/`](../../agent_sources/README.md) into Claude Code, Codex, Cursor, Hermes, and CAI agent files, and writes `generated/manifest.yaml`.
It is a `uv` project with locked dependencies, and the installers never need it, because they consume the committed output.
[Shared Agent Templates](../../docs/specs/shared-agent-templates.md) specifies its behavior.

## Usage

Run it through the repository's recipes:

- `just generate-agents` - regenerate from the sources, or only check under CI.
- `just generate-agents-accept-source` - rewrite generated files that were edited by hand, such as after a merge conflict.
- `just test-agentgen` - run the generator's unit tests.

The recipes call `uv run --locked --project tools/agentgen agentgen generate --root .`, adding `--check` when the `CI` environment variable is set.

## Layout

- `src/agentgen/sources.py` - loads and validates target profiles and roles.
- `src/agentgen/render.py` - builds each target's fields, comments, and body, and verifies the result reads back as intended.
- `src/agentgen/yamlio.py` and `src/agentgen/tomlio.py` - strict YAML reading and deterministic YAML and TOML writing.
- `src/agentgen/manifest.py` - the generation manifest.
- `src/agentgen/publish.py` - hand-edit protection, check mode, and staged publication.
- `src/agentgen/cli.py` - the `agentgen generate` command.
- `tests/` - unit tests, including one that requires the committed output to match the sources.

## Dependencies

Change a dependency in `pyproject.toml`, run `uv lock` in this directory, and commit both files.
