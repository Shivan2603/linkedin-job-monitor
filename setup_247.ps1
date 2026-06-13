# setup_247.ps1 — Register the Job Bot to run 24/7 automatically
# Sets up a highly resilient Windows Scheduled Task.

$taskName = "LinkedInJobBot_247"
$botPath = "E:\SivaShankar\jobbot\bot\main.py"
$pythonExe = (Get-Command python).Source

if (-not $pythonExe) {
    Write-Host "Python not found! Please ensure python is in your PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Registering Universal Job Bot Task: $taskName" -ForegroundColor Cyan

# 1. Action: run Python with main.py
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $botPath -WorkingDirectory "E:\SivaShankar\jobbot"

# 2. Trigger: Run on startup and repeat indefinitely (every 1 hour)
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.RepetitionInterval = (New-TimeSpan -Hours 1)
$trigger.RepetitionDuration = [TimeSpan]::MaxValue

# 3. Settings: Restart on failure, do not start a new instance if one is running
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew

# 4. Register
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -User $env:USERNAME -Force

Write-Host "✅ Task registered successfully! The bot will now run on system startup and loop continuously." -ForegroundColor Green
Write-Host "To view or manage the task, open 'Task Scheduler' and look for '$taskName'."
