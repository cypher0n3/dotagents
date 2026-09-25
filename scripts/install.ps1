#requires -Version 7.0

<#
.SYNOPSIS
    Install this repository's skills, agents, and instructions into the agent
    tools that read them, on Windows without administrator rights.

.DESCRIPTION
    The Unix installer (scripts/install.sh) uses symbolic links. On Windows a
    symbolic link needs administrator rights or Developer Mode, so this script
    avoids them and picks a link type that does not:

      - Directory targets use a junction (mklink /J equivalent). Junctions need
        no elevation and can point across local volumes, so editing a file in
        this clone still changes what every tool reads.
      - Skills get one junction per skill inside a real directory each tool
        owns, so a skill a tool writes there itself never lands in this clone.
        An older install that linked skills/ as a whole is migrated to a real
        directory. A skills/ entry without a SKILL.md is never linked; it is
        reported, since it is usually content a tool wrote through that older
        link. A link to a skill that no longer exists is reported and left in
        place.
      - Single-file targets use a hard link on the same volume, which also needs
        no elevation. When the clone and the home directory are on different
        volumes (a hard link is impossible there) the file is copied instead.

    Copies are the only case that can drift. To keep them predictable the copy
    path compares SHA-256 hashes: an identical file is reported as up to date and
    left alone, and a file that differs is replaced only when -Force is given.
    Pass -Copy to force the copy strategy for files even when a hard link would
    work.

    An existing real file or directory that this repository did not create is
    never overwritten unless -Force is given.

.PARAMETER DryRun
    Print the changes that would be made and change nothing.

.PARAMETER Force
    Replace an existing link, or a copied file whose contents differ, that
    points somewhere other than this clone.

.PARAMETER Copy
    Copy files instead of hard-linking them, even when a hard link is possible.
    Directory targets always use junctions regardless of this switch.

.PARAMETER NoStatusline
    Skip installing and configuring the Claude Code and Cursor status lines.

.PARAMETER NoAttribution
    Skip turning off agent commit and PR attribution.

.PARAMETER NoHermes
    Skip adding this repository's skills to Hermes skills.external_dirs.

.EXAMPLE
    .\scripts\install.ps1 -DryRun

.EXAMPLE
    .\scripts\install.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force,
    [switch]$Copy,
    [switch]$NoStatusline,
    [switch]$NoAttribution,
    [switch]$NoHermes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# One local, filename-safe ISO timestamp and backup decision per install run.
$script:settingsBackupTimestamp = (Get-Date).ToString(
    "yyyyMMdd'T'HHmmss.ffffffzzz", [System.Globalization.CultureInfo]::InvariantCulture
).Replace(':', '')
$script:settingsBackupHandled = @{}

# --- helpers ---------------------------------------------------------------

# Expand a leading ~ to the user's home directory.
function Expand-Home {
    param([Parameter(Mandatory)][string]$Path)
    if ($Path -eq '~') { return $HOME }
    if ($Path.StartsWith('~/') -or $Path.StartsWith('~\')) {
        $Path = Join-Path $HOME $Path.Substring(2)
    }
    return $Path
}

function Write-Step {
    param([string]$Message)
    Write-Host $Message
}

function Write-Detail {
    param([string]$Message)
    Write-Host "  $Message"
}

# Absolute path of an existing item, without a trailing separator.
function Resolve-Full {
    param([Parameter(Mandatory)][string]$Path)
    return (Resolve-Path -LiteralPath $Path).Path.TrimEnd('\', '/')
}

function Get-Root {
    param([Parameter(Mandatory)][string]$Path)
    return [System.IO.Path]::GetPathRoot($Path)
}

function Get-Sha {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

# Reparse target (junction or symlink) of an item, or $null.
function Get-LinkTarget {
    param([Parameter(Mandatory)]$Item)
    $target = $Item.Target
    if ($null -eq $target) { return $null }
    if ($target -is [array]) { $target = $target[0] }
    if ([string]::IsNullOrEmpty($target)) { return $null }
    return ([string]$target).TrimEnd('\', '/')
}

function Ensure-Parent {
    param([Parameter(Mandatory)][string]$Path)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        if ($DryRun) {
            Write-Detail "would create directory: $parent"
        } else {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
    }
}

# Install-DirLink <source-dir> <link-path>
# Point link-path at source-dir with a directory junction.
function Install-DirLink {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Link
    )
    $source = Resolve-Full $Source
    $link = Expand-Home $Link

    if (Test-Path -LiteralPath $link) {
        $item = Get-Item -LiteralPath $link -Force
        $existing = Get-LinkTarget $item
        if ($existing) {
            if ($existing -ieq $source) {
                Write-Detail "ok: $link (already linked)"
                return
            }
            if (-not $Force) {
                Write-Detail "skip: $link points at $existing (use -Force to replace)"
                return
            }
            if ($DryRun) {
                Write-Detail "would remove junction: $link"
            } else {
                # Remove the reparse point without touching the target contents.
                (Get-Item -LiteralPath $link -Force).Delete()
            }
        } else {
            Write-Detail "skip: $link exists and is a real directory"
            return
        }
    }

    Ensure-Parent $link
    if ($DryRun) {
        Write-Detail "would junction: $link -> $source"
    } else {
        New-Item -ItemType Junction -Path $link -Target $source | Out-Null
        Write-Detail "junction: $link -> $source"
    }
}

# Install-FileLink <source-file> <link-path>
# Hard-link link-path to source-file on the same volume, else copy it.
function Install-FileLink {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Link
    )
    $source = Resolve-Full $Source
    $link = Expand-Home $Link

    $sameVolume = (Get-Root $source) -ieq (Get-Root ([System.IO.Path]::GetFullPath($link)))
    $useCopy = $Copy -or (-not $sameVolume)

    if (Test-Path -LiteralPath $link) {
        $item = Get-Item -LiteralPath $link -Force
        if ($item.PSIsContainer) {
            Write-Detail "skip: $link exists and is a directory"
            return
        }
        # A hard link to the same file, or a copy that still matches, shares the
        # source hash. Either way there is nothing to do.
        if ((Get-Sha $link) -ieq (Get-Sha $source)) {
            Write-Detail "ok: $link (up to date)"
            return
        }
        if (-not $Force) {
            Write-Detail "skip: $link differs from source (use -Force to replace)"
            return
        }
        if ($DryRun) {
            Write-Detail "would remove file: $link"
        } else {
            Remove-Item -LiteralPath $link -Force
        }
    }

    Ensure-Parent $link
    if ($useCopy) {
        if ($DryRun) {
            $why = if ($Copy) { '-Copy' } else { 'different volume' }
            Write-Detail "would copy ($why): $link <- $source"
        } else {
            Copy-Item -LiteralPath $source -Destination $link -Force
            Write-Detail "copied: $link <- $source"
        }
        return
    }

    if ($DryRun) {
        Write-Detail "would hard-link: $link -> $source"
        return
    }
    try {
        New-Item -ItemType HardLink -Path $link -Target $source | Out-Null
        Write-Detail "hardlink: $link -> $source"
    } catch {
        Copy-Item -LiteralPath $source -Destination $link -Force
        Write-Detail "copied (hard link failed): $link <- $source"
    }
}

# Report agent files in a target directory that this repository did not provide,
# and reparse points whose target is gone, removing nothing.
function Report-ExtraAgents {
    param(
        [Parameter(Mandatory)][string]$SourceDir,
        [Parameter(Mandatory)][string]$TargetDir
    )
    $target = Expand-Home $TargetDir
    if (-not (Test-Path -LiteralPath $target)) { return }

    $provided = @{}
    Get-ChildItem -LiteralPath $SourceDir -Filter '*.md' |
        Where-Object { $_.Name -ne 'README.md' } |
        ForEach-Object { $provided[$_.Name] = $true }

    foreach ($entry in Get-ChildItem -LiteralPath $target -Filter '*.md' -Force) {
        $linkTarget = Get-LinkTarget $entry
        if ($linkTarget -and -not (Test-Path -LiteralPath $linkTarget)) {
            Write-Detail "note: broken link left in place: $($entry.Name) -> $linkTarget"
            continue
        }
        if (-not $provided.ContainsKey($entry.Name)) {
            Write-Detail "note: agent not provided by this repository, left as is: $($entry.Name)"
        }
    }
}

# Prepare-RealDir <target-dir> <source-dir>
# Make the target a real directory and return 'ready', 'dry-migrate' (a dry run
# that would replace a link, so the directory does not exist yet), or 'skip'.
# A link to the matching source directory in this repository (skills/ or
# agents/) is the layout an older install created, so it is replaced without
# -Force. A link anywhere else needs -Force.
function Prepare-RealDir {
    param(
        [Parameter(Mandatory)][string]$TargetDir,
        [Parameter(Mandatory)][string]$SourceDir
    )
    $target = Expand-Home $TargetDir
    $migrating = $false

    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        $existing = Get-LinkTarget $item
        if ($existing) {
            if ($existing -ieq (Resolve-Full $SourceDir)) {
                Write-Detail "migrate: $target links the whole $(Split-Path -Leaf $SourceDir) directory; replacing it with a real directory"
            } elseif ($Force) {
                Write-Detail "migrate: $target points at $existing; replacing it with a real directory"
            } else {
                Write-Detail "skip: $target points at $existing (use -Force to replace)"
                return 'skip'
            }
            if ($DryRun) { return 'dry-migrate' }
            # Remove the reparse point without touching the target contents.
            $item.Delete()
            $migrating = $true
        } elseif (-not $item.PSIsContainer) {
            Write-Detail "skip: $target exists and is not a directory"
            return 'skip'
        }
    }

    if ($migrating -or -not (Test-Path -LiteralPath $target)) {
        if ($DryRun) {
            Write-Detail "would create directory: $target"
        } else {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
        }
    }
    return 'ready'
}

# Report links in a skills directory that point into skills/ at a skill that
# no longer exists, removing nothing.
function Report-StaleSkills {
    param([Parameter(Mandatory)][string]$TargetDir)
    $target = Expand-Home $TargetDir
    if (-not (Test-Path -LiteralPath $target)) { return }
    $source = Resolve-Full $skillsDir

    foreach ($entry in Get-ChildItem -LiteralPath $target -Force) {
        $linkTarget = Get-LinkTarget $entry
        if ($linkTarget -and $linkTarget.StartsWith($source, [System.StringComparison]::OrdinalIgnoreCase) -and
            -not (Test-Path -LiteralPath $linkTarget)) {
            Write-Detail "note: broken link left in place: $($entry.Name) -> $linkTarget"
        }
    }
}

# Serialize a JSON object stably for before/after comparison.
function ConvertTo-Stable {
    param($Object)
    return ($Object | ConvertTo-Json -Depth 100)
}

function Read-JsonFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return [pscustomobject]@{} }
    try {
        $raw = Get-Content -LiteralPath $Path -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{} }
        return ($raw | ConvertFrom-Json)
    } catch {
        Write-Detail "skip: cannot read $Path ($($_.Exception.Message))"
        return $null
    }
}

function Set-Prop {
    param($Object, [string]$Name, $Value)
    if ($Object.PSObject.Properties[$Name]) {
        $Object.$Name = $Value
    } else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Get-OrCreateChild {
    param($Object, [string]$Name)
    if (-not $Object.PSObject.Properties[$Name] -or $null -eq $Object.$Name -or
        $Object.$Name -isnot [System.Management.Automation.PSCustomObject]) {
        Set-Prop $Object $Name ([pscustomobject]@{})
    }
    return $Object.$Name
}

# Preserve the original bytes once, before the first write to each settings file.
function Backup-SettingsOnce {
    param([Parameter(Mandatory)][string]$Path)
    if ($DryRun -or $script:settingsBackupHandled.ContainsKey($Path)) { return }
    if (Test-Path -LiteralPath $Path) {
        $backup = "$Path.$script:settingsBackupTimestamp.bak"
        # Unlike Copy-Item, this overload atomically refuses an existing target.
        # A collision or copy failure must stop the caller before its source edit.
        [System.IO.File]::Copy($Path, $backup, $false)
        Write-Detail "backed up: $backup"
    }
    # Remember missing files too: a later mutation must not back up a file that
    # this run created with only its first settings change applied.
    $script:settingsBackupHandled[$Path] = $true
}

# Apply a mutation scriptblock to a JSON settings file, backing up and writing
# only when the mutation changes something.
function Update-JsonSettings {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Mutate,
        [switch]$CreateParent
    )
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent) -and -not $CreateParent) {
        Write-Detail "skip: $Label is not installed"
        return
    }
    $settings = Read-JsonFile $Path
    if ($null -eq $settings) { return }

    $before = ConvertTo-Stable $settings
    & $Mutate $settings
    $after = ConvertTo-Stable $settings

    if ($before -eq $after) {
        Write-Detail "ok: $Label already configured"
        return
    }
    if ($DryRun) {
        Write-Detail "would update: $Path"
        return
    }
    Backup-SettingsOnce $Path
    Ensure-Parent $Path
    Set-Content -LiteralPath $Path -Value $after -Encoding UTF8
    Write-Detail "configured: $Path"
}

# Keep Hermes configuration writes behind its CLI, never a YAML rewrite here.
function Invoke-HermesConfig {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $global:LASTEXITCODE = 0
    $output = & hermes @Arguments
    if (-not $? -or $LASTEXITCODE -ne 0) {
        throw "Hermes config command failed: $($Arguments -join ' ') (exit $LASTEXITCODE)"
    }
    return ($output -join "`n")
}

# Normalize only for comparison; preserve every existing list entry verbatim.
function Get-HermesComparisonPath {
    param([AllowEmptyString()][string]$Path, [string]$BasePath)
    $expanded = $Path.Trim()
    if ($IsWindows) { $expanded = [Environment]::ExpandEnvironmentVariables($expanded) }
    $expanded = [regex]::Replace($expanded, '\$\{(?<name>[^}]+)\}|\$(?<name>[A-Za-z_][A-Za-z0-9_]*)', {
        param($match)
        $value = [Environment]::GetEnvironmentVariable($match.Groups['name'].Value)
        if ($null -eq $value) { return $match.Value }
        return $value
    })
    if ($expanded.Length -eq 0) { $expanded = '.' }
    $expanded = Expand-Home $expanded
    return [IO.Path]::GetFullPath($expanded, $BasePath).TrimEnd('\', '/')
}

# -NoEnumerate distinguishes a JSON array from a scalar or nested array.
function ConvertFrom-HermesDirectories {
    param([AllowEmptyString()][string]$Json)
    if ($Json.Trim() -ceq 'null') { return ,@() }
    if ([string]::IsNullOrWhiteSpace($Json)) {
        throw 'Hermes skills.external_dirs must be a JSON list of strings (empty CLI output)'
    }
    $directories = ConvertFrom-Json -InputObject $Json -NoEnumerate
    if ($directories -isnot [array]) {
        throw 'Hermes skills.external_dirs must be a JSON list of strings'
    }
    foreach ($directory in $directories) {
        if ($directory -isnot [string]) {
            throw 'Hermes skills.external_dirs must be a JSON list of strings'
        }
    }
    return ,$directories
}

function Install-HermesSkills {
    $hermesHome = if (-not [string]::IsNullOrWhiteSpace($env:HERMES_HOME)) {
        $env:HERMES_HOME.Trim()
    } elseif ($IsWindows) {
        if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
            Join-Path $env:LOCALAPPDATA 'hermes'
        } else {
            Join-Path $HOME 'AppData/Local/hermes'
        }
    } else {
        Join-Path $HOME '.hermes'
    }
    $hermesHome = [IO.Path]::GetFullPath((Expand-Home $hermesHome), (Get-Location).ProviderPath)
    $config = Join-Path $hermesHome 'config.yaml'
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
        Write-Detail "skip: Hermes config does not exist: $config"
        return
    }
    if (-not (Get-Command hermes -ErrorAction SilentlyContinue)) {
        Write-Detail 'skip: Hermes CLI is not installed'
        return
    }
    $repoSkills = Resolve-Full $skillsDir
    if ($DryRun) {
        Write-Detail "would append $repoSkills to skills.external_dirs in $config (if not already present)"
        return
    }
    $previousHome = $env:HERMES_HOME
    try {
        # An explicit home also prevents Hermes from selecting a sticky profile.
        $env:HERMES_HOME = $hermesHome
        $comparer = if ($IsWindows) { [StringComparer]::OrdinalIgnoreCase } else { [StringComparer]::Ordinal }
        $cliConfig = Invoke-HermesConfig @('config', 'path')
        if (-not $comparer.Equals([IO.Path]::GetFullPath($cliConfig.Trim()), $config)) {
            throw "Hermes config path does not match selected config: $cliConfig (expected $config)"
        }
        $raw = Invoke-HermesConfig @('config', 'get', 'skills.external_dirs', '--json')
        $directories = ConvertFrom-HermesDirectories $raw
        $comparisonPath = Get-HermesComparisonPath $repoSkills $hermesHome
        foreach ($directory in $directories) {
            if ([string]::IsNullOrWhiteSpace($directory)) { continue }
            if ($comparer.Equals((Get-HermesComparisonPath $directory $hermesHome), $comparisonPath)) {
                Write-Detail 'ok: Hermes skills.external_dirs already includes repository skills'
                return
            }
        }
        $desired = @($directories) + @($repoSkills)
        $json = ConvertTo-Json -InputObject $desired -Compress
        Backup-SettingsOnce $config
        $null = Invoke-HermesConfig @('config', 'set', 'skills.external_dirs', $json)
        $actual = Invoke-HermesConfig @('config', 'get', 'skills.external_dirs', '--json')
        $verified = ConvertFrom-HermesDirectories $actual
        if ((ConvertTo-Json -InputObject $verified -Compress) -cne $json) {
            throw 'Hermes skills.external_dirs verification failed after config set'
        }
        Write-Detail "configured: $config (skills.external_dirs)"
    } finally {
        $env:HERMES_HOME = $previousHome
    }
}

# --- paths -----------------------------------------------------------------

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$skillsDir = Join-Path $repoRoot 'skills'
$agentsDir = Join-Path $repoRoot 'agents'
$agentsFile = Join-Path $repoRoot 'AGENTS.md'
$claudeStatuslineSource = Join-Path $repoRoot 'claude\statusline-command.ps1'
$cursorStatuslineSource = Join-Path $repoRoot 'cursor\statusline-command.ps1'

$claudeStatuslineLink = '~/.claude/statusline-command.ps1'
$cursorStatuslineLink = '~/.cursor/statusline-command.ps1'
$claudeSettings = Expand-Home '~/.claude/settings.json'
# Match Cursor CLI precedence; ignore empty/whitespace-only overrides.
$cursorConfigDir = if (-not [string]::IsNullOrWhiteSpace($env:CURSOR_CONFIG_DIR)) {
    $env:CURSOR_CONFIG_DIR
} elseif (-not [string]::IsNullOrWhiteSpace($env:XDG_CONFIG_HOME)) {
    Join-Path $env:XDG_CONFIG_HOME 'cursor'
} else {
    Expand-Home '~/.cursor'
}
$cursorSettings = Join-Path $cursorConfigDir 'cli-config.json'
$codexConfig = Expand-Home '~/.codex/config.toml'

# Status line commands each tool writes into its settings file.
$claudeStatuslineCommand = "pwsh -NoProfile -File `"$(Expand-Home $claudeStatuslineLink)`""
$cursorStatuslineCommand = "pwsh -NoProfile -File `"$(Expand-Home $cursorStatuslineLink)`""

# Per-skill targets: one junction per skill directory.
$perSkillTargets = @(
    '~/.claude/skills'
    '~/.cursor/skills'
    '~/.gemini/config/skills'
    '~/.copilot/skills'
    '~/.codex/skills'
    '~/.grok/skills'
)

# Per-agent targets: one file link per agent under agents/.
$perAgentTargets = @(
    '~/.claude/agents'
)

# Instruction-file targets: one file link to AGENTS.md each.
$instructionTargets = @(
    '~/.claude/AGENTS.md'
    '~/.codex/AGENTS.md'
    '~/.cursor/rules/AGENTS.md'
    '~/.gemini/GEMINI.md'
    '~/.grok/AGENTS.md'
)

# --- run -------------------------------------------------------------------

Write-Host "Source: $skillsDir"
if ($DryRun) { Write-Host '(dry run: nothing will be changed)' }

Write-Step 'Skill targets:'
$skillDirs = Get-ChildItem -LiteralPath $skillsDir -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf }
foreach ($target in $perSkillTargets) {
    $state = Prepare-RealDir $target $skillsDir
    if ($state -eq 'skip') { continue }
    if ($state -eq 'dry-migrate') {
        Write-Detail "would link each skill into $target"
        continue
    }
    foreach ($skill in $skillDirs) {
        Install-DirLink $skill.FullName "$target/$($skill.Name)"
    }
    Report-StaleSkills $target
}
# A tool that wrote through a whole-directory link from an older install
# leaves its content in skills/; report it rather than removing it.
Get-ChildItem -LiteralPath $skillsDir -Directory |
    Where-Object { -not (Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf) } |
    ForEach-Object { Write-Detail "note: non-skill directory left in place: $($_.Name)" }

Write-Step 'Claude agents:'
$agentFiles = Get-ChildItem -LiteralPath $agentsDir -Filter '*.md' |
    Where-Object { $_.Name -ne 'README.md' }
foreach ($target in $perAgentTargets) {
    $state = Prepare-RealDir $target $agentsDir
    if ($state -eq 'skip') { continue }
    if ($state -eq 'dry-migrate') {
        Write-Detail "would link each agent into $target"
        continue
    }
    foreach ($agent in $agentFiles) {
        Install-FileLink $agent.FullName "$target/$($agent.Name)"
    }
    Report-ExtraAgents $agentsDir $target
}

Write-Step 'Global instruction file:'
foreach ($target in $instructionTargets) {
    Install-FileLink $agentsFile $target
}

if ($NoStatusline) {
    Write-Step 'Status line: skipped (-NoStatusline).'
} else {
    Write-Step 'Status line:'
    Install-FileLink $claudeStatuslineSource $claudeStatuslineLink
    Update-JsonSettings $claudeSettings 'claude' {
        param($s)
        Set-Prop $s 'statusLine' ([pscustomobject]@{ type = 'command'; command = $claudeStatuslineCommand })
    }
    Install-FileLink $cursorStatuslineSource $cursorStatuslineLink
    Update-JsonSettings $cursorSettings 'cursor' -CreateParent {
        param($s)
        Set-Prop $s 'statusLine' ([pscustomobject]@{ type = 'command'; command = $cursorStatuslineCommand })
    }
}

if ($NoAttribution) {
    Write-Step 'Commit attribution: skipped (-NoAttribution).'
} else {
    Write-Step 'Commit attribution:'
    Update-JsonSettings $claudeSettings 'claude' {
        param($s)
        $attr = Get-OrCreateChild $s 'attribution'
        Set-Prop $attr 'commit' ''
        Set-Prop $attr 'pr' ''
        Set-Prop $attr 'sessionUrl' $false
    }
    Update-JsonSettings $cursorSettings 'cursor' {
        param($s)
        $attr = Get-OrCreateChild $s 'attribution'
        Set-Prop $attr 'attributeCommitsToAgent' $false
        Set-Prop $attr 'attributePRsToAgent' $false
    }
    # Codex stores config as TOML; set the top-level key with a line edit.
    if (Test-Path -LiteralPath (Split-Path -Parent $codexConfig)) {
        $desired = 'commit_attribution = ""'
        $text = if (Test-Path -LiteralPath $codexConfig) { Get-Content -LiteralPath $codexConfig -Raw } else { '' }
        if ($text -match '(?m)^\s*commit_attribution\s*=\s*""\s*$') {
            Write-Detail 'ok: codex already disables attribution'
        } elseif ($DryRun) {
            Write-Detail "would set commit_attribution in $codexConfig"
        } else {
            $lines = [System.Collections.Generic.List[string]]($text -split "\r?\n")
            $done = $false
            for ($i = 0; $i -lt $lines.Count; $i++) {
                $stripped = $lines[$i].TrimStart()
                if ($stripped.StartsWith('[')) { $lines.Insert($i, $desired); $done = $true; break }
                if ($stripped -match '^commit_attribution\s*=') { $lines[$i] = $desired; $done = $true; break }
            }
            if (-not $done) { $lines.Add($desired) }
            Backup-SettingsOnce $codexConfig
            Set-Content -LiteralPath $codexConfig -Value (($lines -join "`n").TrimEnd() + "`n") -Encoding UTF8
            Write-Detail "configured: $codexConfig"
        }
    } else {
        Write-Detail 'skip: codex is not installed'
    }
    Write-Detail 'note: gemini and grok document no attribution setting; nothing to change'
}

if ($NoHermes) {
    Write-Step 'Hermes skills: skipped (-NoHermes).'
} else {
    Write-Step 'Hermes skills:'
    Install-HermesSkills
}

if ($DryRun) {
    Write-Host 'Dry run: nothing was changed.'
} else {
    Write-Host 'Done.'
}
