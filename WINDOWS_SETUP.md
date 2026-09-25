# Windows Setup Guide

## Overview

This document explains how to set up `dotagents` on Windows with PowerShell and GitHub Copilot in VS Code.
No administrator rights or Developer Mode are required.
The installer uses directory junctions and hard links instead of symbolic links, neither of which needs elevation.

## Prerequisites

- **PowerShell 7 or higher** (`pwsh` on `PATH`; install separately from Windows PowerShell)
- **Git for Windows** (for cloning and git operations)
- **Python 3.x** (for validation scripts)
- **VS Code** or **Claude Code** or **Cursor**
- **GitHub Copilot** extension in VS Code (for GitHub Copilot integration)

Install PowerShell 7 with `winget install --id Microsoft.PowerShell --source winget`, then open `pwsh` before running the commands below.
The installer requires PowerShell 7, and the installed status line commands also use `pwsh`.

### Optional

- **`just`** task runner (Windows binary available from [the just releases page](https://github.com/casey/just/releases))
- **`markdownlint-cli2`** (via npm or npx)
- **Node.js/npm** (if you want to use markdownlint)

## How the Installer Links Files

The Unix installer uses symbolic links, which on Windows require administrator rights or Developer Mode.
To avoid that, `install.ps1` picks a link type that needs neither:

- **Skill directories** (each skill, linked into a real skills directory that each tool owns) use a **junction**.
  An older install that linked the whole `skills/` directory is migrated to a real directory, so skills a tool writes itself never land in the clone.
  Junctions need no elevation and can point across local drives, so editing a file in the clone still changes what every tool reads.
- **Single-file targets** (each Claude, Codex, and Cursor agent file, `AGENTS.md`, the status line scripts) use a **hard link** when the clone and your home directory are on the same drive.
  Hard links also need no elevation and stay in sync with edits made in place.
  Regenerating agents with `just ci`, or a `git pull` that changes a file, replaces the file in the clone instead, which leaves the hard link holding the old content.
- When the clone and your home directory are on **different drives**, a hard link is impossible, so the file is **copied** instead.
  Copies are compared by SHA-256 hash: an identical file is left alone, and a changed file is replaced only when you pass `-Force`.
  A copied file does not update automatically, so re-run the installer after editing such a file.
- The installer records the hash of every file it places in `%LOCALAPPDATA%\dotagents\install-state.json`.
  A re-run refreshes an installed file that still matches that record, so re-run it after regenerating agents or pulling; a file you changed yourself is left alone unless you pass `-Force`.

Pass `-Copy` to force copying for files even when a hard link would work.

## Installation Steps

Follow these three steps to clone the repository, run the installer, and confirm the links were created.

### 1. Clone or Navigate to the Repository

```powershell
# If cloning fresh (recommended location: ~/.agents or your projects folder)
git clone https://github.com/cypher0n3/dotagents.git ~/.agents
cd ~/.agents
```

### 2. Run the Windows Installation Script

```powershell
# Dry run first to see what will be installed
.\scripts\install.ps1 -DryRun

# If everything looks good, run the actual installation
.\scripts\install.ps1

# Options:
# -Force                 Replace an existing link, or a copied file that differs
# -Copy                  Copy files instead of hard-linking them
# -NoStatusline          Skip statusline script installation and configuration
# -NoAttribution         Skip disabling agent commit/PR attribution
# -NoHermes              Skip both Hermes steps: skill registration and personalities
# -NoCodexAgents         Skip installing the generated Codex agents
# -NoCursorAgents        Skip installing the generated Cursor agents
# -NoHermesPersonalities Skip setting the generated Hermes personalities
# -NoCaiPersonas         Silence the CAI personas report (CAI is Linux/XDG only)
# -DryRun                Show what would happen without making changes
```

Before changing an existing settings file, the installer saves one timestamped backup beside it for that run, even when both the status line and attribution change.
See [Settings Backups](README.md#settings-backups) for the filename format and retention behavior.
Cursor CLI settings honor `$env:CURSOR_CONFIG_DIR`, then `$env:XDG_CONFIG_HOME` with a `cursor` subdirectory, then `~/.cursor`; see [Cursor CLI Configuration Location](README.md#cursor-cli-configuration-location).

For an existing Hermes Agent installation, keep `hermes` on `PATH`; the installer registers this clone through `skills.external_dirs` rather than replacing Hermes's own skills directory, and sets each generated personality under `agent.personalities`.
A personality of the same name that the installer did not set, or that you changed after it did, is replaced only with `-Force`.
`HERMES_HOME` selects the target configuration; otherwise native Windows uses `%LOCALAPPDATA%/hermes`.
See [Hermes Agent](README.md#hermes-agent) for profile handling, prerequisites, and the limits of shared skills.

### 3. Verify Installation

Check that skills are linked:

```powershell
# Verify Claude Code skills
if (Test-Path ~/.claude/skills) {
    Get-Item ~/.claude/skills
}

# Verify GitHub Copilot skills
if (Test-Path ~/.copilot/skills) {
    Get-Item ~/.copilot/skills
}

# Verify agents
if (Test-Path ~/.claude/agents) {
    Get-ChildItem ~/.claude/agents
}
```

Run validation scripts:

```powershell
# From the repository root
python .ci_scripts/validate_skills.py skills
python .ci_scripts/validate_agents.py agents skills
```

## Using GitHub Copilot in Visual Studio Code

GitHub Copilot in VS Code discovers Agent Skills automatically from known locations; no settings override is required.
It reads **personal skills** from `~/.copilot/skills/`, `~/.claude/skills/`, and `~/.agents/skills/`, and **project skills** from `.github/skills/`, `.claude/skills/`, and `.agents/skills/` in a workspace.

`install.ps1` links this repository's `skills/` directly into `~/.copilot/skills` (the same junction pattern used for Claude Code, Cursor, and Gemini), so Copilot picks the skills up with no further configuration:

1. **Install the extension**: install "GitHub Copilot" in VS Code.
2. **Run the installer**: `.\scripts\install.ps1` (see above), which creates the `~/.copilot/skills` junction Copilot reads.
3. **Restart VS Code** so it rescans the skill locations.
4. **Verify**: open Copilot Chat, type `/`, and confirm the skills appear in the list, or run `Chat: Configure Skills` from the Command Palette (`Ctrl+Shift+P`).

To scope the skills to a single project instead of your whole profile, symlink or copy `skills/` into that project's `.github/skills/` folder.

VS Code also reads always-on instructions from `AGENTS.md` at the workspace root, so this repository's [AGENTS.md](AGENTS.md) applies automatically when you open the repo in VS Code.

## Using the Task Runner (Just)

If you have `just` installed on Windows:

```powershell
# List available recipes
just

# Run validation
just ci

# Lint markdown (requires markdownlint-cli2)
just lint-md

# Run all checks
just ci
```

To install `just` on Windows:

- Download from [the just releases page](https://github.com/casey/just/releases)
- Or use `scoop install just` or `choco install just`

The recipes need Bash on `PATH`, such as the one Git for Windows installs.
`just ci` runs the PowerShell installer tests with your `pwsh`; without PowerShell 7 it skips them with a notice.

## Troubleshooting

This section covers the failure modes specific to the Windows installer.

### Link Creation Fails

Junctions and hard links do not require elevation, so this should not happen.
If it does:

1. Confirm the target volume supports reparse points (junctions require NTFS; they do not work on FAT32/exFAT drives, or most network shares).
2. Check that a real file or directory is not already at the destination; the installer skips those rather than overwriting them.
   Pass `-Force` to replace a link or copy that points somewhere else:

   ```powershell
   .\scripts\install.ps1 -Force
   ```

3. If the clone and your home directory are on different drives, single files fall back to copying; re-run the installer with `-Force` after editing a source file to refresh those copies.

### Skills Not Appearing in GitHub Copilot

1. Check the junction was created:

   ```powershell
   Get-Item ~/.copilot/skills -Force | Select-Object LinkType, Target
   ```

2. Verify file structure:

   ```powershell
   Get-ChildItem ~/.copilot/skills/*/SKILL.md
   ```

3. Restart VS Code completely (close and reopen).
4. Confirm Copilot sees them: run `Chat: Configure Skills` from the Command Palette (`Ctrl+Shift+P`), or type `/` in Copilot Chat and look for the skill names in the list.

### Validation Fails

If `validate_skills.py` or `validate_agents.py` fail:

```powershell
# Run with Python directly to see full output
python -u .ci_scripts/validate_skills.py skills

# Check Python version (3.7+ required)
python --version
```

### Git Commands Not Working

Ensure Git for Windows is installed and in your PATH:

```powershell
git --version

# If not found, install from https://git-scm.com/download/win
```

## Development Workflow

This section covers the commands used while editing skills without `just` installed.

### Running CI Locally

Without `just`:

```powershell
# Validate all skills
python .ci_scripts/validate_skills.py skills

# Validate all agents
python .ci_scripts/validate_agents.py agents skills

# Validate documentation links
python .ci_scripts/validate_doc_links.py .

# Run Python tests
python -m pytest .ci_scripts/
```

With `just` (if installed):

```powershell
# Run all checks
just ci
```

### Editing Skills

Skills are located in `skills/*/SKILL.md`.
After making changes:

```powershell
# Validate your changes
python .ci_scripts/validate_skills.py skills/your-skill-name

# Run full CI to check everything
python .ci_scripts/validate_skills.py skills
```

## Next Steps

1. **Read the documentation**: [docs/docs_standards/](docs/docs_standards/README.md)
2. **Review skill structure**: [skills/README.md](skills/README.md)
3. **Check agent definitions**: [agents/README.md](agents/README.md)
4. **Explore existing skills** in `skills/` directory

## Additional Resources

- **Original Repository**: [cypher0n3/dotagents](https://github.com/cypher0n3/dotagents)
- **Just Task Runner**: [casey/just](https://github.com/casey/just)
- **GitHub Copilot Docs**: [docs.github.com/en/copilot](https://docs.github.com/en/copilot)
- **Markdownlint**: [DavidAnson/markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2)
