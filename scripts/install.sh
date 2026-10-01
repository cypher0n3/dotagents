#!/usr/bin/env bash
# Link this repository's skills into the agent tools that read them.
#
# It also generates the agents from agent_sources/ into generated/ with
# .ci_scripts/generate_agents.py, the same code `just ci` runs, and links each
# generated Claude Code agent into ~/.claude/agents, the directory Claude Code
# reads user-level subagent definitions from. It links the global
# AGENTS.md into the tools that document a global
# instruction file of their own, installs the Claude Code and Cursor status
# line scripts and points each tool's settings at its script, and turns off
# agent commit and PR attribution in every tool that supports the setting;
# scripts/install_settings.py makes those settings changes.
# The last two steps can be skipped with --no-statusline and --no-attribution.
# Existing Hermes setups scan skills/ via skills.external_dirs; --no-hermes
# skips registration without replacing Hermes-owned skills or identity.
# Pi discovers skills from ~/.pi/agent/skills/ and reads ~/.pi/agent/AGENTS.md
# as a user-level instruction file; --no-pi skips both Pi steps.
#
# The generated Codex and Cursor agents are installed the same way as the
# Claude agents: one symlink per file in generated/codex/agents and
# generated/cursor/agents, into ~/.codex/agents and ~/.cursor/agents, whether or
# not the tool is installed, like the skill links. Without python3 the agent
# steps are skipped and everything else is still installed. Hermes has no
# agent files, so each generated personality is set in its config through the
# hermes CLI. A personality this installer did not set, or one changed since it
# did, is replaced only with --force; ownership is recorded in
# ${XDG_STATE_HOME:-~/.local/state}/dotagents/install-state.json.
#
# CAI reads ~/.agents itself: AGENTS.md as global instructions, skills/, and
# agent_sources/. A clone at ~/.agents needs nothing. For a clone anywhere else,
# when CAI's configuration directory exists, the installer links AGENTS.md and
# each skill into ~/.agents one at a time, and agent_sources/ as a whole, so an
# agent added to the clone appears without reinstalling and a model CAI saves
# with /model is written into the clone. AGENTS.override.md holds this
# repository's own rules and is never linked. --no-cai skips the step.
#
# Skills are linked one directory at a time into a real skills directory that
# each tool owns. A tool can write its own skills next to ours (Claude Code
# syncs vendored ones into ~/.claude/skills), and a symlink to skills/ as a
# whole would land that content in this repository. An older install that
# linked skills/ as a whole is migrated to a real directory. A skills/ entry
# without a SKILL.md is not a skill and is never linked; it is reported, since
# it is usually content a tool wrote through that older link. Links to skills
# that no longer exist are reported rather than removed.
#
# The agents are linked one file at a time for the same reason:
# ~/.claude/agents is usually a real directory that already holds agents
# Claude Code or the user put there, and a link_one on the directory
# itself would refuse to touch it and install nothing. Linking file by file
# cannot clean up after itself, so anything else found in that directory,
# including a link left dangling by a renamed agent, is reported rather than
# removed. An older install that linked agents/ as a whole is migrated to a real
# directory the same way skills are.
#
# Existing paths are never replaced unless --force is given, and a symlink that
# already points at the right place is reported as already installed. A
# symlink that points elsewhere inside this repository, such as an agent
# linked from the agents/ directory of an older layout, is ours and is relinked.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="${repo_root}/skills"
agents_file="${repo_root}/AGENTS.md"
generated_dir="${repo_root}/generated"
agents_dir="${generated_dir}/claude/agents"
agent_sources_dir="${repo_root}/agent_sources"
generator="${repo_root}/.ci_scripts/generate_agents.py"
claude_statusline_source="${repo_root}/claude/statusline-command.sh"
claude_statusline_link="${HOME}/.claude/statusline-command.sh"
claude_statusline_command="sh ~/.claude/statusline-command.sh"
cursor_statusline_source="${repo_root}/cursor/statusline-command.sh"
cursor_statusline_link="${HOME}/.cursor/statusline-command.sh"
cursor_statusline_command="${HOME}/.cursor/statusline-command.sh"

dry_run=0
force=0
no_statusline=0
no_attribution=0
no_hermes=0
no_codex_agents=0
no_cursor_agents=0
no_hermes_personalities=0
no_cai=0
no_pi=0

# Targets that receive one symlink per agent file. Only Claude Code reads this
# file format today, so only its agents directory is linked.
per_agent_targets=(
    "${HOME}/.claude/agents"
)

# Targets that receive one symlink per skill directory.
per_skill_targets=(
    "${HOME}/.claude/skills"
    "${HOME}/.cursor/skills"
    "${HOME}/.gemini/config/skills"
    "${HOME}/.copilot/skills"
    "${HOME}/.codex/skills"
    "${HOME}/.grok/skills"
)
# Pi targets are conditionally prepended below when --no-pi is not passed.
per_skill_pi_target="${HOME}/.pi/agent/skills"

# Targets that receive a symlink to the global AGENTS.md instruction file.
# Each entry is the path that tool reads for user-level instructions. The Gemini
# entry uses that tool's own filename, which is what it reads by default.
instruction_targets=(
    "${HOME}/.claude/AGENTS.md"
    "${HOME}/.codex/AGENTS.md"
    "${HOME}/.cursor/rules/AGENTS.md"
    "${HOME}/.gemini/GEMINI.md"
    "${HOME}/.grok/AGENTS.md"
)
# Pi targets are conditionally prepended below when --no-pi is not passed.
instruction_pi_target="${HOME}/.pi/agent/AGENTS.md"

usage() {
    cat <<'USAGE'
Usage: install.sh [--dry-run] [--force] [--no-statusline]
                  [--no-attribution] [--no-hermes] [--no-codex-agents]
                  [--no-cursor-agents] [--no-hermes-personalities] [--no-cai]
                  [--no-pi] [--help]

  --dry-run                  Print the changes that would be made and change nothing.
  --force                    Replace an existing symlink that points somewhere else, or a
                             Hermes personality this installer does not own.
  --no-statusline            Skip installing and configuring the Claude Code and Cursor status lines.
  --no-attribution           Skip turning off agent commit and PR attribution.
  --no-hermes                Skip both Hermes steps: skill registration and personalities.
  --no-codex-agents          Skip linking the generated Codex agents.
  --no-cursor-agents         Skip linking the generated Cursor agents.
  --no-hermes-personalities  Skip setting the generated Hermes personalities.
  --no-cai                   Skip exposing a clone outside ~/.agents to CAI.
  --no-pi                    Skip installing links for Pi (pi.dev).
  --help                     Show this message.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry_run=1 ;;
        --force) force=1 ;;
        --no-statusline) no_statusline=1 ;;
        --no-attribution) no_attribution=1 ;;
        --no-hermes) no_hermes=1 ;;
        --no-codex-agents) no_codex_agents=1 ;;
        --no-cursor-agents) no_cursor_agents=1 ;;
        --no-hermes-personalities) no_hermes_personalities=1 ;;
        --no-cai) no_cai=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        --no-pi) no_pi=1 ;;
        *)
            echo "error: unknown argument '$1'" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

# Conditionally prepend Pi targets so the existing loops pick them up.
if [ "$no_pi" -eq 0 ]; then
    per_skill_targets=("${per_skill_pi_target}" "${per_skill_targets[@]}")
    instruction_targets=("${instruction_pi_target}" "${instruction_targets[@]}")
fi

run() {
    if [ "$dry_run" -eq 1 ]; then
        echo "  would run: $*"
    else
        "$@"
    fi
}

# report_extra_agents <source_dir> <target_dir> [extension]
# Report entries in the target that this repository did not just link, and
# remove nothing. A leftover from a renamed agent and an agent the user added
# deliberately look identical from here, so the choice is theirs to make.
report_extra_agents() {
    local source_dir="$1" target_dir="$2" extension="${3:-md}" entry name resolved
    local -a stale=() unmanaged=()

    [ -d "$target_dir" ] || return 0
    for entry in "$target_dir"/*."$extension"; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        name="$(basename "$entry")"
        if [ -L "$entry" ] && [ ! -e "$entry" ]; then
            stale+=("${name} -> $(readlink "$entry")")
            continue
        fi
        resolved="$(readlink -f "$entry" 2>/dev/null || true)"
        case "$resolved" in
            "$source_dir"/*) continue ;;
        esac
        unmanaged+=("$name")
    done

    if [ "${#stale[@]}" -gt 0 ]; then
        echo "  note: broken link(s) in ${target_dir}, left in place for you to remove:" >&2
        for entry in "${stale[@]}"; do
            echo "    stale: ${entry}" >&2
        done
    fi
    if [ "${#unmanaged[@]}" -gt 0 ]; then
        echo "  note: agent(s) in ${target_dir} that this repository does not provide, left as they are:" >&2
        for entry in "${unmanaged[@]}"; do
            echo "    local: ${entry}" >&2
        done
    fi
}

# link_one <source> <link_path>
link_one() {
    local source="$1" link_path="$2" existing

    if [ "$(readlink -f "$link_path" 2>/dev/null || true)" = "$(readlink -f "$source")" ]; then
        echo "  ok: ${link_path} (already linked)"
        return 0
    fi

    if [ -e "$link_path" ] || [ -L "$link_path" ]; then
        if [ ! -L "$link_path" ]; then
            echo "  skip: ${link_path} exists and is not a symlink" >&2
            return 0
        fi
        existing="$(readlink "$link_path")"
        case "$existing" in
            "$repo_root"/*)
                echo "  relink: ${link_path} pointed at ${existing} in this repository"
                run rm -f "$link_path"
                existing=""
                ;;
        esac
        if [ -n "$existing" ] && [ "$force" -eq 0 ]; then
            echo "  skip: ${link_path} points at ${existing} (use --force to replace)" >&2
            return 0
        fi
        run rm -f "$link_path"
    fi

    [ -d "$(dirname "$link_path")" ] || run mkdir -p "$(dirname "$link_path")"
    run ln -sfn "$source" "$link_path"
    if [ "$dry_run" -eq 0 ]; then
        echo "  linked: ${link_path} -> ${source}"
    fi
}

# prepare_real_dir <target_dir> <source_dir>
# Make the target a real directory. A symlink to the matching source directory
# in this repository (skills/ or agents/) is the layout an older install
# created, so it is replaced without --force. A symlink anywhere else is the
# user's own and needs --force. Returns non-zero when the target must be left
# alone.
prepare_real_dir() {
    local target="$1" source="$2"

    if [ -L "$target" ]; then
        if [ "$(readlink -f "$target")" = "$(readlink -f "$source")" ]; then
            echo "  migrate: ${target} links the whole $(basename "$source") directory; replacing it with a real directory"
        elif case "$(readlink "$target")" in "$repo_root"/*) true ;; *) false ;; esac; then
            echo "  migrate: ${target} links $(readlink "$target") in this repository; replacing it with a real directory"
        elif [ "$force" -eq 1 ]; then
            echo "  migrate: ${target} points at $(readlink "$target"); replacing it with a real directory"
        else
            echo "  skip: ${target} points at $(readlink "$target") (use --force to replace)" >&2
            return 1
        fi
        run rm -f "$target"
    elif [ -e "$target" ] && [ ! -d "$target" ]; then
        echo "  skip: ${target} exists and is not a directory" >&2
        return 1
    fi
    [ -d "$target" ] || run mkdir -p "$target"
}

# report_stale_skills <target_dir>
# Report links in the target that point into skills/ at a skill that no longer
# exists, and remove nothing.
report_stale_skills() {
    local target_dir="$1" entry
    local -a stale=()

    [ -d "$target_dir" ] || return 0
    for entry in "$target_dir"/*; do
        if [ ! -L "$entry" ] || [ -e "$entry" ]; then
            continue
        fi
        case "$(readlink "$entry")" in
            "$skills_dir"/*) stale+=("$(basename "$entry") -> $(readlink "$entry")") ;;
        esac
    done

    if [ "${#stale[@]}" -gt 0 ]; then
        echo "  note: broken link(s) in ${target_dir}, left in place for you to remove:" >&2
        for entry in "${stale[@]}"; do
            echo "    stale: ${entry}" >&2
        done
    fi
}

# link_skills <target_dir>
link_skills() {
    local target="$1" skill_path skill_name

    prepare_real_dir "$target" "$skills_dir" || return 0
    if [ "$dry_run" -eq 1 ] && [ -L "$target" ]; then
        echo "  would link each skill into ${target}"
        return 0
    fi
    for skill_path in "$skills_dir"/*/; do
        [ -f "${skill_path}SKILL.md" ] || continue
        skill_name="$(basename "$skill_path")"
        link_one "${skills_dir}/${skill_name}" "${target}/${skill_name}"
    done
    report_stale_skills "$target"
}

# report_non_skill_entries
# Report directories in skills/ that have no SKILL.md, and remove nothing. A
# tool that wrote through a whole-directory link from an older install leaves
# its content here, and migrating the link does not move it back out.
report_non_skill_entries() {
    local entry
    local -a extra=()

    for entry in "$skills_dir"/*/; do
        [ -f "${entry}SKILL.md" ] || extra+=("$(basename "$entry")")
    done

    if [ "${#extra[@]}" -gt 0 ]; then
        echo "  note: non-skill director(ies) in ${skills_dir}, left in place for you to remove:" >&2
        for entry in "${extra[@]}"; do
            echo "    extra: ${entry}" >&2
        done
    fi
}

echo "Source: ${skills_dir}"

echo "Skill targets:"
for target in "${per_skill_targets[@]}"; do
    link_skills "$target"
done
report_non_skill_entries

# Generate the agents with the same code `just ci` runs. generated/ lives in
# this clone and is not installed anywhere by itself, so a dry run generates too.
agents_available=0
agents_skip=""
echo "Agent generation:"
if [ ! -d "$agent_sources_dir" ] || [ ! -f "$generator" ]; then
    agents_skip="no agent sources in ${agent_sources_dir}"
elif ! command -v python3 >/dev/null 2>&1; then
    agents_skip="python3 not found; install Python 3 to install the agents"
else
    python3 "$generator" --root "$repo_root" | while IFS= read -r line; do echo "  ${line}"; done
    agents_available=1
fi
[ -z "$agents_skip" ] || echo "  skip: ${agents_skip}"

# link_generated <label> <switch> <skipped> <source_dir> <target_dir> <extension>
# Link each generated file into a real directory the tool owns, one file at a
# time, and report what else is there.
link_generated() {
    local label="$1" switch="$2" skipped="$3" source_dir="$4" target="$5" extension="$6" path

    echo "${label}:"
    if [ -n "$switch" ] && [ "$skipped" -eq 1 ]; then
        echo "  skipped (${switch})."
        return 0
    fi
    if [ "$agents_available" -eq 0 ]; then
        echo "  skip: ${agents_skip}"
        return 0
    fi
    if ! compgen -G "${source_dir}/*.${extension}" >/dev/null; then
        echo "  skip: no generated files in ${source_dir}"
        report_extra_agents "$source_dir" "$target" "$extension"
        return 0
    fi
    prepare_real_dir "$target" "$source_dir" || return 0
    if [ "$dry_run" -eq 1 ] && [ -L "$target" ]; then
        echo "  would link each file into ${target}"
        return 0
    fi
    for path in "$source_dir"/*."$extension"; do
        link_one "$path" "${target}/$(basename "$path")"
    done
    report_extra_agents "$source_dir" "$target" "$extension"
}

for target in "${per_agent_targets[@]}"; do
    link_generated "Claude agents" "" 0 "$agents_dir" "$target" md
done
link_generated "Codex agents" --no-codex-agents "$no_codex_agents" \
    "${generated_dir}/codex/agents" "${HOME}/.codex/agents" toml
link_generated "Cursor agents" --no-cursor-agents "$no_cursor_agents" \
    "${generated_dir}/cursor/agents" "${HOME}/.cursor/agents" md

echo "Global instruction file:"
for target in "${instruction_targets[@]}"; do
    link_one "$agents_file" "$target"
done

# CAI discovers ~/.agents only, so a clone elsewhere is linked there; see the
# header. CAI's configuration directory follows CAI's own rule: a non-empty
# XDG_CONFIG_HOME, else ~/.config.
agents_home="${HOME}/.agents"
cai_config_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/cai"
echo "CAI:"
if [ "$no_cai" -eq 1 ]; then
    echo "  skipped (--no-cai)."
elif [ "$(readlink -f "$agents_home" 2>/dev/null || true)" = "$(readlink -f "$repo_root")" ]; then
    echo "  ok: CAI reads this clone at ${agents_home} directly"
elif [ ! -d "$cai_config_dir" ]; then
    echo "  skip: CAI configuration not found at ${cai_config_dir}"
elif { [ -e "$agents_home" ] || [ -L "$agents_home" ]; } && [ ! -d "$agents_home" ]; then
    echo "  skip: ${agents_home} exists and is not a directory" >&2
else
    link_one "$agents_file" "${agents_home}/AGENTS.md"
    link_skills "${agents_home}/skills"
    if [ -d "$agent_sources_dir" ]; then
        link_one "$agent_sources_dir" "${agents_home}/agent_sources"
    fi
fi

if [ "$no_statusline" -eq 1 ]; then
    echo "Status line: skipped (--no-statusline)."
else
    echo "Status line:"
    link_one "$claude_statusline_source" "$claude_statusline_link"
    link_one "$cursor_statusline_source" "$cursor_statusline_link"
fi

# Pin CLI calls to the selected Hermes home rather than its sticky profile.
hermes_home="${HERMES_HOME-}"
hermes_home="${hermes_home#"${hermes_home%%[![:space:]]*}"}"
hermes_home="${hermes_home%"${hermes_home##*[![:space:]]}"}"
hermes_home="${hermes_home:-${HOME}/.hermes}"
hermes_enabled=0
hermes_personalities_enabled=0
hermes_command="$(type -P hermes || true)"
hermes_skip=""
if [ "$no_hermes" -eq 1 ]; then
    hermes_skip="skipped (--no-hermes)."
elif [ ! -f "$hermes_home/config.yaml" ]; then
    hermes_skip="skip: Hermes config not found at $hermes_home/config.yaml"
elif [ -z "$hermes_command" ]; then
    hermes_skip="skip: hermes command not found on PATH"
else
    hermes_enabled=1
fi
echo "Hermes skills:"
[ -z "$hermes_skip" ] || echo "  ${hermes_skip}"
personalities_skip="skipped (--no-hermes-personalities)."
if [ -n "$hermes_skip" ]; then
    personalities_skip="$hermes_skip"
elif [ "$agents_available" -eq 0 ]; then
    personalities_skip="skip: ${agents_skip}"
fi
if [ "$hermes_enabled" -eq 1 ] && [ "$no_hermes_personalities" -eq 0 ] && [ "$agents_available" -eq 1 ]; then
    hermes_personalities_enabled=1
fi

if [ "$no_statusline" -eq 1 ] && [ "$no_attribution" -eq 1 ] && [ "$hermes_enabled" -eq 0 ]; then
    echo "Hermes personalities:"
    echo "  ${personalities_skip}"
    echo "Commit attribution: skipped (--no-attribution)."
else
    # Keep all settings mutations in one process so each file is backed up once.
    settings_args=(
        --claude-statusline-command="$claude_statusline_command"
        --cursor-statusline-command="$cursor_statusline_command"
        --hermes-home="$hermes_home"
        --hermes-command="$hermes_command"
        --skills-dir="$skills_dir"
        --personalities-dir="${generated_dir}/hermes/personalities"
        --personalities-skip="$personalities_skip"
    )
    [ "$dry_run" -eq 0 ] || settings_args+=(--dry-run)
    [ "$force" -eq 0 ] || settings_args+=(--force)
    [ "$no_statusline" -eq 0 ] || settings_args+=(--no-statusline)
    [ "$no_attribution" -eq 0 ] || settings_args+=(--no-attribution)
    [ "$hermes_enabled" -eq 0 ] || settings_args+=(--hermes-skills)
    [ "$hermes_personalities_enabled" -eq 0 ] || settings_args+=(--personalities)
    python3 "${repo_root}/scripts/install_settings.py" "${settings_args[@]}"
fi

if [ "$dry_run" -eq 1 ]; then
    echo "Dry run: nothing was changed."
fi
