#!/usr/bin/env python3
"""Apply the settings changes scripts/install.sh makes, in one process.

install.sh runs this after linking skills and agents. It:

- points the Claude Code and Cursor status lines at the repository's scripts;
- turns off commit and pull request attribution in Claude Code, Codex, and Cursor;
- registers the skills directory with Hermes, and adds the generated personalities.

Every file is backed up once, before its first change, and every backup in one
run shares a timestamp. Running everything in one process is what makes that
possible. Hermes is only ever changed through its own CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python older than 3.11
    tomllib = None


def say(message: str) -> None:
    print("  " + message)


class Backups:
    """Back up each file once per run, before its first change."""

    def __init__(self) -> None:
        self.timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S.%f%z")
        self.seen: set[Path] = set()

    def once(self, path: Path) -> None:
        if path in self.seen:
            return
        if path.exists():
            destination = Path(str(path) + "." + self.timestamp + ".bak")
            # Exclusive creation preserves older backups even on a timestamp collision.
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as target, path.open("rb") as source:
                shutil.copyfileobj(source, target)
            shutil.copystat(path, destination)
            say(f"backed up: {destination}")
        # Remember absent files too: later mutations must not back up partial installs.
        self.seen.add(path)


# --- Status line and attribution --------------------------------------------


def cursor_config_dir(home: Path) -> Path:
    """Return Cursor's config directory, following the Cursor CLI's precedence.

    Empty or whitespace-only overrides are ignored.
    """
    custom = os.environ.get("CURSOR_CONFIG_DIR", "")
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    if custom.strip():
        return Path(custom)
    if xdg.strip():
        return Path(xdg) / "cursor"
    return home / ".cursor"


def read_json_object(path: Path) -> dict | None:
    """Read a JSON settings file; a missing one is empty, an unusable one is None."""
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as error:
        say(f"skip: cannot read {path} ({error})")
        return None
    if not isinstance(settings, dict):
        say(f"skip: {path} is not a JSON object")
        return None
    return settings


def configure_statusline(path: Path, command: str, dry_run: bool, backups: Backups) -> None:
    desired = {"type": "command", "command": command}
    settings = read_json_object(path)
    if settings is None:
        return
    if settings.get("statusLine") == desired:
        say(f"ok: {path} already points at the status line script")
        return
    if dry_run:
        say(f"would set statusLine in {path} to: {command}")
        return
    backups.once(path)
    settings["statusLine"] = desired
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    say(f"configured: statusLine in {path}")


def merge(target: dict, updates: dict) -> bool:
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


def configure_json(path: Path, updates: dict, label: str, dry_run: bool, backups: Backups) -> None:
    """Merge updates into a tool's JSON settings, if the tool is installed."""
    if not path.parent.is_dir():
        say(f"skip: {label} is not installed")
        return
    settings = read_json_object(path)
    if settings is None:
        return

    # Merge into a copy first, so an unchanged file is neither backed up nor rewritten.
    probe = json.loads(json.dumps(settings))
    if not merge(probe, updates):
        say(f"ok: {label} already disables attribution")
        return
    if dry_run:
        say(f"would update: {path}")
        return
    backups.once(path)
    merge(settings, updates)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    say(f"configured: {path}")


def set_toml_key(text: str, key: str, value: str) -> str:
    """Set a top-level key in TOML text, keeping it above the first table."""
    lines = text.splitlines()
    assignment = f'{key} = "{value}"'
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
    return "\n".join(lines) + "\n"


def configure_codex_toml(path: Path, key: str, value: str, dry_run: bool, backups: Backups) -> None:
    """Set a top-level key in Codex's config.toml, verifying the edit before writing it."""
    if not path.parent.is_dir():
        say("skip: codex is not installed")
        return
    if tomllib is None:
        say(f"skip: editing {path} needs Python 3.11 or newer")
        return
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        if tomllib.loads(text).get(key) == value:
            say("ok: codex already disables attribution")
            return
    except tomllib.TOMLDecodeError as error:
        say(f"skip: cannot parse {path} ({error})")
        return
    if dry_run:
        say(f"would set {key} = \"{value}\" in {path}")
        return

    updated = set_toml_key(text, key, value)
    try:
        if tomllib.loads(updated).get(key) != value:
            raise tomllib.TOMLDecodeError("key did not take effect", updated, 0)
    except tomllib.TOMLDecodeError as error:
        say(f"skip: edit would corrupt {path} ({error}); left unchanged")
        return
    backups.once(path)
    path.write_text(updated, encoding="utf-8")
    say(f"configured: {path}")


# --- Hermes ------------------------------------------------------------------


class Hermes:
    """The Hermes CLI, run against one HERMES_HOME."""

    def __init__(self, home: str, command: str) -> None:
        self.home = Path(home)
        self.command = command

    @property
    def config_path(self) -> Path:
        return self.home / "config.yaml"

    def cli(self, *args: str) -> str:
        """Run `hermes config ARGS...` and return its trimmed output."""
        env = dict(os.environ, HERMES_HOME=str(self.home.resolve()))
        result = subprocess.run(
            [self.command, "config", *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"Hermes config {args[0]} failed (exit {result.returncode}); check {self.config_path}"
            )
        return result.stdout.strip()

    def get(self, key: str) -> object:
        """Return a config value, or None when it is unset."""
        return json.loads(self.cli("get", key, "--json") or "null")

    def check_config_path(self) -> None:
        """Refuse to write when the CLI would edit a different config file."""
        actual_path = Path(self.cli("path"))
        if actual_path.resolve() != self.config_path.resolve():
            raise RuntimeError("Hermes CLI resolved a different config; refusing to write")


def configure_hermes_skills(hermes: Hermes, skills_dir: str, dry_run: bool, backups: Backups) -> None:
    """Append the skills directory to skills.external_dirs, unless Hermes already scans it."""
    path = hermes.config_path
    skills_path = str(Path(skills_dir).resolve())
    if dry_run:
        say(f"would append {skills_path} to Hermes skills.external_dirs in {path} if absent")
        return
    hermes.check_config_path()
    current = json.loads(hermes.cli("get", "skills.external_dirs", "--json"))
    if current is None:
        current = []
    if not isinstance(current, list) or not all(isinstance(p, str) for p in current):
        raise ValueError("Hermes skills.external_dirs must be a list of paths")

    # Entries may use ~, environment variables, or paths relative to HERMES_HOME.
    target = Path(skills_path)
    for entry in current:
        if not entry.strip():
            continue
        existing = Path(os.path.expandvars(entry.strip())).expanduser()
        if not existing.is_absolute():
            existing = hermes.home / existing
        if existing.resolve() == target:
            say(f"ok: Hermes already scans {skills_path}")
            return

    desired = current + [skills_path]
    backups.once(path)
    hermes.cli("set", "skills.external_dirs", json.dumps(desired))
    if json.loads(hermes.cli("get", "skills.external_dirs", "--json")) != desired:
        raise RuntimeError("Hermes skills.external_dirs did not take effect; backup retained")
    say(f"configured: Hermes skills.external_dirs in {path}")


# --- Hermes personalities ----------------------------------------------------
#
# A Hermes personality lives in the user's config.yaml, which the user may also
# edit, so this installer only replaces a personality it can show it set. The
# state file records, per config file, a digest of each personality this
# installer wrote. A personality whose current value still matches its digest
# is ours to update; any other existing value needs --force.

PERSONALITY_KEYS = {"description", "system_prompt"}


def state_path() -> Path:
    """Return the installer's state file, under XDG_STATE_HOME."""
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    state_home = Path(base) if base else Path.home() / ".local" / "state"
    return state_home / "dotagents" / "install-state.json"


def load_state() -> dict:
    """Read the state file; a missing or unreadable one means nothing is owned."""
    path = state_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        say(f"note: cannot read {path} ({error}); treating every personality as not owned")
        return {}
    return state if isinstance(state, dict) else {}


def save_state(state: dict) -> None:
    """Write the state file through a temporary file, so a crash cannot truncate it."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def personality_digest(value: object) -> str | None:
    """Return a digest of a personality, or None when it is not one this installer writes.

    Only a mapping of exactly a string description and a string system_prompt
    can be owned; anything else was shaped by someone else.
    """
    if not isinstance(value, dict) or set(value) != PERSONALITY_KEYS:
        return None
    if not all(isinstance(value[key], str) for key in value):
        return None
    data = value["description"] + "\0" + value["system_prompt"]
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


def read_personality_file(path: Path) -> dict[str, str]:
    """Read a generated personality file.

    The generator writes a header comment and then one line per key, each value
    a JSON string (which is also valid YAML), so no YAML parser is needed.
    """
    value: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        key, separator, raw = line.partition(": ")
        if not separator or key not in PERSONALITY_KEYS or key in value:
            raise ValueError(f"{path}: unexpected line {line[:40]!r}")
        value[key] = json.loads(raw)
        if not isinstance(value[key], str):
            raise ValueError(f"{path}: {key} must be a string")
    if set(value) != PERSONALITY_KEYS:
        raise ValueError(f"{path}: needs description and system_prompt")
    return value


def personality_action(name: str, existing: object, recorded_digest: str | None, force: bool) -> str | None:
    """Decide how to treat a personality that differs from the generated one.

    Returns the verb to report, or None to leave the personality alone.
    """
    if existing is None:
        return "added"
    if recorded_digest is not None and personality_digest(existing) == recorded_digest:
        # Unchanged since this installer wrote it, so it is safe to update.
        return "updated"
    if force:
        return "replaced (--force; the previous value is in the config backup)"
    say(
        f"skip: personality {name} exists and was not set by this installer, or was changed since "
        "(use --force to replace)"
    )
    return None


class PersonalityOwnership:
    """The personalities this installer set in one Hermes config file, by digest.

    Ownership is recorded per config file, so two HERMES_HOME values do not
    vouch for each other: state["hermes_personalities"][config path][name].
    """

    def __init__(self, config_path: Path) -> None:
        self.state = load_state()
        by_config = self.state.get("hermes_personalities")
        if not isinstance(by_config, dict):
            by_config = self.state["hermes_personalities"] = {}
        self.by_config = by_config
        self.key = str(config_path.resolve())
        owned = by_config.get(self.key)
        self.owned: dict[str, str] = owned if isinstance(owned, dict) else {}
        self.changed = False

    def record(self, name: str, digest: str | None) -> None:
        if self.owned.get(name) != digest:
            self.owned[name] = digest
            self.changed = True

    def forget(self, name: str) -> None:
        del self.owned[name]
        self.changed = True

    def save(self) -> None:
        if self.changed:
            self.by_config[self.key] = self.owned
            save_state(self.state)


def configure_hermes_personalities(hermes: Hermes, options: argparse.Namespace, backups: Backups) -> None:
    """Add each generated personality, or update one this installer set, then report leftovers."""
    print("Hermes personalities:")
    if not options.personalities:
        say(options.personalities_skip)
        return
    source = Path(options.personalities_dir)
    files = sorted(source.glob("*.yaml")) if source.is_dir() else []
    if not files:
        say(f"skip: no generated personalities in {source}")
        return

    path = hermes.config_path
    desired = {item.stem: read_personality_file(item) for item in files}
    if options.dry_run:
        for name in desired:
            say(f"would set agent.personalities.{name} in {path} if absent or owned by this installer")
        return

    hermes.check_config_path()
    current = hermes.get("agent.personalities")
    if current is None:
        current = {}
    if not isinstance(current, dict):
        raise ValueError("Hermes agent.personalities must be a mapping")

    ownership = PersonalityOwnership(path)
    for name, value in desired.items():
        existing = current.get(name)
        digest = personality_digest(value)
        if existing == value:
            say(f"ok: personality {name} is current")
            # Record ownership of a matching value too, so a later update works.
            ownership.record(name, digest)
            continue

        action = personality_action(name, existing, ownership.owned.get(name), options.force)
        if action is None:
            continue
        backups.once(path)
        hermes.cli("set", "agent.personalities." + name, json.dumps(value))
        if hermes.get("agent.personalities." + name) != value:
            raise RuntimeError(f"Hermes agent.personalities.{name} did not take effect; backup retained")
        ownership.record(name, digest)
        say(f"{action}: personality {name}")

    # A personality recorded as ours whose agent was removed is reported, not
    # deleted; once the user removes it, its record is dropped too.
    for name in sorted(set(ownership.owned) - set(desired)):
        if name in current:
            say(
                f"note: personality {name} was set by this installer, but its role no longer exists; "
                "left in place for you to remove"
            )
        else:
            ownership.forget(name)
    ownership.save()


# --- Entry point ---------------------------------------------------------------


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes without making them")
    parser.add_argument("--force", action="store_true", help="replace personalities this installer did not set")
    parser.add_argument("--no-statusline", action="store_true", help="leave status line settings alone")
    parser.add_argument("--no-attribution", action="store_true", help="leave attribution settings alone")
    parser.add_argument("--claude-statusline-command", default="", help="Claude Code status line command")
    parser.add_argument("--cursor-statusline-command", default="", help="Cursor status line command")
    parser.add_argument("--hermes-home", default="", help="the HERMES_HOME to configure")
    parser.add_argument("--hermes-command", default="hermes", help="the Hermes executable")
    parser.add_argument("--hermes-skills", action="store_true", help="register --skills-dir with Hermes")
    parser.add_argument("--skills-dir", default="", help="the skills directory to register")
    parser.add_argument("--personalities", action="store_true", help="add the generated Hermes personalities")
    parser.add_argument("--personalities-dir", default="", help="the generated personalities directory")
    parser.add_argument("--personalities-skip", default="", help="the message to print when not adding them")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    home = Path.home()
    backups = Backups()
    hermes = Hermes(options.hermes_home, options.hermes_command)

    if options.hermes_skills:
        configure_hermes_skills(hermes, options.skills_dir, options.dry_run, backups)
    configure_hermes_personalities(hermes, options, backups)

    cursor_settings = cursor_config_dir(home) / "cli-config.json"
    if not options.no_statusline:
        print("Status line settings:")
        claude_settings = home / ".claude" / "settings.json"
        configure_statusline(claude_settings, options.claude_statusline_command, options.dry_run, backups)
        configure_statusline(cursor_settings, options.cursor_statusline_command, options.dry_run, backups)

    if options.no_attribution:
        print("Commit attribution: skipped (--no-attribution).")
        return 0

    print("Commit attribution:")
    # sessionUrl is a separate switch from commit and pr: it defaults to true and
    # appends a claude.ai session link to commits and PR bodies, but only in web and
    # Remote Control sessions, so an empty commit and pr pair does not cover it.
    configure_json(
        home / ".claude" / "settings.json",
        {"attribution": {"commit": "", "pr": "", "sessionUrl": False}},
        "claude",
        options.dry_run,
        backups,
    )
    configure_codex_toml(home / ".codex" / "config.toml", "commit_attribution", "", options.dry_run, backups)
    configure_json(
        cursor_settings,
        {"attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}},
        "cursor",
        options.dry_run,
        backups,
    )
    say("note: gemini and grok document no attribution setting; nothing to change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
