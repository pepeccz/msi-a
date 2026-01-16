# =============================================================================
# MSI-a AI Skills Setup Script (PowerShell)
# =============================================================================
# Configures AI coding assistants that follow agentskills.io standard:
#   - Claude Code: .claude/skills/ symlink + CLAUDE.md copies
#   - Gemini CLI: .gemini/skills/ symlink + GEMINI.md copies
#   - Codex (OpenAI): .codex/skills/ symlink + AGENTS.md (native)
#   - GitHub Copilot: .github/copilot-instructions.md copy
#   - Cursor: .cursor/rules/ symlink + .cursorrules copy
#
# Usage:
#   .\setup.ps1              # Interactive mode (select AI assistants)
#   .\setup.ps1 -All         # Configure all AI assistants
#   .\setup.ps1 -Claude      # Configure only Claude Code
#   .\setup.ps1 -Claude -Cursor  # Configure multiple
#
# Note: Run as Administrator for symlink creation, or enable Developer Mode
# =============================================================================

[CmdletBinding()]
param(
    [switch]$All,
    [switch]$Claude,
    [switch]$Gemini,
    [switch]$Codex,
    [switch]$Copilot,
    [switch]$Cursor,
    [switch]$Help
)

# Script paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$SkillsSource = $ScriptDir

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

function Show-Help {
    Write-Host @"
Usage: .\setup.ps1 [OPTIONS]

Configure AI coding assistants for MSI-a development.

Options:
  -All       Configure all AI assistants
  -Claude    Configure Claude Code
  -Gemini    Configure Gemini CLI
  -Codex     Configure Codex (OpenAI)
  -Copilot   Configure GitHub Copilot
  -Cursor    Configure Cursor IDE
  -Help      Show this help message

If no options provided, runs in interactive mode.

Examples:
  .\setup.ps1                  # Interactive selection
  .\setup.ps1 -All             # All AI assistants
  .\setup.ps1 -Claude -Cursor  # Only Claude and Cursor

Note: Run as Administrator or enable Developer Mode for symlinks.
"@
}

function Show-Menu {
    $options = @(
        @{ Name = "Claude Code"; Selected = $true },
        @{ Name = "Gemini CLI"; Selected = $false },
        @{ Name = "Codex (OpenAI)"; Selected = $false },
        @{ Name = "GitHub Copilot"; Selected = $false },
        @{ Name = "Cursor IDE"; Selected = $false }
    )

    Write-Host "`nWhich AI assistants do you use?" -ForegroundColor White
    Write-Host "(Use numbers to toggle, Enter to confirm)" -ForegroundColor Cyan
    Write-Host ""

    while ($true) {
        for ($i = 0; $i -lt $options.Count; $i++) {
            $marker = if ($options[$i].Selected) { "[x]" } else { "[ ]" }
            $color = if ($options[$i].Selected) { "Green" } else { "Gray" }
            Write-Host "  $marker $($i + 1). $($options[$i].Name)" -ForegroundColor $color
        }
        Write-Host ""
        Write-Host "  a. Select all" -ForegroundColor Yellow
        Write-Host "  n. Select none" -ForegroundColor Yellow
        Write-Host ""
        
        $choice = Read-Host "Toggle (1-5, a, n) or Enter to confirm"

        switch ($choice) {
            "1" { $options[0].Selected = -not $options[0].Selected }
            "2" { $options[1].Selected = -not $options[1].Selected }
            "3" { $options[2].Selected = -not $options[2].Selected }
            "4" { $options[3].Selected = -not $options[3].Selected }
            "5" { $options[4].Selected = -not $options[4].Selected }
            "a" { $options | ForEach-Object { $_.Selected = $true } }
            "A" { $options | ForEach-Object { $_.Selected = $true } }
            "n" { $options | ForEach-Object { $_.Selected = $false } }
            "N" { $options | ForEach-Object { $_.Selected = $false } }
            "" { 
                return @{
                    Claude = $options[0].Selected
                    Gemini = $options[1].Selected
                    Codex = $options[2].Selected
                    Copilot = $options[3].Selected
                    Cursor = $options[4].Selected
                }
            }
            default { Write-Host "Invalid option" -ForegroundColor Red }
        }

        # Clear menu for redraw
        Clear-Host
        Write-Host "`n🤖 MSI-a AI Skills Setup" -ForegroundColor White
        Write-Host "========================`n"
        Write-Host "Found $SkillCount skills to configure" -ForegroundColor Blue
        Write-Host ""
        Write-Host "Which AI assistants do you use?" -ForegroundColor White
        Write-Host "(Use numbers to toggle, Enter to confirm)" -ForegroundColor Cyan
        Write-Host ""
    }
}

function New-SymlinkSafe {
    param(
        [string]$TargetDir,
        [string]$LinkPath,
        [string]$DisplayPath
    )

    # Create parent directory if needed
    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }

    # Handle existing link/directory
    if (Test-Path $LinkPath) {
        $item = Get-Item $LinkPath -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            # It's a symlink, remove it
            Remove-Item $LinkPath -Force
        } else {
            # It's a real directory, backup
            $backupPath = "$LinkPath.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Move-Item $LinkPath $backupPath
            Write-Host "  ! Backed up existing directory" -ForegroundColor Yellow
        }
    }

    # Create symlink
    try {
        New-Item -ItemType SymbolicLink -Path $LinkPath -Target $SkillsSource -Force | Out-Null
        Write-Host "  ✓ $DisplayPath -> skills/" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to create symlink. Run as Administrator or enable Developer Mode." -ForegroundColor Red
        Write-Host "    Error: $_" -ForegroundColor Red
    }
}

function Copy-AgentsMd {
    param([string]$TargetName)

    $count = 0
    $agentsFiles = Get-ChildItem -Path $RepoRoot -Filter "AGENTS.md" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch "node_modules|\.git" }

    foreach ($file in $agentsFiles) {
        $targetPath = Join-Path $file.DirectoryName $TargetName
        Copy-Item $file.FullName $targetPath -Force
        $count++
    }

    Write-Host "  ✓ Copied $count AGENTS.md -> $TargetName" -ForegroundColor Green
}

function Setup-Claude {
    $targetDir = Join-Path $RepoRoot ".claude"
    $linkPath = Join-Path $targetDir "skills"

    New-SymlinkSafe -TargetDir $targetDir -LinkPath $linkPath -DisplayPath ".claude/skills"
    Copy-AgentsMd -TargetName "CLAUDE.md"
}

function Setup-Gemini {
    $targetDir = Join-Path $RepoRoot ".gemini"
    $linkPath = Join-Path $targetDir "skills"

    New-SymlinkSafe -TargetDir $targetDir -LinkPath $linkPath -DisplayPath ".gemini/skills"
    Copy-AgentsMd -TargetName "GEMINI.md"
}

function Setup-Codex {
    $targetDir = Join-Path $RepoRoot ".codex"
    $linkPath = Join-Path $targetDir "skills"

    New-SymlinkSafe -TargetDir $targetDir -LinkPath $linkPath -DisplayPath ".codex/skills"
    Write-Host "  ✓ Codex uses AGENTS.md natively" -ForegroundColor Green
}

function Setup-Copilot {
    $targetDir = Join-Path $RepoRoot ".github"
    $targetFile = Join-Path $targetDir "copilot-instructions.md"
    $sourceFile = Join-Path $RepoRoot "AGENTS.md"

    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }

    if (Test-Path $sourceFile) {
        Copy-Item $sourceFile $targetFile -Force
        Write-Host "  ✓ AGENTS.md -> .github/copilot-instructions.md" -ForegroundColor Green
    } else {
        Write-Host "  ✗ AGENTS.md not found in repo root" -ForegroundColor Red
    }
}

function Setup-Cursor {
    $targetDir = Join-Path $RepoRoot ".cursor"
    $rulesPath = Join-Path $targetDir "rules"
    $cursorrules = Join-Path $RepoRoot ".cursorrules"
    $sourceFile = Join-Path $RepoRoot "AGENTS.md"

    # Create symlink for .cursor/rules/
    New-SymlinkSafe -TargetDir $targetDir -LinkPath $rulesPath -DisplayPath ".cursor/rules"

    # Copy AGENTS.md to .cursorrules
    if (Test-Path $sourceFile) {
        Copy-Item $sourceFile $cursorrules -Force
        Write-Host "  ✓ AGENTS.md -> .cursorrules" -ForegroundColor Green
    } else {
        Write-Host "  ✗ AGENTS.md not found in repo root" -ForegroundColor Red
    }
}

# =============================================================================
# MAIN
# =============================================================================

if ($Help) {
    Show-Help
    exit 0
}

Write-Host ""
Write-Host "🤖 MSI-a AI Skills Setup" -ForegroundColor White
Write-Host "========================"
Write-Host ""

# Count skills
$SkillCount = (Get-ChildItem -Path $SkillsSource -Filter "SKILL.md" -Recurse -Depth 1 -ErrorAction SilentlyContinue).Count

if ($SkillCount -eq 0) {
    Write-Host "No skills found in $SkillsSource" -ForegroundColor Red
    exit 1
}

Write-Host "Found $SkillCount skills to configure" -ForegroundColor Blue
Write-Host ""

# Determine what to setup
$SetupClaude = $Claude -or $All
$SetupGemini = $Gemini -or $All
$SetupCodex = $Codex -or $All
$SetupCopilot = $Copilot -or $All
$SetupCursor = $Cursor -or $All

# Interactive mode if no flags
if (-not ($SetupClaude -or $SetupGemini -or $SetupCodex -or $SetupCopilot -or $SetupCursor)) {
    $selections = Show-Menu
    $SetupClaude = $selections.Claude
    $SetupGemini = $selections.Gemini
    $SetupCodex = $selections.Codex
    $SetupCopilot = $selections.Copilot
    $SetupCursor = $selections.Cursor
}

# Check if anything selected
if (-not ($SetupClaude -or $SetupGemini -or $SetupCodex -or $SetupCopilot -or $SetupCursor)) {
    Write-Host "No AI assistants selected. Nothing to do." -ForegroundColor Yellow
    exit 0
}

# Count total steps
$Total = 0
if ($SetupClaude) { $Total++ }
if ($SetupGemini) { $Total++ }
if ($SetupCodex) { $Total++ }
if ($SetupCopilot) { $Total++ }
if ($SetupCursor) { $Total++ }

$Step = 1

# Run setups
if ($SetupClaude) {
    Write-Host "[$Step/$Total] Setting up Claude Code..." -ForegroundColor Yellow
    Setup-Claude
    $Step++
    Write-Host ""
}

if ($SetupGemini) {
    Write-Host "[$Step/$Total] Setting up Gemini CLI..." -ForegroundColor Yellow
    Setup-Gemini
    $Step++
    Write-Host ""
}

if ($SetupCodex) {
    Write-Host "[$Step/$Total] Setting up Codex (OpenAI)..." -ForegroundColor Yellow
    Setup-Codex
    $Step++
    Write-Host ""
}

if ($SetupCopilot) {
    Write-Host "[$Step/$Total] Setting up GitHub Copilot..." -ForegroundColor Yellow
    Setup-Copilot
    $Step++
    Write-Host ""
}

if ($SetupCursor) {
    Write-Host "[$Step/$Total] Setting up Cursor IDE..." -ForegroundColor Yellow
    Setup-Cursor
    Write-Host ""
}

# =============================================================================
# SUMMARY
# =============================================================================

Write-Host "✅ Successfully configured $SkillCount AI skills!" -ForegroundColor Green
Write-Host ""
Write-Host "Configured:"
if ($SetupClaude) { Write-Host "  • Claude Code:    .claude/skills/ + CLAUDE.md" }
if ($SetupGemini) { Write-Host "  • Gemini CLI:     .gemini/skills/ + GEMINI.md" }
if ($SetupCodex) { Write-Host "  • Codex (OpenAI): .codex/skills/ + AGENTS.md (native)" }
if ($SetupCopilot) { Write-Host "  • GitHub Copilot: .github/copilot-instructions.md" }
if ($SetupCursor) { Write-Host "  • Cursor IDE:     .cursor/rules/ + .cursorrules" }
Write-Host ""
Write-Host "Note: Restart your AI assistant to load the skills." -ForegroundColor Blue
Write-Host "      AGENTS.md is the source of truth - edit it, then re-run this script." -ForegroundColor Blue
Write-Host ""
