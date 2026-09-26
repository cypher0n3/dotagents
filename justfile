# dotagents dev environment and scripting.
# Run `just` for a list of recipes. Requires: https://github.com/casey/just
# shellcheck disable=SC2148,SC1007
# (justfile: not a shell script; recipe bodies are run by just with set shell)

set shell := ["bash", "-euo", "pipefail", "-c"]

# Directory containing this justfile (repository root).
root_dir := justfile_directory()

# Show list of available recipes (same as just --list).
default:
    @just --list

# Install the tooling the checks below need.
setup: install-markdownlint
    @echo "Setup complete. Run: just ci"

# Local CI: everything that gates a merge in this repository. Agents are
# generated first, so every later check sees the current generated files.
ci: generate-agents docs-check validate-skills validate-agents validate-skills-spec test-python test-powershell lint-sh
    @:

# Generate every tool's agent files from agent_sources/ into generated/, which is not committed.
generate-agents:
    @python3 "{{ root_dir }}/.ci_scripts/generate_agents.py"

# All documentation checks: Markdown lint plus internal link validation.
docs-check: lint-md validate-doc-links
    @:

# Install markdownlint-cli2 custom rules into .markdownlint-rules (for lint-md).
install-markdownlint:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    RULES_DIR=".markdownlint-rules"
    REPO_DIR=".markdownlint-repo"
    REPO_URL="https://github.com/cypher0n3/docs-as-code-tools.git"
    command -v markdownlint-cli2 >/dev/null 2>&1 || {
        echo "Error: markdownlint-cli2 not found. Install it (npm i -g markdownlint-cli2) and retry."
        exit 1
    }
    command -v git >/dev/null 2>&1 || { echo "Error: git required."; exit 1; }
    if [ ! -d "$REPO_DIR" ]; then
        git clone --depth 1 "$REPO_URL" "$REPO_DIR"
    else
        git -C "$REPO_DIR" fetch origin main
        git -C "$REPO_DIR" merge --ff-only origin/main || true
    fi
    ln -sfn "$REPO_DIR/markdownlint-rules" "$RULES_DIR"
    echo "Custom markdownlint rules installed in $RULES_DIR."

# Lint Markdown and apply automatic fixes, or only check under CI. Pass paths or
# omit for the whole repo.
# The whole-repo run skips symlinked entries in skills/, such as locally linked
# system skills: their content is not ours, and --fix would rewrite the target.
# It also skips generated/, which holds uncommitted output of agent_sources/.
lint-md *PATHS:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    if [ ! -e ".markdownlint-rules" ]; then
        echo "Error: .markdownlint-rules missing. Run: just install-markdownlint"
        exit 1
    fi
    # Fix locally; under CI (the CI environment variable is set), only check.
    fix=(--fix)
    case "$(printf '%s' "${CI:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
        "" | 0 | false) ;;
        *) fix=() ;;
    esac
    if [ -z "{{ PATHS }}" ]; then
        excludes=()
        while IFS= read -r link; do
            excludes+=("!${link}/**" "!${link}")
        done < <(find skills -mindepth 1 -maxdepth 1 -type l | sort)
        # Generated agents are not committed; their sources in agent_sources/ are linted instead.
        excludes+=("!generated/**" "!.generated.*/**")
        markdownlint-cli2 "${fix[@]}" '**/*.md' "${excludes[@]}"
    else
        markdownlint-cli2 "${fix[@]}" {{ PATHS }}
    fi

# Validate skill frontmatter, naming, and agent manifests.
validate-skills:
    @python3 "{{ root_dir }}/.ci_scripts/validate_skills.py" "{{ root_dir }}/skills"

# Validate the generated Claude Code agents, their preloaded skills, and the agent index.
validate-agents: generate-agents
    @python3 "{{ root_dir }}/.ci_scripts/validate_agents.py" "{{ root_dir }}/generated/claude/agents" "{{ root_dir }}/skills" --index "{{ root_dir }}/agent_sources/README.md"

# Validate skills with the Agent Skills reference validator (skills-ref). Skipped locally, and an error under CI, when it is absent.
validate-skills-spec:
    @python3 "{{ root_dir }}/.ci_scripts/validate_skills_spec.py" "{{ root_dir }}/skills"

# Validate relative Markdown links and heading anchors across the repository.
validate-doc-links:
    @python3 "{{ root_dir }}/.ci_scripts/validate_doc_links.py" "{{ root_dir }}"

# Run the offline Python unit tests for the CI helper scripts, except the PowerShell installer tests (see test-powershell).
test-python:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}/.ci_scripts"
    modules=()
    for test in test_*.py; do
        [ "$test" = test_install_powershell.py ] || modules+=("${test%.py}")
    done
    python3 -m unittest "${modules[@]}"

# Run the PowerShell installer tests with the local pwsh. Skipped with a notice when pwsh is absent.
test-powershell:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    if ! command -v pwsh >/dev/null 2>&1; then
        echo "pwsh not installed; skipping PowerShell installer tests."
        echo "Run: just test-powershell-container"
        exit 0
    fi
    python=$(command -v python3 || command -v python)
    exec "$python" .ci_scripts/test_install_powershell.py -v

# Run the PowerShell installer tests in a PowerShell container (podman, then docker), for machines without pwsh.
test-powershell-container:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    engine=""
    for candidate in podman docker; do
        if command -v "$candidate" >/dev/null 2>&1; then
            engine="$candidate"
            break
        fi
    done
    if [ -z "$engine" ]; then
        echo "Error: install podman or docker to run the PowerShell tests in a container." >&2
        exit 1
    fi
    image="dotagents-pwsh-tests:7.5"
    echo "Running the PowerShell tests in ${image} with ${engine}."
    "$engine" build --quiet --file .ci_scripts/powershell.Containerfile --tag "$image" .ci_scripts
    exec "$engine" run --rm \
        --volume "{{ root_dir }}:/repo:ro,z" \
        --env PYTHONDONTWRITEBYTECODE=1 \
        --env POWERSHELL_TELEMETRY_OPTOUT=1 \
        "$image" python3 .ci_scripts/test_install_powershell.py -v

# Lint the repository's shell scripts (shellcheck). Skipped with a notice when shellcheck is absent.
lint-sh:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    if ! command -v shellcheck >/dev/null 2>&1; then
        echo "shellcheck not installed; skipping shell lint."
        exit 0
    fi
    shellcheck scripts/*.sh claude/*.sh cursor/*.sh

# Generate the agents, link them, the skills, and the global AGENTS.md into each tool, and register Hermes skills and personalities.
install *ARGS:
    @bash "{{ root_dir }}/scripts/install.sh" {{ ARGS }}

# Show what `just install` would link, without changing anything.
install-dry-run:
    @bash "{{ root_dir }}/scripts/install.sh" --dry-run

# Remove locally installed lint tooling and caches.
clean:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    rm -rf .markdownlint-repo .markdownlint-rules .ci_scripts/__pycache__ generated
    echo "Removed local lint tooling and caches."
