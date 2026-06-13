"""
sites/company_careers.py — Generic Company Career Website Automation
Uses AI form filler to navigate to custom career pages and apply dynamically.
"""
import time, random
from playwright.sync_api import sync_playwright
from bot.config import JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.ai_agent_filler import fill_form_with_ai
from bot.utils import logger

SITE = "company_careers"

# List of demo career page URLs to process (in reality, this could be scraped from Google)
CAREER_PAGES = [
    # Placeholder example URLs that usually host standard forms (Lever/Greenhouse/etc)
    "https://jobs.lever.co/example-company/12345/apply",
    "https://boards.greenhouse.io/example/jobs/67890"
]

def _human_delay(a=2.0, b=4.0):
    time.sleep(random.uniform(a, b))

def run_company_careers_bot():
    logger.info("🚀 Starting Universal Career Pages bot", SITE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()

        applied = 0
        try:
            for url in CAREER_PAGES:
                # In a real scenario, these URLs would be discovered dynamically.
                # For this implementation, we simulate navigating to an application page.
                if "example" in url:
                    continue  # Skip placeholders
                    
                logger.info(f"Navigating to {url}", SITE)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    _human_delay(2, 4)
                    
                    # Extract title and company from the page title
                    page_title = page.title()
                    company = page_title.split("-")[0].strip() if "-" in page_title else "Unknown Company"
                    job_t = page_title.split("-")[1].strip() if "-" in page_title else "Software Engineer"
                    
                    from bot.utils.logger import record_application, is_already_applied, git_sync
                    if is_already_applied(SITE, company, job_t):
                        logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
                        continue

                    # Tailor resume based on generic description
                    desc = page.inner_text("body")[:3000]
                    tailor_result = tailor_resume(job_t, company, desc, site=SITE)
                    resume_path = tailor_result["resume_path"]
                    
                    # Upload resume first if there's a file input
                    upload = page.query_selector('input[type="file"]')
                    if upload:
                        upload.set_input_files(resume_path)
                        _human_delay(1, 3)
                        
                    # Use AI to fill the rest of the form
                    success = fill_form_with_ai(page, site=SITE)
                    
                    if success:
                        submit_btn = page.query_selector('button[type="submit"], input[type="submit"]')
                        if submit_btn:
                            submit_btn.click()
                            _human_delay(3, 5)
                            
                        record_application(
                            site=SITE, company=company, role=job_t, location="Remote/Various",
                            job_url=url, match_score=tailor_result["match_score"],
                            resume_used=resume_path,
                        )
                        git_sync()
                        applied += 1
                        _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 5)
                        
                except Exception as e:
                    logger.warn(f"Failed to process career page {url}: {e}", SITE)
                    continue
                    
        except Exception as e:
            logger.error(f"Company Careers bot crash: {e}", SITE)
        finally:
            browser.close()
            logger.info(f"Company Careers bot session ended. Applied to {applied} jobs.", SITE)
