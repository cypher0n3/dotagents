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
# Existing Hermes setups scan skills/ via skills.external_dirs; --no-hermes
# skips registration without replacing Hermes-owned skills or identity.
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
# already points at the right place is reported as already installed.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="${repo_root}/skills"
agents_dir="${repo_root}/agents"
agents_file="${repo_root}/AGENTS.md"
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
                  [--no-attribution] [--no-hermes] [--help]

  --dry-run         Print the changes that would be made and change nothing.
  --force           Replace an existing symlink that points somewhere else.
  --no-statusline   Skip installing and configuring the Claude Code and Cursor status lines.
  --no-attribution  Skip turning off agent commit and PR attribution.
  --no-hermes       Skip registering this repository as a Hermes skill directory.
  --help            Show this message.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry_run=1 ;;
        --force) force=1 ;;
        --no-statusline) no_statusline=1 ;;
        --no-attribution) no_attribution=1 ;;
        --no-hermes) no_hermes=1 ;;
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

echo "Claude agents:"
for target in "${per_agent_targets[@]}"; do
    prepare_real_dir "$target" "$agents_dir" || continue
    if [ "$dry_run" -eq 1 ] && [ -L "$target" ]; then
        echo "  would link each agent into ${target}"
        continue
    fi
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
    link_one "$cursor_statusline_source" "$cursor_statusline_link"
fi

# Pin CLI calls to the selected Hermes home rather than its sticky profile.
hermes_home="${HERMES_HOME-}"
hermes_home="${hermes_home#"${hermes_home%%[![:space:]]*}"}"
hermes_home="${hermes_home%"${hermes_home##*[![:space:]]}"}"
hermes_home="${hermes_home:-${HOME}/.hermes}"
hermes_enabled=0
hermes_command="$(type -P hermes || true)"
echo "Hermes skills:"
if [ "$no_hermes" -eq 1 ]; then
    echo "  skipped (--no-hermes)."
elif [ ! -f "$hermes_home/config.yaml" ]; then
    echo "  skip: Hermes config not found at $hermes_home/config.yaml"
elif [ -z "$hermes_command" ]; then
    echo "  skip: hermes command not found on PATH"
else
    hermes_enabled=1
fi

if [ "$no_statusline" -eq 1 ] && [ "$no_attribution" -eq 1 ] && [ "$hermes_enabled" -eq 0 ]; then
    echo "Commit attribution: skipped (--no-attribution)."
else
# Keep all settings mutations in one process so each file is backed up once.
python3 - "$dry_run" "$no_statusline" "$no_attribution" \
    "$claude_statusline_command" "$cursor_statusline_command" \
    "$hermes_enabled" "$hermes_home" "$hermes_command" "$skills_dir" <<'SETTINGS_PY'
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

dry_run, no_statusline, no_attribution = (value == "1" for value in sys.argv[1:4])
claude_command, cursor_command = sys.argv[4:6]
hermes_enabled = sys.argv[6] == "1"
hermes_home, hermes_command, skills_dir = sys.argv[7:10]
home = Path.home()
# Match Cursor CLI precedence; ignore empty/whitespace-only overrides.
custom_config = os.environ.get("CURSOR_CONFIG_DIR", "")
xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
if custom_config.strip():
    cursor_config_dir = Path(custom_config)
elif xdg_config.strip():
    cursor_config_dir = Path(xdg_config) / "cursor"
else:
    cursor_config_dir = home / ".cursor"
cursor_settings = cursor_config_dir / "cli-config.json"
backup_timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S.%f%z")
backed_up = set()


def say(message):
    print("  " + message)


def backup_once(path):
    if path in backed_up:
        return
    if path.exists():
        destination = Path(str(path) + "." + backup_timestamp + ".bak")
        # Exclusive creation preserves older backups even on a timestamp collision.
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as target, path.open("rb") as source:
            shutil.copyfileobj(source, target)
        shutil.copystat(path, destination)
        say("backed up: %s" % destination)
    # Remember absent files too: later mutations must not back up partial installs.
    backed_up.add(path)


def configure_statusline_settings(path, command):
    desired = {"type": "command", "command": command}
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as error:
        say("skip: cannot read %s (%s)" % (path, error))
        return
    if not isinstance(settings, dict):
        say("skip: %s is not a JSON object" % path)
        return
    if settings.get("statusLine") == desired:
        say("ok: %s already points at the status line script" % path)
        return
    if dry_run:
        say("would set statusLine in %s to: %s" % (path, command))
        return
    backup_once(path)
    settings["statusLine"] = desired
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    say("configured: statusLine in %s" % path)


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
    backup_once(path)
    merge(settings, updates)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    say("configured: %s" % path)


def configure_codex_toml(path, key, value):
    """Set a top-level key in config.toml, keeping it above the first table."""
    import tomllib

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
    backup_once(path)
    path.write_text(updated, encoding="utf-8")
    say("configured: %s" % path)


def configure_hermes_skills():
    path = Path(hermes_home) / "config.yaml"
    skills_path = str(Path(skills_dir).resolve())
    if dry_run:
        say("would append %s to Hermes skills.external_dirs in %s if absent" % (skills_path, path))
        return
    env = dict(os.environ, HERMES_HOME=str(Path(hermes_home).resolve()))

    def cli(*args):
        result = subprocess.run([hermes_command, "config", *args], env=env,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Hermes config %s failed (exit %s); check %s" %
                               (args[0], result.returncode, path))
        return result.stdout.strip()

    actual_path = Path(cli("path"))
    if actual_path.resolve() != path.resolve():
        raise RuntimeError("Hermes CLI resolved a different config; refusing to write")
    current = json.loads(cli("get", "skills.external_dirs", "--json"))
    if current is None:
        current = []
    if not isinstance(current, list) or not all(isinstance(p, str) for p in current):
        raise ValueError("Hermes skills.external_dirs must be a list of paths")
    target = Path(skills_path)
    for entry in current:
        if not entry.strip():
            continue
        existing = Path(os.path.expandvars(entry.strip())).expanduser()
        if not existing.is_absolute():
            existing = Path(hermes_home) / existing
        if existing.resolve() == target:
            say("ok: Hermes already scans %s" % skills_path)
            return
    desired = current + [skills_path]
    backup_once(path)
    cli("set", "skills.external_dirs", json.dumps(desired))
    if json.loads(cli("get", "skills.external_dirs", "--json")) != desired:
        raise RuntimeError("Hermes skills.external_dirs did not take effect; backup retained")
    say("configured: Hermes skills.external_dirs in %s" % path)


if hermes_enabled:
    configure_hermes_skills()

if not no_statusline:
    configure_statusline_settings(home / ".claude" / "settings.json", claude_command)
    configure_statusline_settings(cursor_settings, cursor_command)

if no_attribution:
    print("Commit attribution: skipped (--no-attribution).")
    sys.exit(0)

print("Commit attribution:")
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
    cursor_settings,
    {"attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}},
    "cursor",
)
say("note: gemini and grok document no attribution setting; nothing to change")
SETTINGS_PY
fi

if [ "$dry_run" -eq 1 ]; then
    echo "Dry run: nothing was changed."
fi
