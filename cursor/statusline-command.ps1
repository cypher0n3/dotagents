# Cursor CLI status line: current dir, git branch, model and effort
# summary, context % with a bar, and Cursor models / API % used.
# Colors are chosen to read well when the terminal dims the status line.
#
# PowerShell version of statusline-command.sh
# NOTE TO AGENTS: this file is user-managed configuration. Do not edit it
# unless the user has explicitly directed you to change the status line.

# Color codes
$RESET = "`e[0m"
$DIM = "`e[2m"
$BLUE = "`e[1;34m"
$GREEN = "`e[32m"
$YELLOW = "`e[33m"
$RED = "`e[31m"
$MAGENTA = "`e[35m"
$CYAN = "`e[36m"

# Get current directory (shortened)
function Get-ShortPath {
    $cwd = Get-Location
    $home = [System.IO.Path]::Combine($env:USERPROFILE)
    
    if ($cwd.Path.StartsWith($home)) {
        $short = "~" + $cwd.Path.Substring($home.Length)
    } else {
        $short = $cwd.Path
    }
    
    # Truncate if too long
    if ($short.Length -gt 30) {
        $short = "..." + $short.Substring($short.Length - 27)
    }
    
    return $short
}

# Get git branch
function Get-GitBranch {
    try {
        if (git rev-parse --git-dir 2>$null) {
            $branch = git rev-parse --abbrev-ref HEAD 2>$null
            return $branch
        }
    } catch { }
    
    return $null
}

# Pick a color for a percentage
function Get-ColorForPercentage {
    param([int]$Percentage)
    
    if ($Percentage -lt 70) {
        return $GREEN
    } elseif ($Percentage -lt 90) {
        return $YELLOW
    } else {
        return $RED
    }
}

# 10-character bar for a percentage
function Get-PercentageBar {
    param([int]$Percentage)
    
    $percentage = [Math]::Min([Math]::Max($Percentage, 0), 100)
    $filled = [Math]::Floor($percentage / 10)
    
    $bar = ""
    for ($i = 0; $i -lt $filled; $i++) {
        $bar += "█"
    }
    for ($i = $filled; $i -lt 10; $i++) {
        $bar += "░"
    }
    
    return $bar
}

# Build the status line
$path = Get-ShortPath
$branch = Get-GitBranch
$contextPercent = 0  # Would need Cursor API integration
$apiPercent = 0      # Would need Cursor API integration

$statusLine = "$BLUE$path"

if ($branch) {
    $statusLine += " $DIM($CYAN$branch$DIM)$RESET"
}

# Model and context would require integration with Cursor
# For now, show a basic status line
$statusLine += " $RESET"

Write-Host $statusLine -NoNewline
