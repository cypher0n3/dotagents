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

    Copies can drift, and so can hard links: regenerating agents, or a git
    checkout that updates a file, replaces the file in this clone rather than
    editing it, which leaves the installed link holding the old content. The
    file path compares SHA-256 hashes: an identical file is reported as up to
    date and left alone. A file that differs is refreshed when its content is
    still what this installer last placed there, as recorded in
    install-state.json under %LOCALAPPDATA%\dotagents, and is otherwise
    replaced only when -Force is given. Pass -Copy to force the copy strategy
    for files even when a hard link would work.

    The agents generated from agent_sources/ are installed the same way as the
    Claude agents: one file per generated agent in ~/.codex/agents and
    ~/.cursor/agents. CAI personas are installed only by scripts/install.sh,
    because CAI's layout is Linux/XDG. Each generated Hermes personality is set
    in Hermes config through its CLI; one this installer did not set, or one
    changed since, is replaced only with -Force.

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
    Skip both Hermes steps: adding this repository's skills to
    skills.external_dirs, and setting the generated personalities.

.PARAMETER NoCodexAgents
    Skip installing the generated Codex agents.

.PARAMETER NoCursorAgents
    Skip installing the generated Cursor agents.

.PARAMETER NoHermesPersonalities
    Skip setting the generated Hermes personalities.

.PARAMETER NoCaiPersonas
    Skip the CAI personas step, which this installer reports as unsupported.

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
    [switch]$NoHermes,
    [switch]$NoCodexAgents,
    [switch]$NoCursorAgents,
    [switch]$NoHermesPersonalities,
    [switch]$NoCaiPersonas
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

# Per-user record of what this installer placed, so it can tell its own stale
# files and Hermes personalities from ones the user owns.
function Get-StatePath {
    $base = if ($IsWindows) {
        if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData/Local' }
    } elseif (-not [string]::IsNullOrWhiteSpace($env:XDG_STATE_HOME)) {
        $env:XDG_STATE_HOME.Trim()
    } else {
        Join-Path $HOME '.local/state'
    }
    return Join-Path (Join-Path $base 'dotagents') 'install-state.json'
}

function Get-InstallState {
    if ($null -ne $script:installState) { return $script:installState }
    $path = Get-StatePath
    $state = @{}
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        try {
            $parsed = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -AsHashtable
            if ($parsed -is [hashtable]) { $state = $parsed }
        } catch {
            Write-Detail "note: cannot read $path ($($_.Exception.Message)); treating nothing as installed by this script"
        }
    }
    foreach ($key in 'file_links', 'hermes_personalities') {
        if ($state[$key] -isnot [hashtable]) { $state[$key] = @{} }
    }
    $script:installState = $state
    return $state
}

function Save-InstallState {
    if ($DryRun -or -not $script:installStateChanged) { return }
    $path = Get-StatePath
    $parent = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $temp = "$path.tmp"
    [IO.File]::WriteAllText($temp, (ConvertTo-Json -InputObject $script:installState -Depth 10) + "`n")
    Move-Item -LiteralPath $temp -Destination $path -Force
}

function Set-InstallStateEntry {
    param([string]$Section, [string]$Key, $Value)
    $state = Get-InstallState
    if ($state[$Section][$Key] -ceq $Value) { return }
    $state[$Section][$Key] = $Value
    $script:installStateChanged = $true
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
    $stateKey = [System.IO.Path]::GetFullPath($link)
    $sourceSha = Get-Sha $source

    $sameVolume = (Get-Root $source) -ieq (Get-Root $stateKey)
    $useCopy = $Copy -or (-not $sameVolume)

    if (Test-Path -LiteralPath $link) {
        $item = Get-Item -LiteralPath $link -Force
        if ($item.PSIsContainer) {
            Write-Detail "skip: $link exists and is a directory"
            return
        }
        # A hard link to the same file, or a copy that still matches, shares the
        # source hash. Either way there is nothing to do.
        $linkSha = Get-Sha $link
        if ($linkSha -ieq $sourceSha) {
            Write-Detail "ok: $link (up to date)"
            if (-not $DryRun) { Set-InstallStateEntry 'file_links' $stateKey $sourceSha.ToLowerInvariant() }
            return
        }
        # Unchanged since this installer placed it, so only the source moved on,
        # as regenerating agents or a git checkout does.
        $recorded = (Get-InstallState)['file_links'][$stateKey]
        $stale = $recorded -and ($recorded -ieq $linkSha)
        if ($stale) {
            Write-Detail "refresh: $link (unchanged since this installer placed it; the source changed)"
        } elseif (-not $Force) {
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
            Set-InstallStateEntry 'file_links' $stateKey $sourceSha.ToLowerInvariant()
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
    Set-InstallStateEntry 'file_links' $stateKey $sourceSha.ToLowerInvariant()
}

# Report agent files in a target directory that this repository did not provide,
# and reparse points whose target is gone, removing nothing.
function Report-ExtraAgents {
    param(
        [Parameter(Mandatory)][string]$SourceDir,
        [Parameter(Mandatory)][string]$TargetDir,
        [string]$Filter = '*.md'
    )
    $target = Expand-Home $TargetDir
    if (-not (Test-Path -LiteralPath $target)) { return }

    $provided = @{}
    Get-ChildItem -LiteralPath $SourceDir -Filter $Filter |
        Where-Object { $_.Name -ne 'README.md' } |
        ForEach-Object { $provided[$_.Name] = $true }

    foreach ($entry in Get-ChildItem -LiteralPath $target -Filter $Filter -Force) {
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

function Get-HermesHome {
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
    return [IO.Path]::GetFullPath((Expand-Home $hermesHome), (Get-Location).ProviderPath)
}

# Return the Hermes config path, or $null after reporting why Hermes is skipped.
function Get-HermesConfig {
    param([Parameter(Mandatory)][string]$HermesHome)
    $config = Join-Path $HermesHome 'config.yaml'
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
        Write-Detail "skip: Hermes config does not exist: $config"
        return $null
    }
    if (-not (Get-Command hermes -ErrorAction SilentlyContinue)) {
        Write-Detail 'skip: Hermes CLI is not installed'
        return $null
    }
    return $config
}

function Assert-HermesConfigPath {
    param([string]$Config)
    $comparer = if ($IsWindows) { [StringComparer]::OrdinalIgnoreCase } else { [StringComparer]::Ordinal }
    $cliConfig = Invoke-HermesConfig @('config', 'path')
    if (-not $comparer.Equals([IO.Path]::GetFullPath($cliConfig.Trim()), $Config)) {
        throw "Hermes config path does not match selected config: $cliConfig (expected $Config)"
    }
}

function Install-HermesSkills {
    $hermesHome = Get-HermesHome
    $config = Get-HermesConfig $hermesHome
    if ($null -eq $config) { return }
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
        Assert-HermesConfigPath $config
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

# Read a generated personality: two lines, each a key and a JSON string.
function Read-PersonalityFile {
    param([Parameter(Mandatory)][string]$Path)
    $value = [ordered]@{}
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        $index = $line.IndexOf(': ')
        $key = if ($index -gt 0) { $line.Substring(0, $index) } else { '' }
        if ($key -notin 'description', 'system_prompt' -or $value.Contains($key)) {
            throw "${Path}: unexpected line"
        }
        $parsed = ConvertFrom-Json -InputObject $line.Substring($index + 2) -NoEnumerate
        if ($parsed -isnot [string]) { throw "${Path}: $key must be a string" }
        $value[$key] = $parsed
    }
    if ($value.Count -ne 2) { throw "${Path}: needs description and system_prompt" }
    return $value
}

# A personality this installer can own holds exactly description and system_prompt.
function Get-PersonalityDigest {
    param($Value)
    if ($Value -isnot [System.Collections.IDictionary] -or $Value.Count -ne 2 -or
        -not $Value.Contains('description') -or -not $Value.Contains('system_prompt') -or
        $Value['description'] -isnot [string] -or $Value['system_prompt'] -isnot [string]) {
        return $null
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value['description'] + [char]0 + $Value['system_prompt'])
    return 'sha256:' + [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}

function Test-PersonalityEqual {
    param($Current, $Desired)
    $digest = Get-PersonalityDigest $Current
    return $null -ne $digest -and $digest -ceq (Get-PersonalityDigest $Desired)
}

function Install-HermesPersonalities {
    $files = @(if (Test-Path -LiteralPath $hermesPersonalitiesDir) {
        Get-ChildItem -LiteralPath $hermesPersonalitiesDir -Filter '*.yaml' | Sort-Object Name
    })
    $hermesHome = Get-HermesHome
    $config = Get-HermesConfig $hermesHome
    if ($null -eq $config) { return }
    if ($files.Count -eq 0) {
        Write-Detail "skip: no generated personalities in $hermesPersonalitiesDir"
        return
    }
    $desired = [ordered]@{}
    foreach ($file in $files) { $desired[$file.BaseName] = Read-PersonalityFile $file.FullName }
    if ($DryRun) {
        foreach ($name in $desired.Keys) {
            Write-Detail "would set agent.personalities.$name in $config if absent or owned by this installer"
        }
        return
    }
    $previousHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $hermesHome
        Assert-HermesConfigPath $config
        $raw = Invoke-HermesConfig @('config', 'get', 'agent.personalities', '--json')
        $current = if ([string]::IsNullOrWhiteSpace($raw) -or $raw.Trim() -ceq 'null') { @{} } else {
            ConvertFrom-Json -InputObject $raw -AsHashtable -NoEnumerate
        }
        if ($current -isnot [System.Collections.IDictionary]) {
            throw 'Hermes agent.personalities must be a mapping'
        }
        $state = Get-InstallState
        $key = [IO.Path]::GetFullPath($config)
        if ($state['hermes_personalities'][$key] -isnot [hashtable]) { $state['hermes_personalities'][$key] = @{} }
        $owned = $state['hermes_personalities'][$key]
        foreach ($name in $desired.Keys) {
            $value = $desired[$name]
            $digest = Get-PersonalityDigest $value
            $existing = if ($current.Contains($name)) { $current[$name] } else { $null }
            if (Test-PersonalityEqual $existing $value) {
                Write-Detail "ok: personality $name is current"
                if ($owned[$name] -cne $digest) { $owned[$name] = $digest; $script:installStateChanged = $true }
                continue
            }
            $recorded = $owned[$name]
            if ($null -eq $existing) {
                $action = 'added'
            } elseif ($recorded -and (Get-PersonalityDigest $existing) -ceq $recorded) {
                $action = 'updated'
            } elseif ($Force) {
                $action = 'replaced (-Force; the previous value is in the config backup)'
            } else {
                Write-Detail "skip: personality $name exists and was not set by this installer, or was changed since (use -Force to replace)"
                continue
            }
            Backup-SettingsOnce $config
            $json = ConvertTo-Json -InputObject $value -Compress
            $null = Invoke-HermesConfig @('config', 'set', "agent.personalities.$name", $json)
            $actual = Invoke-HermesConfig @('config', 'get', "agent.personalities.$name", '--json')
            $verified = if ([string]::IsNullOrWhiteSpace($actual)) { $null } else {
                ConvertFrom-Json -InputObject $actual -AsHashtable -NoEnumerate
            }
            if (-not (Test-PersonalityEqual $verified $value)) {
                throw "Hermes agent.personalities.$name verification failed after config set"
            }
            $owned[$name] = $digest
            $script:installStateChanged = $true
            Write-Detail "${action}: personality $name"
        }
        foreach ($name in @($owned.Keys | Sort-Object)) {
            if ($desired.Contains($name)) { continue }
            if ($current.Contains($name)) {
                Write-Detail "note: personality $name was set by this installer, but its role no longer exists; left in place for you to remove"
            } else {
                $owned.Remove($name)
                $script:installStateChanged = $true
            }
        }
    } finally {
        $env:HERMES_HOME = $previousHome
    }
}

# --- paths -----------------------------------------------------------------

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$skillsDir = Join-Path $repoRoot 'skills'
$agentsDir = Join-Path $repoRoot 'agents'
$agentsFile = Join-Path $repoRoot 'AGENTS.md'
$generatedDir = Join-Path $repoRoot 'generated'
$hermesPersonalitiesDir = Join-Path $generatedDir 'hermes/personalities'
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

$script:installState = $null
$script:installStateChanged = $false

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

# Generated agents for other tools, one file each, like the Claude agents.
$generatedTargets = @(
    @{ Label = 'Codex agents'; Switch = 'NoCodexAgents'; Skip = $NoCodexAgents
       Source = (Join-Path $generatedDir 'codex/agents'); Target = '~/.codex/agents'; Filter = '*.toml' }
    @{ Label = 'Cursor agents'; Switch = 'NoCursorAgents'; Skip = $NoCursorAgents
       Source = (Join-Path $generatedDir 'cursor/agents'); Target = '~/.cursor/agents'; Filter = '*.md' }
)
foreach ($generated in $generatedTargets) {
    Write-Step "$($generated.Label):"
    if ($generated.Skip) {
        Write-Detail "skipped (-$($generated.Switch))."
        continue
    }
    $files = @(if (Test-Path -LiteralPath $generated.Source) {
        Get-ChildItem -LiteralPath $generated.Source -Filter $generated.Filter | Sort-Object Name
    })
    if ($files.Count -eq 0) {
        Write-Detail "skip: no generated files in $($generated.Source)"
        continue
    }
    $state = Prepare-RealDir $generated.Target $generated.Source
    if ($state -eq 'skip') { continue }
    if ($state -eq 'dry-migrate') {
        Write-Detail "would link each file into $($generated.Target)"
        continue
    }
    foreach ($file in $files) {
        Install-FileLink $file.FullName "$($generated.Target)/$($file.Name)"
    }
    Report-ExtraAgents $generated.Source $generated.Target $generated.Filter
}

Write-Step 'CAI personas:'
if ($NoCaiPersonas) {
    Write-Detail 'skipped (-NoCaiPersonas).'
} else {
    Write-Detail 'skip: CAI personas follow the Linux/XDG layout; install them with scripts/install.sh'
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
    Write-Step 'Hermes personalities: skipped (-NoHermes).'
} else {
    Write-Step 'Hermes skills:'
    Install-HermesSkills
    if ($NoHermesPersonalities) {
        Write-Step 'Hermes personalities: skipped (-NoHermesPersonalities).'
    } else {
        Write-Step 'Hermes personalities:'
        Install-HermesPersonalities
    }
}

Save-InstallState

if ($DryRun) {
    Write-Host 'Dry run: nothing was changed.'
} else {
    Write-Host 'Done.'
}
