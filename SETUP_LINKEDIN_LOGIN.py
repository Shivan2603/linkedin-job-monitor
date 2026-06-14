"""
SETUP_LINKEDIN_LOGIN.py
=======================
Run this ONCE to log into LinkedIn manually in the persistent browser.
After you log in, your session is saved FOREVER.
The bot will never ask you to log in to LinkedIn again.

Usage:
    python SETUP_LINKEDIN_LOGIN.py
"""
import os, sys
from playwright.sync_api import sync_playwright

DATA_FOLDER    = os.path.join(os.path.dirname(__file__), "data")
PROFILE_DIR    = os.path.join(DATA_FOLDER, "chrome_profile_linkedin")
os.makedirs(PROFILE_DIR, exist_ok=True)

print("=" * 60)
print("  LinkedIn One-Time Login Setup")
print("=" * 60)
print()
print("  A browser will open. Please:")
print("  1. Log into LinkedIn with your email + password")
print("  2. Solve any CAPTCHA if it appears")
print("  3. Once you see your LinkedIn feed, come back here")
print("     and press ENTER to save your session.")
print()
print("  You will NEVER need to do this again!")
print("=" * 60)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
        slow_mo=50,
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

    input("\n  >> Press ENTER once you are logged in and can see your feed... ")

    # Verify login
    try:
        page.wait_for_selector(".global-nav", timeout=5000)
        print()
        print("  SUCCESS! LinkedIn session saved permanently.")
        print("  You can now run START_JOB_BOT.bat and LinkedIn will")
        print("  log in automatically without any CAPTCHA!")
    except Exception:
        print()
        print("  WARNING: Could not detect the LinkedIn navigation bar.")
        print("  Please make sure you are fully logged in before closing.")

    context.close()
    print()
    print("  Session saved. Setup complete!")
