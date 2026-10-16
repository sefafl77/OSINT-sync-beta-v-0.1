<#
Set up the CTI Expert tool server for Codex on Windows.
Creates a repository-local Python environment and project MCP configuration.
No model API key or Claude SDK is installed or requested.
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Continue'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..') -ErrorAction Stop).Path
$Venv = Join-Path $Repo '.venv'
$Python = Join-Path $Venv 'Scripts\python.exe'
$CodexDir = Join-Path $Repo '.codex'
$Config = Join-Path $CodexDir 'config.toml'
$Requirements = Join-Path $Repo 'requirements.txt'
$CollectorRequirements = Join-Path $Repo 'scripts\requirements.txt'
$Server = Join-Path $Repo 'intel_engine\harness\mcp_server.py'

if (-not (Test-Path $Python)) {
$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 -m venv $Venv
} else {
    $launcher = Get-Command python -ErrorAction SilentlyContinue
    if (-not $launcher) { throw 'Python 3 was not found. Install Python 3.11+ and rerun this script.' }
    & $launcher.Source -m venv $Venv
}
if ($LASTEXITCODE -ne 0) { throw 'Could not create the repository-local Python environment.' }
}

& $Python -X utf8 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Codex native setup requires Python 3.11+.' }
Write-Host '[1/3] Menyiapkan dependency runtime lokal...'
& $Python -m pip install --quiet --disable-pip-version-check -r $Requirements
if ($LASTEXITCODE -ne 0) { throw 'Could not install CTI Expert dependencies.' }
& $Python -m pip install --quiet --disable-pip-version-check -r $CollectorRequirements
if ($LASTEXITCODE -ne 0) { throw 'Could not install OSINT collector dependencies.' }

Write-Host '[2/3] Memeriksa config project Codex...'
& $Python -X utf8 (Join-Path $Repo 'scripts\codex_runtime.py') configure --repo $Repo --python $Python
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the project MCP server. Existing settings were preserved.' }
Write-Host '[3/3] Memeriksa tool server lokal...'
& $Python -X utf8 (Join-Path $Repo 'cti.py') --doctor
if ($LASTEXITCODE -ne 0) { throw 'A required runtime check failed. Review the message above.' }

Write-Host ''
Write-Host 'Codex MCP setup is ready.' -ForegroundColor Green
Write-Host "Config: $Config"
Write-Host 'Restart Codex, open this repository, and approve/trust it when prompted.'
Write-Host 'Guided menu: double-click Mulai CTI.cmd, or run python cti.py.'
Write-Host 'The Codex project config is gitignored because it contains local absolute paths.'
