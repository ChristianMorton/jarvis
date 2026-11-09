# Start Jarvis.
#   .\scripts\run.ps1            listen and act
#   .\scripts\run.ps1 -DryRun    listen and print, but send nothing
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "No .venv here. Run scripts\setup.ps1 first."
}

$jarvisArgs = @("-m", "jarvis", "run")
if ($DryRun) { $jarvisArgs += "--dry-run" }
& $venvPython @jarvisArgs
