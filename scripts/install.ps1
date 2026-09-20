param(
  [string]$AgentsSkillRoot = (Join-Path $env:USERPROFILE '.agents\skills'),
  [string]$CodexSkillRoot = (Join-Path $env:USERPROFILE '.codex\skills'),
  [switch]$SkipPlaywright
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$scholar = Join-Path $repo 'scholar-slides'
$paper = Join-Path $repo 'paper-tutor'
if (!(Test-Path (Join-Path $scholar 'SKILL.md'))) { throw "scholar-slides package is missing" }
if (!(Test-Path (Join-Path $paper 'SKILL.md'))) { throw "paper-tutor package is missing" }
$agentsRoot = [IO.Path]::GetFullPath($AgentsSkillRoot)
$codexRoot = [IO.Path]::GetFullPath($CodexSkillRoot)
New-Item -ItemType Directory -Force $agentsRoot,$codexRoot | Out-Null
$destScholar = Join-Path $agentsRoot 'scholar-slides'
$destPaper = Join-Path $codexRoot 'paper-tutor'
$backup = Join-Path ([IO.Path]::GetDirectoryName($agentsRoot)) ("skill-backup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $backup | Out-Null
foreach($pair in @(@($destScholar,(Join-Path $backup 'scholar-slides')), @($destPaper,(Join-Path $backup 'paper-tutor')))) {
  if (Test-Path $pair[0]) { Copy-Item -Recurse -Force $pair[0] $pair[1] }
}
if (Test-Path $destScholar) { Remove-Item -Recurse -Force $destScholar }
if (Test-Path $destPaper) { Remove-Item -Recurse -Force $destPaper }
Copy-Item -Recurse -Force $scholar $destScholar
Copy-Item -Recurse -Force $paper $destPaper
$runtime = Join-Path $destScholar 'runtime'
$venv = Join-Path $runtime '.venv'
if (!(Test-Path (Join-Path $venv 'Scripts\python.exe'))) { python -m venv $venv }
& (Join-Path $venv 'Scripts\python.exe') -m pip install -r (Join-Path $runtime 'requirements-runtime.txt')
Push-Location $runtime
try {
  npm ci
  if (!$SkipPlaywright) { npx playwright install chromium }
} finally { Pop-Location }
Write-Output ("Installed Scholar-Slides to {0}" -f $destScholar)
Write-Output ("Installed Paper-Tutor to {0}" -f $destPaper)
Write-Output ("Previous installations backed up at {0}" -f $backup)
