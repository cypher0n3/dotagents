# dotagents dev environment and scripting.
# Run `just` for a list of recipes. Requires: https://github.com/casey/just
# shellcheck disable=SC2148,SC1007
# (justfile: not a shell script; recipe bodies are run by just with set shell)

set shell := ["bash", "-euo", "pipefail", "-c"]

# Directory containing this justfile (repository root).
root_dir := justfile_directory()

# Every directory holding tracked Python; .ci_scripts/python_quality_gate.py
# rejects Python anywhere else, so lint-python cannot miss a file.
python_roots := ".ci_scripts scripts"

# Show list of available recipes (same as just --list).
default:
    @just --list

# Install the tooling the checks below need.
setup: install-markdownlint venv
    @echo "Setup complete. Run: just ci"

# Local CI: everything that gates a merge in this repository. Agents are
# generated first, so every later check sees the current generated files.
ci: generate-agents docs-check validate-skills validate-agents validate-skills-spec lint-python test-python test-powershell lint-sh
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

# Create .venv and install the Python lint tools from .ci_scripts/requirements-lint.txt.
venv:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    python3 -m venv .venv
    python=.venv/bin/python
    [ -x "$python" ] || python=.venv/Scripts/python
    "$python" -m pip install --quiet --upgrade pip
    "$python" -m pip install --quiet -r .ci_scripts/requirements-lint.txt
    echo "Python lint tools installed in .venv."

# Lint every Python root: flake8 (style), pylint, xenon (per-function complexity),
# radon (per-file maintainability), vulture (dead code), and bandit (security).
# Uses .venv when present, else tools on PATH; run `just venv` to install them.
lint-python:
    #!/usr/bin/env bash
    set -uo pipefail
    cd "{{ root_dir }}"
    for bin in .venv/bin .venv/Scripts; do
        if [ -d "$bin" ]; then PATH="$PWD/$bin:$PATH"; fi
    done
    missing=()
    for tool in flake8 pylint xenon radon vulture bandit; do
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done
    if [ "${#missing[@]}" -gt 0 ]; then
        echo "Error: ${missing[*]} not found. Run: just venv" >&2
        exit 1
    fi
    read -r -a roots <<< "{{ python_roots }}"
    failed=()
    check() {
        local name=$1
        shift
        echo "Running ${name}..."
        "$@" || failed+=("$name")
    }
    # A file ranked C (maintainability index below 10) fails; radon lists only those.
    maintainability() {
        local low
        low=$(radon mi --min C "${roots[@]}")
        [ -z "$low" ] || { echo "$low"; return 1; }
    }
    check flake8 flake8 "${roots[@]}"
    check pylint pylint --rcfile=.pylintrc "${roots[@]}"
    check xenon xenon --max-absolute C "${roots[@]}"
    check "radon mi" maintainability
    check vulture vulture --min-confidence 80 "${roots[@]}"
    check bandit bandit --quiet --recursive --configfile bandit.yaml "${roots[@]}"
    if [ "${#failed[@]}" -gt 0 ]; then
        echo "Python lint failed: ${failed[*]}" >&2
        exit 1
    fi
    echo "Python lint passed."

# Check that every tracked Python file is linted, compile everything, and run the
# offline unit tests, except the PowerShell installer tests (see test-powershell).
test-python:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    python3 .ci_scripts/python_quality_gate.py
    read -r -a roots <<< "{{ python_roots }}"
    python3 -m compileall -q "${roots[@]}"
    cd .ci_scripts
    modules=()
    for test in test_*.py; do
        case "$test" in
            test_install_powershell_*) ;;
            *) modules+=("${test%.py}") ;;
        esac
    done
    python3 -m unittest "${modules[@]}"

# Run the PowerShell installer tests with the local pwsh. When pwsh is absent,
# print that the tests were not run and exit 0. That skip is not a pass.
# just test-powershell-container is the local check that actually runs them,
# and just test-powershell-readonly is the CI check: it fails when pwsh is missing.
test-powershell:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    if ! command -v pwsh >/dev/null 2>&1; then
        echo "pwsh not installed; PowerShell installer tests were not run."
        echo "This skip is not a pass. Run: just test-powershell-container"
        exit 0
    fi
    python=$(command -v python3 || command -v python)
    exec "$python" -m unittest discover --start-directory .ci_scripts --pattern 'test_install_powershell_*.py' -v

# Run the PowerShell installer tests in a PowerShell container (podman, then docker), for machines without pwsh.
# The installer writes generated/ into the clone, so the host checkout is mounted read-only at /src
# and copied to a writable /repo before the tests run. Those writes stay in the container.
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
        --volume "{{ root_dir }}:/src:ro,z" \
        --env PYTHONDONTWRITEBYTECODE=1 \
        --env POWERSHELL_TELEMETRY_OPTOUT=1 \
        "$image" \
        bash -c 'set -euo pipefail; cp -a /src/. /repo/; exec python3 -m unittest discover --start-directory .ci_scripts --pattern "test_install_powershell_*.py" -v'

# Run the PowerShell installer tests from a writable copy of a read-only source.
# pwsh is required. A missing pwsh fails the recipe, and so does a run that skips
# every test. CI calls this so a writable checkout cannot hide the read-only failure
# that test-powershell-container covers by mounting the source read-only and copying it.
test-powershell-readonly:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root_dir }}"
    if ! command -v pwsh >/dev/null 2>&1; then
        echo "Error: pwsh is required. Refusing to skip the PowerShell installer tests." >&2
        exit 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Error: python3 is required to run the PowerShell installer tests." >&2
        exit 1
    fi
    source_tree=$(mktemp -d)
    work_tree=$(mktemp -d)
    tester_home=$(mktemp -d)
    log=$(mktemp)
    cleanup() {
        chmod -R u+w "$source_tree" "$work_tree" "$tester_home" 2>/dev/null || true
        rm -rf "$source_tree" "$work_tree" "$tester_home" "$log"
    }
    trap cleanup EXIT
    # Root ignores mode bits. CI images run as root, so the tests drop to
    # nobody before a mode-bit lock counts as a read-only source.
    as_tester() {
        if [ "$(id -u)" -eq 0 ]; then
            command -v su >/dev/null 2>&1 || {
                echo "Error: root can write through mode bits; su is required to exercise the read-only source." >&2
                exit 1
            }
            su nobody -s /bin/bash -c "$1"
        else
            bash -c "$1"
        fi
    }
    cp -a . "$source_tree/src"
    chmod a+rx "$source_tree" "$work_tree"
    chmod -R a-w "$source_tree/src"
    mkdir -p "$work_tree/repo"
    cp -a "$source_tree/src/." "$work_tree/repo/"
    chmod -R a+rwX "$work_tree/repo"
    chmod a+rwx "$tester_home"
    if as_tester "touch '$source_tree/src/write-probe'" 2>/dev/null; then
        echo "Error: read-only source accepted a write, so the read-only case was not exercised." >&2
        exit 1
    fi
    if ! as_tester "touch '$work_tree/repo/write-probe' && rm -f '$work_tree/repo/write-probe'"; then
        echo "Error: writable copy rejected a write." >&2
        exit 1
    fi
    if ! as_tester "cd '$work_tree/repo' && export HOME='$tester_home' PYTHONDONTWRITEBYTECODE=1 POWERSHELL_TELEMETRY_OPTOUT=1 && python3 -m unittest discover --start-directory .ci_scripts --pattern 'test_install_powershell_*.py' -v" >"$log" 2>&1; then
        cat "$log" >&2
        exit 1
    fi
    cat "$log"
    ran=$(sed -n 's/^Ran \([0-9][0-9]*\) tests.*/\1/p' "$log" | tail -n 1)
    skipped=$(sed -n 's/^OK (skipped=\([0-9][0-9]*\)).*/\1/p' "$log" | tail -n 1)
    skipped=${skipped:-0}
    if [ -z "$ran" ] || [ "$ran" -eq 0 ] || [ "$skipped" -ge "$ran" ]; then
        echo "Error: PowerShell installer tests did not execute (ran=${ran:-0}, skipped=${skipped})." >&2
        exit 1
    fi
    if as_tester "touch '$source_tree/src/write-probe'" 2>/dev/null; then
        echo "Error: the read-only source accepted a write during the tests." >&2
        exit 1
    fi

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
    rm -rf .markdownlint-repo .markdownlint-rules .ci_scripts/__pycache__ scripts/__pycache__ generated
    echo "Removed local lint tooling and caches."
