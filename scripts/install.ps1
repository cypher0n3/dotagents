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
    [switch]$NoAttribution
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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

# Apply a mutation scriptblock to a JSON settings file, backing up and writing
# only when the mutation changes something.
function Update-JsonSettings {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Mutate
    )
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
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
    if (Test-Path -LiteralPath $Path) {
        Copy-Item -LiteralPath $Path -Destination "$Path.bak" -Force
        Write-Detail "backed up: $Path.bak"
    }
    Set-Content -LiteralPath $Path -Value $after -Encoding UTF8
    Write-Detail "configured: $Path"
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
$cursorSettings = Expand-Home '~/.cursor/cli-config.json'
$codexConfig = Expand-Home '~/.codex/config.toml'

# Status line commands each tool writes into its settings file.
$claudeStatuslineCommand = "pwsh -NoProfile -File `"$(Expand-Home $claudeStatuslineLink)`""
$cursorStatuslineCommand = "pwsh -NoProfile -File `"$(Expand-Home $cursorStatuslineLink)`""

# Whole-directory targets: one junction to skills/.
$directoryTargets = @(
    '~/.claude/skills'
    '~/.cursor/skills'
    '~/.gemini/config/skills'
    '~/.copilot/skills'
)

# Per-skill targets: one junction per skill directory.
$perSkillTargets = @(
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

Write-Step 'Directory targets:'
foreach ($target in $directoryTargets) {
    Install-DirLink $skillsDir $target
}

Write-Step 'Per-skill targets:'
$skillDirs = Get-ChildItem -LiteralPath $skillsDir -Directory
foreach ($target in $perSkillTargets) {
    foreach ($skill in $skillDirs) {
        Install-DirLink $skill.FullName "$target/$($skill.Name)"
    }
}

Write-Step 'Claude agents:'
$agentFiles = Get-ChildItem -LiteralPath $agentsDir -Filter '*.md' |
    Where-Object { $_.Name -ne 'README.md' }
foreach ($target in $perAgentTargets) {
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
    Update-JsonSettings $cursorSettings 'cursor' {
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
            if (Test-Path -LiteralPath $codexConfig) {
                Copy-Item -LiteralPath $codexConfig -Destination "$codexConfig.bak" -Force
                Write-Detail "backed up: $codexConfig.bak"
            }
            Set-Content -LiteralPath $codexConfig -Value (($lines -join "`n").TrimEnd() + "`n") -Encoding UTF8
            Write-Detail "configured: $codexConfig"
        }
    } else {
        Write-Detail 'skip: codex is not installed'
    }
    Write-Detail 'note: gemini and grok document no attribution setting; nothing to change'
}

if ($DryRun) {
    Write-Host 'Dry run: nothing was changed.'
} else {
    Write-Host 'Done.'
}
