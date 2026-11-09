# Start Jarvis automatically at logon, with no console window.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-startup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-startup.ps1 -Remove
#
# Uses a Scheduled Task rather than the Startup folder so it can run without
# flashing a terminal. It runs as you, at your normal privilege level —
# Jarvis synthesises input, so it must not be elevated unless you also want
# it driving elevated windows (Windows blocks input from a lower integrity
# level to a higher one, which is why an un-elevated Jarvis cannot type into
# an admin PowerShell).

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$taskName = "Jarvis Voice Control"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$taskName'." -ForegroundColor Green
    return
}

$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "No .venv here. Run scripts\setup.ps1 first." }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m jarvis run" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null

Write-Host @"
Registered '$taskName' — Jarvis will start at logon.

  Stop it now:  Stop-ScheduledTask -TaskName '$taskName'
  Start it now: Start-ScheduledTask -TaskName '$taskName'
  Remove it:    .\scripts\install-startup.ps1 -Remove

With no console, the only feedback is the beeps. While you are still tuning
commands, run it in a terminal instead so you can see what it hears.
"@ -ForegroundColor Green
