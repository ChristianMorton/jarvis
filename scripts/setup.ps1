# Jarvis — one-shot Windows setup.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#
# Creates a venv, installs dependencies, downloads the speech model and
# writes a starter jarvis.yaml. Safe to re-run.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Jarvis setup" -ForegroundColor Cyan
Write-Host "  project: $root"

# --- python ---------------------------------------------------------------
$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) { $py = "py"; $pyArgs = @("-3") } else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw "Python 3.10+ not found. Install it from python.org or the Microsoft Store." }
    $py = "python"; $pyArgs = @()
}

if (-not (Test-Path ".venv")) {
    Write-Host "`ncreating .venv" -ForegroundColor Cyan
    & $py @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Creating the virtual environment failed." }
}
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "`ninstalling dependencies" -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { throw "Setup failed; see the command output above." }
& $venvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Setup failed; see the command output above." }

# --- speech model ---------------------------------------------------------
Write-Host "`ndownloading the speech model (~40 MB)" -ForegroundColor Cyan
& $venvPython -m jarvis download-model small-en-us
if ($LASTEXITCODE -ne 0) { throw "Setup failed; see the command output above." }

# --- config ---------------------------------------------------------------
if (-not (Test-Path "jarvis.yaml")) {
    Write-Host "`nwriting jarvis.yaml" -ForegroundColor Cyan
    & $venvPython -m jarvis init
    if ($LASTEXITCODE -ne 0) { throw "Setup failed; see the command output above." }
} else {
    Write-Host "`njarvis.yaml already exists, leaving it alone" -ForegroundColor DarkGray
}

Write-Host "`nchecking the install" -ForegroundColor Cyan
& $venvPython -m jarvis doctor
if ($LASTEXITCODE -ne 0) { throw "Setup failed; see the command output above." }

Write-Host @"

Done. Next:

  1. Open jarvis.yaml and set vars.wispr_hotkey to whatever you have bound
     in Wispr Flow's own settings.
  2. Start it:      .\scripts\run.ps1
     Or try it dry: .\scripts\run.ps1 -DryRun

"@ -ForegroundColor Green
