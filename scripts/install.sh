#!/usr/bin/env bash
# Link this repository's skills into the agent tools that read them.
#
# It also links each file in agents/ into ~/.claude/agents, the directory Claude
# Code reads user-level subagent definitions from, and links the global
# AGENTS.md into the tools that document a global
# instruction file of their own, installs the Claude Code and Cursor status
# line scripts and points each tool's settings at its script, and turns off
# agent commit and PR attribution in every tool that supports the setting.
# The last two steps can be skipped with --no-statusline and --no-attribution.
#
# Two link styles are needed for the skills because the tools disagree about
# what a skills directory is:
#   - directory targets get one symlink pointing at skills/ as a whole.
#   - per-skill targets get one symlink per skill directory inside their own
#     skills directory, so tool-managed siblings are left in place.
#
# The agents are linked one file at a time for the same reason a per-skill
# target is: ~/.claude/agents is usually a real directory that already holds
# agents Claude Code or the user put there, and a link_one on the directory
# itself would refuse to touch it and install nothing. Linking file by file
# cannot clean up after itself, so anything else found in that directory,
# including a link left dangling by a renamed agent, is reported rather than
# removed.
#
# Existing paths are never replaced unless --force is given, and a symlink that
# already points at the right place is reported as already installed.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="${repo_root}/skills"
agents_dir="${repo_root}/agents"
agents_file="${repo_root}/AGENTS.md"
claude_statusline_source="${repo_root}/claude/statusline-command.sh"
claude_statusline_link="${HOME}/.claude/statusline-command.sh"
claude_settings="${HOME}/.claude/settings.json"
claude_statusline_command="sh ~/.claude/statusline-command.sh"
cursor_statusline_source="${repo_root}/cursor/statusline-command.sh"
cursor_statusline_link="${HOME}/.cursor/statusline-command.sh"
cursor_settings="${HOME}/.cursor/cli-config.json"
cursor_statusline_command="${HOME}/.cursor/statusline-command.sh"

dry_run=0
force=0
no_statusline=0
no_attribution=0

# Targets that receive a single symlink to the whole skills/ directory.
directory_targets=(
    "${HOME}/.claude/skills"
    "${HOME}/.cursor/skills"
    "${HOME}/.gemini/config/skills"
    "${HOME}/.copilot/skills"
)

# Targets that receive one symlink per agent file. Only Claude Code reads this
# file format today, so only its agents directory is linked.
per_agent_targets=(
    "${HOME}/.claude/agents"
)

# Targets that receive one symlink per skill directory.
per_skill_targets=(
    "${HOME}/.codex/skills"
    "${HOME}/.grok/skills"
)

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

usage() {
    cat <<'USAGE'
Usage: install.sh [--dry-run] [--force] [--no-statusline]
                  [--no-attribution] [--help]

  --dry-run         Print the changes that would be made and change nothing.
  --force           Replace an existing symlink that points somewhere else.
  --no-statusline   Skip installing and configuring the Claude Code and Cursor status lines.
  --no-attribution  Skip turning off agent commit and PR attribution.
  --help            Show this message.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry_run=1 ;;
        --force) force=1 ;;
        --no-statusline) no_statusline=1 ;;
        --no-attribution) no_attribution=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "error: unknown argument '$1'" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

run() {
    if [ "$dry_run" -eq 1 ]; then
        echo "  would run: $*"
    else
        "$@"
    fi
}

# report_extra_agents <source_dir> <target_dir>
# Report entries in the target that this repository did not just link, and
# remove nothing. A leftover from a renamed agent and an agent the user added
# deliberately look identical from here, so the choice is theirs to make.
report_extra_agents() {
    local source_dir="$1" target_dir="$2" entry name resolved
    local -a stale=() unmanaged=()

    [ -d "$target_dir" ] || return 0
    for entry in "$target_dir"/*.md; do
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

# configure_statusline_settings <settings_path> <command>
# Point a tool's settings file at its status line script, backing up first.
configure_statusline_settings() {
    local settings_path="$1" command="$2"
    python3 -c '
import json
import shutil
import sys

path, command, dry_run = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
desired = {"type": "command", "command": command}

try:
    with open(path, encoding="utf-8") as handle:
        settings = json.load(handle)
except FileNotFoundError:
    settings = {}
except (OSError, ValueError) as error:
    print("  skip: cannot read %s (%s)" % (path, error))
    sys.exit(0)

if settings.get("statusLine") == desired:
    print("  ok: %s already points at the status line script" % path)
    sys.exit(0)

if dry_run:
    print("  would set statusLine in %s to: %s" % (path, command))
    sys.exit(0)

if settings:
    shutil.copy2(path, path + ".bak")
    print("  backed up: %s.bak" % path)
settings["statusLine"] = desired
with open(path, "w", encoding="utf-8") as handle:
    json.dump(settings, handle, indent=2)
    handle.write("\n")
print("  configured: statusLine in %s" % path)
' "$settings_path" "$command" "$dry_run"
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
        if [ "$force" -eq 0 ]; then
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

echo "Source: ${skills_dir}"

echo "Directory targets:"
for target in "${directory_targets[@]}"; do
    link_one "$skills_dir" "$target"
done

echo "Per-skill targets:"
for target in "${per_skill_targets[@]}"; do
    [ -d "$target" ] || run mkdir -p "$target"
    for skill_path in "$skills_dir"/*/; do
        skill_name="$(basename "$skill_path")"
        link_one "${skills_dir}/${skill_name}" "${target}/${skill_name}"
    done
done

echo "Claude agents:"
for target in "${per_agent_targets[@]}"; do
    [ -d "$target" ] || run mkdir -p "$target"
    for agent_path in "$agents_dir"/*.md; do
        agent_name="$(basename "$agent_path")"
        if [ "$agent_name" = "README.md" ]; then
            continue
        fi
        link_one "$agent_path" "${target}/${agent_name}"
    done
    report_extra_agents "$agents_dir" "$target"
done

echo "Global instruction file:"
for target in "${instruction_targets[@]}"; do
    link_one "$agents_file" "$target"
done

if [ "$no_statusline" -eq 1 ]; then
    echo "Status line: skipped (--no-statusline)."
else
    echo "Status line:"
    link_one "$claude_statusline_source" "$claude_statusline_link"
    configure_statusline_settings "$claude_settings" "$claude_statusline_command"
    link_one "$cursor_statusline_source" "$cursor_statusline_link"
    configure_statusline_settings "$cursor_settings" "$cursor_statusline_command"
fi

if [ "$no_attribution" -eq 1 ]; then
    echo "Commit attribution: skipped (--no-attribution)."
else
    echo "Commit attribution:"
    python3 - "$dry_run" <<'ATTRIBUTION_PY'
import json
import shutil
import sys
import tomllib
from pathlib import Path

dry_run = sys.argv[1] == "1"
home = Path.home()


def say(message):
    print("  " + message)


def backup(path):
    shutil.copy2(path, str(path) + ".bak")
    say("backed up: %s.bak" % path)


def merge(target, updates):
    """Recursively apply updates to target, returning True when it changed."""
    changed = False
    for key, value in updates.items():
        if isinstance(value, dict):
            branch = target.get(key)
            if not isinstance(branch, dict):
                branch = {}
                target[key] = branch
            changed = merge(branch, value) or changed
        elif target.get(key) != value:
            target[key] = value
            changed = True
    return changed


def configure_json(path, updates, label):
    if not path.parent.is_dir():
        say("skip: %s is not installed" % label)
        return
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as error:
        say("skip: cannot read %s (%s)" % (path, error))
        return
    if not isinstance(settings, dict):
        say("skip: %s is not a JSON object" % path)
        return

    probe = json.loads(json.dumps(settings))
    if not merge(probe, updates):
        say("ok: %s already disables attribution" % label)
        return
    if dry_run:
        say("would update: %s" % path)
        return
    if path.exists():
        backup(path)
    merge(settings, updates)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    say("configured: %s" % path)


def configure_codex_toml(path, key, value):
    """Set a top-level key in config.toml, keeping it above the first table."""
    if not path.parent.is_dir():
        say("skip: codex is not installed")
        return
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        if tomllib.loads(text).get(key) == value:
            say("ok: codex already disables attribution")
            return
    except tomllib.TOMLDecodeError as error:
        say("skip: cannot parse %s (%s)" % (path, error))
        return
    if dry_run:
        say("would set %s = \"%s\" in %s" % (key, value, path))
        return

    lines = text.splitlines()
    assignment = '%s = "%s"' % (key, value)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("["):
            lines.insert(index, assignment)
            break
        if stripped.split("=")[0].strip() == key:
            lines[index] = assignment
            break
    else:
        lines.append(assignment)

    updated = "\n".join(lines) + "\n"
    try:
        if tomllib.loads(updated).get(key) != value:
            raise tomllib.TOMLDecodeError("key did not take effect", updated, 0)
    except tomllib.TOMLDecodeError as error:
        say("skip: edit would corrupt %s (%s); left unchanged" % (path, error))
        return
    if path.exists():
        backup(path)
    path.write_text(updated, encoding="utf-8")
    say("configured: %s" % path)


# sessionUrl is a separate switch from commit and pr: it defaults to true and
# appends a claude.ai session link to commits and PR bodies, but only in web and
# Remote Control sessions, so an empty commit and pr pair does not cover it.
configure_json(
    home / ".claude" / "settings.json",
    {"attribution": {"commit": "", "pr": "", "sessionUrl": False}},
    "claude",
)
configure_codex_toml(home / ".codex" / "config.toml", "commit_attribution", "")
configure_json(
    home / ".cursor" / "cli-config.json",
    {"attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}},
    "cursor",
)
say("note: gemini and grok document no attribution setting; nothing to change")
ATTRIBUTION_PY
fi

if [ "$dry_run" -eq 1 ]; then
    echo "Dry run: nothing was changed."
fi
