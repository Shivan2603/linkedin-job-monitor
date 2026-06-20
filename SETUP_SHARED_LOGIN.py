"""
SETUP_SHARED_LOGIN.py
=======================
Run this ONCE to log into Google, Indeed, Foundit, and LinkedIn manually.
Since these portals share the 'chrome_profile_shared' context, logging in here
saves your session FOREVER. The bot will run automatically without login prompts.

Usage:
    python SETUP_SHARED_LOGIN.py
"""
import os, sys, time, subprocess

# Add project path to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot.config import DATA_FOLDER

PROFILE_DIR = os.path.join(DATA_FOLDER, "chrome_profile_shared")
os.makedirs(PROFILE_DIR, exist_ok=True)

# Clean up stale lock files from crashed previous sessions (prevents Error Code 32)
for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    lock_path = os.path.join(PROFILE_DIR, lock_file)
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass

def find_chrome():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

chrome_path = find_chrome()

print("=" * 60)
print("  Shared Profile One-Time Login Setup (Native Bypass Mode)")
print("=" * 60)
print()

if not chrome_path:
    print("  ERROR: Google Chrome could not be found in standard paths!")
    print("  Please make sure Google Chrome is installed on this system.")
    sys.exit(1)

print("  Starting native Chrome instance...")
print(f"  Profile directory: {PROFILE_DIR}")
print()
print("  Please complete the logins in the browser tabs:")
print("  1. Log into your Google Account (sivashankar.avi6@gmail.com)")
print("  2. Verify Indeed login (https://secure.indeed.com/auth)")
print("  3. Verify Foundit login (https://www.foundit.in/)")
print("  4. Verify LinkedIn login (https://www.linkedin.com/login)")
print("  5. Verify Shine login (https://www.shine.com/login/)")
print("  6. Verify JobStreet login (https://www.jobstreet.com.sg/oauth/login?returnUrl=%2F)")
print("  7. Verify Jooble login (https://jooble.org)")
print("  8. Solve any CAPTCHAs, OTPs, or 2FA if prompted")
print("  9. Once you are logged in, close the browser window and press ENTER.")
print("=" * 60)

# Launch native Chrome pointing to our shared profile. 
# This has ZERO automation flags, bypassing Google SSO detection completely.
try:
    proc = subprocess.Popen([
        chrome_path,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "https://accounts.google.com/InteractiveLogin",
        "https://secure.indeed.com/auth",
        "https://www.foundit.in/",
        "https://www.linkedin.com/login",
        "https://www.shine.com/login/",
        "https://www.jobstreet.com.sg/oauth/login?returnUrl=%2F",
        "https://jooble.org"
    ])
    
    input("\n  >> Press ENTER here after you have successfully signed in and CLOSED the Chrome window... ")
    
    # Ensure process is closed
    try:
        proc.terminate()
    except Exception:
        pass
        
    print("\n  SUCCESS! All sessions saved permanently in the shared profile folder.")
    print("  You can now run the Job Bot and it will use your active logged-in sessions!")
except Exception as e:
    print(f"\n  Failed to launch Chrome: {e}")
