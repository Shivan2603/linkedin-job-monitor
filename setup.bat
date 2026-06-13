@echo off
echo ============================================
echo  LinkedIn Job Bot - One-Click Setup
echo ============================================
echo.

echo [1/5] Installing Python dependencies...
pip install -r requirements.txt
echo.

echo [2/5] Installing Playwright browsers...
python -m playwright install chromium
echo.

echo [3/5] Creating today's tailored resume folder...
for /f "tokens=1-3 delims=/" %%a in ('date /t') do set DATESTR=%%b-%%c-%%a
mkdir "E:\SivaShankar\Resume\tailored\%date:~-4%-%date:~3,2%-%date:~0,2%" 2>nul
echo     Created: E:\SivaShankar\Resume\tailored\%date:~0,2%-%date:~3,2%-%date:~-4%
echo.

echo [4/5] Copying .env.example to .env ...
if not exist .env (
    copy .env.example .env
    echo     IMPORTANT: Edit E:\SivaShankar\jobbot\.env and fill in your credentials!
) else (
    echo     .env already exists - skipping
)
echo.

echo [5/5] Registering Windows Task Scheduler job...
schtasks /create /tn "LinkedInJobBot" /tr "python \"E:\SivaShankar\jobbot\bot\main.py\"" /sc daily /st 00:00 /f
echo     Task 'LinkedInJobBot' registered - runs daily at 12:00 AM
echo.

echo ============================================
echo  Setup complete!
echo.
echo  Next steps:
echo  1. Edit E:\SivaShankar\jobbot\.env with your credentials
echo  2. Run manually: python bot\main.py
echo  3. View dashboard: open monitor\index.html
echo ============================================
pause
