# CI Scripts

## Overview

These are the validation helpers that [`justfile`](../justfile) recipes and CI call.
They are Python 3 standard library only, so they run without a virtual environment or any installed package.
Only [Python Lint](#python-lint) needs third-party tools, and those check the code rather than run it.

## Scripts

- [`generate_agents.py`](generate_agents.py) - generates every tool's agent files from the sources in `agent_sources/` into `generated/`, rebuilding the whole tree on each run and leaving it untouched when any source is invalid.
  It is the same code `just ci` and both installers run, and it imports three modules beside it:
  [`agent_front_matter.py`](agent_front_matter.py) parses the documented YAML subset sources use, so no YAML library is needed; [`agent_source.py`](agent_source.py) validates each source into an agent; and [`agent_render.py`](agent_render.py) writes an agent in each tool's format.
  See [Shared Agent Templates](../docs/specs/shared-agent-templates.md) for the source format and each tool's output.
- [`validate_skills.py`](validate_skills.py) - checks that every skill directory has a `SKILL.md` with well-formed frontmatter, a `name` matching its directory, valid boolean flags, an H1 body opening, no HTML comments outside fenced code blocks, and a complete `agents/openai.yaml` when one is present.
  Field names and length limits follow the [Agent Skills specification](https://agentskills.io/specification), and the specification's advisory size guidance of 500 lines and roughly 5000 tokens is reported as a warning rather than an error.
  Unrecognized frontmatter keys are warnings, because agent tools add fields over time.
- [`validate_agents.py`](validate_agents.py) - checks that every generated Claude Code agent under `generated/claude/agents/` has well-formed frontmatter, a `name` matching its filename, a `model`, `color`, `permissionMode`, `memory`, `isolation`, `maxTurns`, `effort`, and `background` that Claude Code accepts, tool lists without empty entries, preloaded `skills` that exist under `skills/`, an H1 body opening with instructions beneath it, no HTML comments, and an entry in the agent index.
  The index is `agent_sources/README.md`, passed with `--index`.
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
- [`python_quality_gate.py`](python_quality_gate.py) - fails when Git tracks a Python file outside `.ci_scripts/` and `scripts/`, the roots `just lint-python` checks, so no Python file escapes the lint gates.

## Tests

Each script and module has an offline unit test beside it, named `test_<script>.py`, using only `unittest`.
Run them with `just test-python`, which first runs the Python quality gate and compiles every Python file, then runs every `test_*.py` in this directory except the PowerShell installer tests.

The installer tests are split by topic, with shared fixtures in a support module:
`test_install_hermes.py`, `test_install_settings.py`, `test_install_links.py`, and `test_install_cai.py` use [`install_test_support.py`](install_test_support.py), and the `test_install_powershell_*.py` files use [`powershell_test_support.py`](powershell_test_support.py).
The generator tests share [`agent_test_support.py`](agent_test_support.py).

Installer regression tests cover original settings preservation, timestamped backups, repeated runs, and dry runs using temporary homes rather than the real user configuration.
Hermes tests use an offline CLI double to cover profile selection, external-directory registration, read/write failures, and preservation of local skills and identity.
They also cover personality ownership: adding, updating an owned personality, refusing a foreign or edited one without `--force`, and reporting one whose role was removed.
Generated-agent tests cover generation at install time, per-file links for Claude Code, Codex, and Cursor, their skip switches, dry runs, installs without Python, relinking the older `agents/` layout, whole-directory migration, and on PowerShell, symbolic links first and the refresh of a stale installed file.
The Bash tests require Unix Bash; the PowerShell tests require PowerShell 7 (`pwsh`) and report a skip when that runtime is unavailable.
`just test-powershell` runs them with a local `pwsh` and is part of `just ci`; without `pwsh` it prints a notice and skips.
`just test-powershell-container` runs them in the pinned PowerShell image from [`powershell.Containerfile`](powershell.Containerfile), using `podman` or `docker`, so a Linux or macOS machine without `pwsh` can still run them.
GitHub CI runs them on a Windows runner, which also covers the junction-migration test; GitLab CI runs them in the Linux PowerShell image.
The junction-migration test only runs on Windows, since junctions do not exist elsewhere; it warns and skips itself on every other system, including inside the container.

## Python Lint

`just lint-python` checks every Python file under `.ci_scripts/` and `scripts/`, and fails if any of these fails:

- `flake8`, configured by [`.flake8`](../.flake8), for style, with lines up to 120 characters.
- `pylint`, configured by [`.pylintrc`](../.pylintrc), with every check enabled except the few listed there; test files are exempt, since `flake8` covers them.
- `xenon`, which fails any function or method whose cyclomatic complexity ranks worse than C.
- `radon`, which fails any file whose maintainability index ranks C, below 10; a long, dense file fails even when each function is simple, so split it.
- `vulture`, which fails on dead code it is at least 80 percent sure of.
- `bandit`, configured by [`bandit.yaml`](../bandit.yaml), for security issues.

`just venv` installs the tools from [`requirements-lint.txt`](requirements-lint.txt) into `.venv`, which the recipe uses when present; `just setup` runs it.
The thresholds and tools follow CAI's Python gates.

## Conventions

Keep these scripts standard library only, so that the generator and validators run anywhere Python 3 does, including inside the installers.
Third-party packages belong only in `requirements-lint.txt`, and a check that needs one belongs in a separate recipe that states its own prerequisite.
Do not modify `.flake8`, `.pylintrc`, or `bandit.yaml`, and do not add lint suppressions, to make a check pass.
