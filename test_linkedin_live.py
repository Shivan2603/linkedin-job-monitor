import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from playwright.sync_api import sync_playwright
from bot.sites.linkedin import _login, _apply_to_job
from bot.utils.safety import safe_browser_context
from bot.config import CREDENTIALS

def test_live():
    creds = CREDENTIALS["linkedin"]
    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "linkedin")
        page = context.pages[0] if context.pages else context.new_page()
        
        print("Waiting for you to ensure you are logged into Gmail and LinkedIn if needed...")
        
        # We will run _login which now has resilient locators and uses persistent contexts.
        # If already logged in natively, it'll skip.
        if not _login(page, creds):
            print("Login failed.")
            return
            
        print("Logged in successfully. Finding 1 test job...")
        
        # Go to job search
        search_url = "https://www.linkedin.com/jobs/search/?keywords=Senior%20.NET%20Developer&location=Remote&f_AL=true&f_E=4"
        page.goto(search_url, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass
            
        jobs = page.query_selector_all('.job-card-container')
        if not jobs:
            print("No jobs found on first page.")
            return
            
        print("Clicking first job to test Easy Apply...")
        jobs[0].click()
        try:
            page.wait_for_selector(".jobs-apply-button", timeout=5000)
        except:
            print("No apply button found.")
            return
            
        _apply_to_job(page, jobs[0])
        print("Finished.")

if __name__ == "__main__":
    test_live()
