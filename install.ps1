#Requires -Version 5.1
<#
.SYNOPSIS
  Install lanren-zhishiku skills into the pi skills directory and write xinxi.txt.

.PARAMETER Mode
  Link (default) or Copy

.PARAMETER Force
  Replace existing same-named skills under SkillsRoot

.PARAMETER SkillsRoot
  Override default ~/.pi/agent/skills

.PARAMETER SkipXinxi
  Do not regenerate xinxi.txt from examples
#>
param(
  [ValidateSet('Link', 'Copy')]
  [string]$Mode = 'Link',
  [switch]$Force,
  [string]$SkillsRoot = '',
  [switch]$SkipXinxi,
  [switch]$SkipLink
)

$ErrorActionPreference = 'Stop'
$SrcRoot = $PSScriptRoot
if (-not $SkillsRoot) {
  $SkillsRoot = Join-Path $env:USERPROFILE '.pi\agent\skills'
}

$Names = @(
  'zhishiku-caiji',
  'zhishiku-tilian',
  'zhishiku-gengxin',
  'zhishiku-chuli'
)

function Get-RepoWinPath([string]$Root) {
  $p = (Resolve-Path -LiteralPath $Root).Path
  return ($p -replace '\\', '/')
}

function Write-XinxiFiles([string]$RepoWin, [string]$RepoLinux) {
  $pairs = @(
    @{ Dir = 'zhishiku-caiji'; Key = 'caiji_wei' },
    @{ Dir = 'zhishiku-tilian'; Key = 'tilian_wei' },
    @{ Dir = 'zhishiku-gengxin'; Key = 'gengxin_wei' }
  )
  foreach ($p in $pairs) {
    $example = Join-Path $SrcRoot (Join-Path $p.Dir 'xinxi.txt.example')
    $out = Join-Path $SrcRoot (Join-Path $p.Dir 'xinxi.txt')
    if (-not (Test-Path -LiteralPath $example)) {
      Write-Warning "missing example: $example"
      continue
    }
    $text = Get-Content -LiteralPath $example -Raw -Encoding UTF8
    $text = $text.Replace('{{REPO_WIN}}', $RepoWin).Replace('{{REPO_LINUX}}', $RepoLinux)
    # Normalize newlines
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
    [System.IO.File]::WriteAllText($out, $text.TrimEnd() + "`n")
    Write-Host "wrote   $out"
  }
}

# --- xinxi ---
$repoWin = Get-RepoWinPath $SrcRoot
# Dual-boot / WSL style mapping used by this project family:
#   C:/Users/xi/...  ->  /media/xi/系统/Users/xi/...
if ($repoWin -match '^C:/(.*)$') {
  $repoLinux = '/media/xi/系统/' + $Matches[1]
} elseif ($repoWin -match '^([A-Za-z]):/(.*)$') {
  $d = $Matches[1].ToLower()
  $repoLinux = "/mnt/$d/$($Matches[2])"
} else {
  $repoLinux = $repoWin
}

if (-not $SkipXinxi) {
  Write-XinxiFiles -RepoWin $repoWin -RepoLinux $repoLinux
}

# --- link / copy into pi skills ---
if ($SkipLink) {
  Write-Host 'skip link/copy (-SkipLink)'
} else {
  if (-not (Test-Path -LiteralPath $SkillsRoot)) {
    New-Item -ItemType Directory -Path $SkillsRoot -Force | Out-Null
    Write-Host "created skills root: $SkillsRoot"
  }

  foreach ($n in $Names) {
    $src = Join-Path $SrcRoot $n
    $dst = Join-Path $SkillsRoot $n
    if (-not (Test-Path -LiteralPath $src)) {
      Write-Warning "skip missing source: $src"
      continue
    }
    if (Test-Path -LiteralPath $dst) {
      if ($Force) {
        Write-Host "removing existing: $dst"
        Remove-Item -LiteralPath $dst -Recurse -Force
      } else {
        Write-Warning "exists, skip (use -Force to replace): $dst"
        continue
      }
    }
    if ($Mode -eq 'Link') {
      try {
        New-Item -ItemType SymbolicLink -Path $dst -Target $src | Out-Null
        Write-Host "linked  $dst  ->  $src"
      } catch {
        Write-Warning "symlink failed ($($_.Exception.Message)); retry with: .\install.ps1 -Mode Copy"
        throw
      }
    } else {
      Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
      Write-Host "copied  $src  ->  $dst"
    }
  }
}

Write-Host ""
Write-Host "done."
Write-Host "  data roots : $SrcRoot"
Write-Host "  skills root: $SkillsRoot"
Write-Host "  triggers   : 「使用知识库系统」 / 「开启知识库系统模式」"
Write-Host "reopen the pi session to load skills."
