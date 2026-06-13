$taskName = "UniversalJobBot_247"
$botScript = "E:\SivaShankar\jobbot\bot\main.py"
$workDir = "E:\SivaShankar\jobbot"
$logFile = "E:\SivaShankar\jobbot\data\bot_startup.log"

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$pythonExe = if ($pythonCmd) { $pythonCmd.Source } else { $null }

if (-not $pythonExe) {
    Write-Host "Python not found in PATH!" -ForegroundColor Red
    exit 1
}

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $botScript -WorkingDirectory $workDir

$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$triggerHourly  = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At (Get-Date)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -ExecutionTimeLimit 0 -Priority 4

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggerStartup -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Task Registered successfully." -ForegroundColor Green

Write-Host "Installing dependencies..."
& $pythonExe -m pip install -r "$workDir\requirements.txt" --quiet
& $pythonExe -m playwright install chromium

$dataDir = "$workDir\data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }
if (-not (Test-Path "$dataDir\applications.json")) { "[]" | Out-File "$dataDir\applications.json" -Encoding utf8 }
if (-not (Test-Path "$dataDir\logs.json")) { "[]" | Out-File "$dataDir\logs.json" -Encoding utf8 }

$startNow = Read-Host "Start the bot RIGHT NOW? (Y/N)"
if ($startNow -match "^[Yy]") {
    Start-ScheduledTask -TaskName $taskName
    Start-Sleep -Seconds 3
    $status = (Get-ScheduledTask -TaskName $taskName).State
    Write-Host "Bot status: $status" -ForegroundColor Cyan
}
