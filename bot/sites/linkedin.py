"""
sites/linkedin.py — LinkedIn Easy Apply automation
Uses Playwright to log in, search jobs, filter Easy Apply, tailor resume, apply
"""
import time, random, os
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger

SITE = "linkedin"
BASE_URL = "https://www.linkedin.com"

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_linkedin_bot():
    """Main entry point — applies to all matching LinkedIn Easy Apply jobs"""
    creds = CREDENTIALS["linkedin"]
    if not creds["email"] or not creds["password"]:
        logger.warn("LinkedIn credentials not configured — skipping", SITE)
        return

    logger.info("🚀 Starting LinkedIn Easy Apply bot", SITE)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Set True for background running
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        try:
            if not _login(page, creds):
                return

            for job_title in JOB_TITLES:
                for location in LOCATIONS:
                    _apply_for_jobs(page, job_title, location)

        except Exception as e:
            logger.error(f"LinkedIn bot crash: {e}", SITE)
        finally:
            browser.close()
            logger.info("LinkedIn bot session ended", SITE)

def _login(page, creds) -> bool:
    """Log into LinkedIn"""
    logger.info("Logging into LinkedIn...", SITE)
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    _human_delay(1, 2)

    try:
        page.fill("#username", creds["email"])
        _human_delay(0.5, 1)
        page.fill("#password", creds["password"])
        _human_delay(0.5, 1)
        page.click('[type="submit"]')
        page.wait_for_url("**/feed/**", timeout=15000)
        logger.success("LinkedIn login successful ✅", SITE)
        return True
    except PWTimeout:
        logger.error("LinkedIn login failed — check credentials or CAPTCHA", SITE)
        return False

def _apply_for_jobs(page, job_title: str, location: str):
    """Search and apply to Easy Apply jobs for a title/location combo"""
    logger.info(f"Searching: '{job_title}' in '{location}'", SITE)

    # Build search URL with Easy Apply filter
    search_url = (
        f"{BASE_URL}/jobs/search/?keywords={_encode(job_title)}"
        f"&location={_encode(location)}&f_AL=true"  # f_AL = Easy Apply
    )

    page.goto(search_url, wait_until="domcontentloaded")
    _human_delay(2, 3)

    applied_count = 0
    page_num = 0

    while applied_count < 50:  # Max 50 per title/location combo per session
        page_num += 1
        jobs = page.query_selector_all(".jobs-search__results-list li, .scaffold-layout__list-item")

        if not jobs:
            logger.info(f"No more jobs on page {page_num} for '{job_title}' in {location}", SITE)
            break

        for job_el in jobs:
            try:
                result = _apply_to_job(page, job_el)
                if result:
                    applied_count += 1
                    _human_delay(APPLY_DELAY_SECONDS - 2, APPLY_DELAY_SECONDS + 4)
            except Exception as e:
                logger.warn(f"Job apply error: {e}", SITE)
                continue

        # Try next page
        try:
            next_btn = page.query_selector('[aria-label="View next page"]')
            if next_btn:
                next_btn.click()
                _human_delay(2, 4)
            else:
                break
        except Exception:
            break

    logger.info(f"Applied to {applied_count} jobs for '{job_title}' in {location}", SITE)

def _apply_to_job(page, job_el) -> bool:
    """Click a job listing and attempt Easy Apply"""
    try:
        job_el.click()
        _human_delay(1.5, 2.5)

        # Get job details
        title_el   = page.query_selector(".jobs-unified-top-card__job-title, h1.t-24")
        company_el = page.query_selector(".jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name")
        loc_el     = page.query_selector(".jobs-unified-top-card__bullet")
        desc_el    = page.query_selector(".jobs-description__content, .jobs-box__html-content")

        job_title   = title_el.inner_text().strip()   if title_el   else "Unknown Role"
        company     = company_el.inner_text().strip()  if company_el else "Unknown Company"
        location    = loc_el.inner_text().strip()      if loc_el     else "Unknown"
        job_desc    = desc_el.inner_text().strip()     if desc_el    else ""
        job_url     = page.url

        # Check Easy Apply button
        easy_btn = page.query_selector(".jobs-apply-button--top-card button, button[aria-label*='Easy Apply']")
        if not easy_btn:
            return False

        from bot.utils.logger import record_application, is_already_applied, git_sync

        if is_already_applied(SITE, company, job_title):
            logger.info(f"Skipping {company} - {job_title} (Already applied)", SITE)
            return False

        # AI Tailor Resume
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        # Click Easy Apply
        easy_btn.click()
        _human_delay(1, 2)

        # Fill Easy Apply modal
        _fill_easy_apply_modal(page, resume_path)

        # Record application
        from bot.utils.logger import record_application
        record_application(
            site=SITE,
            company=company,
            role=job_title,
            location=location,
            job_url=job_url,
            match_score=match_score,
            resume_used=resume_path,
        )
        git_sync()
        return True

    except Exception as e:
        logger.warn(f"Failed to apply: {e}", SITE)
        return False

def _fill_easy_apply_modal(page, resume_path: str):
    """Step through Easy Apply multi-step modal"""
    for _ in range(10):  # Max 10 steps/pages in modal
        _human_delay(1, 2)

        # Upload resume if prompted
        upload = page.query_selector('input[type="file"]')
        if upload:
            upload.set_input_files(resume_path)
            _human_delay(1, 2)

        # Fill phone if asked
        phone_input = page.query_selector('input[id*="phoneNumber"]')
        if phone_input and not phone_input.input_value():
            phone_input.fill("+91 9999999999")  # Will be replaced with real number from .env

        # Click Next / Review / Submit
        next_btn   = page.query_selector('button[aria-label="Continue to next step"]')
        review_btn = page.query_selector('button[aria-label="Review your application"]')
        submit_btn = page.query_selector('button[aria-label="Submit application"]')

        if submit_btn:
            submit_btn.click()
            _human_delay(1, 2)
            # Close confirmation
            close = page.query_selector('button[aria-label="Dismiss"]')
            if close:
                close.click()
            return

        if review_btn:
            review_btn.click()
        elif next_btn:
            next_btn.click()
        else:
            break

def _encode(text: str) -> str:
    from urllib.parse import quote
    return quote(text)
