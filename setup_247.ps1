# setup_247.ps1 — Register the Universal Job Bot for 24/7 Operation
# Run as Administrator for best results.
# Registers a highly resilient Windows Scheduled Task that:
#   - Starts automatically on system boot
#   - Restarts automatically on failure (3x, every 5 min)
#   - Prevents duplicate instances from running in parallel
#   - Runs with highest privileges for network access
#   - Continues even when running on battery

$taskName     = "UniversalJobBot_247"
$botScript    = "E:\SivaShankar\jobbot\bot\main.py"
$workDir      = "E:\SivaShankar\jobbot"
$logFile      = "E:\SivaShankar\jobbot\data\bot_startup.log"
$pythonExe    = (Get-Command python -ErrorAction SilentlyContinue)?.Source

# ── Validate Python ──────────────────────────────────────────────────────────
if (-not $pythonExe) {
    Write-Host "❌ Python not found in PATH!" -ForegroundColor Red
    Write-Host "   Install Python 3.10+ and add it to PATH, then re-run this script." -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ Python found at: $pythonExe" -ForegroundColor Green

# ── Check for existing task ──────────────────────────────────────────────────
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "⚠️  Existing task '$taskName' found — replacing..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# ── Build Task Components ────────────────────────────────────────────────────

# Action: run Python with main.py, redirect output to log file
$actionArgs = "`"$botScript`" >> `"$logFile`" 2>&1"
$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument $actionArgs `
    -WorkingDirectory $workDir

# Triggers: (1) On Startup, (2) Fallback every 2 hours
$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$triggerHourly  = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At (Get-Date)

# Settings: resilient, background, no duplicates
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -Priority 4

# Principal: run as current user, highest privileges
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

# ── Register Task ────────────────────────────────────────────────────────────
try {
    Register-ScheduledTask `
        -TaskName  $taskName `
        -Action    $action `
        -Trigger   $triggerStartup `
        -Settings  $settings `
        -Principal $principal `
        -Force | Out-Null

    Write-Host ""
    Write-Host "════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  ✅ Universal Job Bot Task Registered!" -ForegroundColor Green
    Write-Host "════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Task Name   : $taskName" -ForegroundColor White
    Write-Host "  Script      : $botScript" -ForegroundColor White
    Write-Host "  Python      : $pythonExe" -ForegroundColor White
    Write-Host "  Trigger     : On system startup + every 2 hours" -ForegroundColor White
    Write-Host "  Restart     : Auto-restart 5x on failure (5 min delay)" -ForegroundColor White
    Write-Host "  Duplicates  : Prevented (IgnoreNew)" -ForegroundColor White
    Write-Host "  Log file    : $logFile" -ForegroundColor White
    Write-Host ""
    Write-Host "  To start NOW without rebooting, run:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  To stop the bot:" -ForegroundColor Yellow
    Write-Host "  Stop-ScheduledTask  -TaskName '$taskName'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  To view status:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask   -TaskName '$taskName' | Select-Object State" -ForegroundColor Cyan
    Write-Host ""
} catch {
    Write-Host "❌ Failed to register task: $_" -ForegroundColor Red
    Write-Host "   Try running this script as Administrator." -ForegroundColor Yellow
    exit 1
}

# ── Install Python dependencies ──────────────────────────────────────────────
Write-Host "📦 Installing/updating Python dependencies..." -ForegroundColor Cyan
try {
    & $pythonExe -m pip install -r "$workDir\requirements.txt" --quiet
    Write-Host "✅ Dependencies installed." -ForegroundColor Green
} catch {
    Write-Host "⚠️  pip install failed: $_" -ForegroundColor Yellow
}

# ── Install Playwright browsers ──────────────────────────────────────────────
Write-Host "🎭 Installing Playwright Chromium browser..." -ForegroundColor Cyan
try {
    & $pythonExe -m playwright install chromium
    Write-Host "✅ Playwright Chromium installed." -ForegroundColor Green
} catch {
    Write-Host "⚠️  Playwright install failed: $_" -ForegroundColor Yellow
}

# ── Initialize data files if missing ────────────────────────────────────────
$dataDir = "$workDir\data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }
if (-not (Test-Path "$dataDir\applications.json")) { "[]" | Out-File "$dataDir\applications.json" -Encoding utf8 }
if (-not (Test-Path "$dataDir\logs.json"))         { "[]" | Out-File "$dataDir\logs.json"         -Encoding utf8 }
Write-Host "✅ Data files initialized at $dataDir" -ForegroundColor Green

# ── Prompt to start now ──────────────────────────────────────────────────────
Write-Host ""
$startNow = Read-Host "▶  Start the bot RIGHT NOW? (Y/N)"
if ($startNow -match "^[Yy]") {
    Write-Host "🚀 Starting bot..." -ForegroundColor Green
    Start-ScheduledTask -TaskName $taskName
    Start-Sleep -Seconds 3
    $status = (Get-ScheduledTask -TaskName $taskName).State
    Write-Host "   Bot status: $status" -ForegroundColor Cyan
}
