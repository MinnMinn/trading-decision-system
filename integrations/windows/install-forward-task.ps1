# Registers the forward cycle (scripts/forward_cycle.py) as a Windows scheduled task every 5 minutes.
# Run ONCE from the repository root in PowerShell:   powershell -ExecutionPolicy Bypass -File integrations\windows\install-forward-task.ps1
# Remove with:                                       Unregister-ScheduledTask -TaskName "TYME Forward Cycle" -Confirm:$false
# The task runs as the logged-in user (MetaTrader 5 and its Common\Files bridge live in that user's profile) and only while
# that user is logged on -- the same condition under which the MT5 terminal itself runs.
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command py -ErrorAction Stop).Source; $Args = "-3 `"$Repo\scripts\forward_cycle.py`"" }
else { $Args = "`"$Repo\scripts\forward_cycle.py`"" }
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Args -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
            -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "TYME Forward Cycle" -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "TYME trading: MT5 sync, forward paper log, DEMO executor (scripts/forward_cycle.py)" -Force | Out-Null
Write-Host "Registered 'TYME Forward Cycle' every 5 minutes: $Python $Args (in $Repo)"
Write-Host "Log: $Repo\data\live\forward\cycle.log"
