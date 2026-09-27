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

.PARAMETER DataRoot
  Directory that will hold caiji_wei / tilian_wei / gengxin_wei. Use this to
  keep the knowledge data outside the repo (and outside any harness dir) so
  every harness shares one copy. Default: the repo root.

.PARAMETER ForceXinxi
  Overwrite an existing xinxi.txt whose contents differ. Without this, install
  keeps the existing file and warns, so a rerun cannot silently repoint your
  knowledge base at an empty directory.
#>
param(
  [ValidateSet('Link', 'Copy')]
  [string]$Mode = 'Link',
  [switch]$Force,
  [string]$SkillsRoot = '',
  [switch]$SkipXinxi,
  [switch]$SkipLink,
  [string]$DataRoot = '',
  [switch]$ForceXinxi
)

# Console may default to a legacy codepage; force UTF-8 so Chinese output is readable.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
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

function Write-XinxiFiles([string]$RootWin, [string]$RootLinux) {
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
    $text = $text.Replace('{{DATA_WIN}}', "$RootWin/$($p.Key)").Replace('{{DATA_LINUX}}', "$RootLinux/$($p.Key)")
    # Normalize newlines
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
    $text = $text.TrimEnd() + "`n"

    if (Test-Path -LiteralPath $out) {
      $old = (Get-Content -LiteralPath $out -Raw -Encoding UTF8)
      $old = ($old -replace "`r`n", "`n" -replace "`r", "`n")
      if ($old -ne $text -and -not $ForceXinxi) {
        Write-Warning "$out already points somewhere else; keeping it."
        Write-Warning "  (rerun with -ForceXinxi to overwrite with: $RootWin/$($p.Key))"
        continue
      }
    }
    [System.IO.File]::WriteAllText($out, $text)
    Write-Host "wrote   $out"
  }
}

# --- xinxi ---
# $DataRoot overrides where the knowledge data lives (default: repo root).
$dataWinSource = if ($DataRoot) { (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Path $DataRoot -Force).FullName).Path } else { $SrcRoot }
$dataWin = Get-RepoWinPath $dataWinSource
# Dual-boot / WSL style mapping used by this project family:
#   C:/Users/xi/...  ->  /media/xi/系统/Users/xi/...
if ($dataWin -match '^C:/(.*)$') {
  $dataLinux = '/media/xi/系统/' + $Matches[1]
} elseif ($dataWin -match '^([A-Za-z]):/(.*)$') {
  $d = $Matches[1].ToLower()
  $dataLinux = "/mnt/$d/$($Matches[2])"
} else {
  $dataLinux = $dataWin
}

if (-not $SkipXinxi) {
  foreach ($k in @('caiji_wei', 'tilian_wei', 'gengxin_wei')) {
    New-Item -ItemType Directory -Path (Join-Path $dataWinSource $k) -Force | Out-Null
  }
  Write-XinxiFiles -RootWin $dataWin -RootLinux $dataLinux
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
Write-Host "  data roots : $(if ($DataRoot) { $DataRoot } else { $SrcRoot })"
Write-Host "  skills root: $SkillsRoot"
Write-Host "  triggers   : 「使用知识库系统」 / 「开启知识库系统模式」"
Write-Host "reopen the pi session to load skills."
