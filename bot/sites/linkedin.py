"""
sites/linkedin.py — LinkedIn Easy Apply automation (Safe Mode)
Fixed: _human_delay removed → uses safety module, phone from profile,
       updated selectors (2025), git_sync import added.
"""
import time, random, os
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.ai_agent_filler import fill_form_with_ai
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import (
    safe_browser_context, save_cookies,
    long_delay, medium_delay, short_delay, think_delay,
    check_daily_limit, increment_daily_count
)

SITE     = "linkedin"
BASE_URL = "https://www.linkedin.com"

# Load phone from profile
def _get_phone():
    try:
        import yaml
        p = yaml.safe_load(open("profile.yaml", encoding="utf-8"))
        return p["personal_info"].get("phone", "+916383149155")
    except Exception:
        return "+916383149155"

def _delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def _encode(text: str) -> str:
    return quote(text)

# ─── MAIN ENTRY ──────────────────────────────────────────────────────────────
def run_linkedin_bot():
    creds = CREDENTIALS["linkedin"]
    if not creds["email"] or not creds["password"]:
        logger.warn("LinkedIn credentials not configured — skipping", SITE)
        return
    if not check_daily_limit(SITE):
        return

    logger.info("Starting LinkedIn Easy Apply bot (Safe Mode)", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()
        try:
            if not _login(page, creds):
                return
            save_cookies(context, SITE)   # Save login cookies for next run
            for job_title in JOB_TITLES:
                for location in LOCATIONS:
                    if not check_daily_limit(SITE):
                        logger.info("LinkedIn daily limit reached — stopping", SITE)
                        return
                    _apply_for_jobs(page, job_title, location)
        except Exception as e:
            logger.error(f"LinkedIn bot crash: {e}", SITE)
        finally:
            browser.close()
            logger.info("LinkedIn bot session ended", SITE)

# ─── LOGIN ────────────────────────────────────────────────────────────────────
def _login(page, creds) -> bool:
    logger.info("Logging into LinkedIn...", SITE)
    try:
        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=45000)
        _delay(2, 3)

        # Check if already logged in (cookie worked)
        if "/feed" in page.url or "/jobs" in page.url:
            logger.success("LinkedIn already logged in via cookies", SITE)
            return True

        page.fill("#username", creds["email"])
        _delay(0.5, 1.2)
        page.fill("#password", creds["password"])
        _delay(0.5, 1.0)
        page.click('button[type="submit"]')
        _delay(3, 5)

        # Handle OTP/verification
        if "checkpoint" in page.url or "challenge" in page.url:
            logger.info("LinkedIn OTP/verification required — check your Gmail/phone", SITE)
            try:
                from bot.utils.gmail_otp import fill_otp_on_page
                fill_otp_on_page(page, site="linkedin", timeout=90)
            except Exception:
                pass
            page.wait_for_url("**/feed/**", timeout=60000)  # Wait for user to solve

        page.wait_for_url("**/feed/**", timeout=30000)
        logger.success("LinkedIn login successful", SITE)
        return True
    except PWTimeout:
        logger.error("LinkedIn login failed — CAPTCHA or wrong credentials", SITE)
        return False
    except Exception as e:
        logger.error(f"LinkedIn login error: {e}", SITE)
        return False

# ─── JOB SEARCH + APPLY ───────────────────────────────────────────────────────
def _apply_for_jobs(page, job_title: str, location: str):
    logger.info(f"Searching LinkedIn: '{job_title}' in '{location}'", SITE)
    search_url = (
        f"{BASE_URL}/jobs/search/?keywords={_encode(job_title)}"
        f"&location={_encode(location)}&f_AL=true&f_TPR=r86400"  # Easy Apply + last 24h
    )
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return
    _delay(2, 4)

    applied_count = 0

    for page_num in range(5):  # Max 5 pages per search
        # Updated selectors for 2025 LinkedIn UI
        jobs = page.query_selector_all(
            "li.jobs-search-results__list-item, "
            ".scaffold-layout__list-item, "
            "li[class*='result']"
        )
        if not jobs:
            break

        for job_el in jobs:
            if not check_daily_limit(SITE):
                return
            try:
                result = _apply_to_job(page, job_el)
                if result:
                    applied_count += 1
                    increment_daily_count(SITE)
                    _delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 5)
            except Exception as e:
                logger.warn(f"Job apply error: {str(e)[:80]}", SITE)
                continue

        # Next page
        try:
            next_btn = page.query_selector(
                'button[aria-label="View next page"], '
                '[aria-label="Next"]'
            )
            if next_btn and next_btn.is_visible():
                next_btn.click()
                _delay(2, 4)
            else:
                break
        except Exception:
            break

    logger.info(f"LinkedIn: Applied to {applied_count} jobs for '{job_title}' in {location}", SITE)

# ─── SINGLE JOB APPLICATION ───────────────────────────────────────────────────
def _apply_to_job(page, job_el) -> bool:
    try:
        job_el.click()
        _delay(1.5, 2.5)

        # 2025 LinkedIn selectors
        title_el   = page.query_selector(
            "h1.t-24.t-bold, "
            ".jobs-unified-top-card__job-title h1, "
            ".job-details-jobs-unified-top-card__job-title h1"
        )
        company_el = page.query_selector(
            ".jobs-unified-top-card__company-name a, "
            ".job-details-jobs-unified-top-card__company-name a, "
            ".jobs-unified-top-card__company-name"
        )
        loc_el     = page.query_selector(
            ".jobs-unified-top-card__bullet, "
            ".job-details-jobs-unified-top-card__primary-description-container"
        )
        desc_el    = page.query_selector(
            ".jobs-description__content, "
            ".jobs-box__html-content, "
            "#job-details"
        )

        job_title = title_el.inner_text().strip()   if title_el   else "Unknown Role"
        company   = company_el.inner_text().strip() if company_el else "Unknown Company"
        location  = loc_el.inner_text().strip()     if loc_el     else "Unknown"
        job_desc  = desc_el.inner_text().strip()    if desc_el    else ""
        job_url   = page.url

        # Easy Apply button — 2025 selectors
        easy_btn = page.query_selector(
            ".jobs-apply-button--top-card button, "
            "button[aria-label*='Easy Apply'], "
            ".jobs-s-apply button, "
            "button.jobs-apply-button"
        )
        if not easy_btn or not easy_btn.is_visible():
            return False  # Not an Easy Apply job

        if is_already_applied(SITE, company, job_title):
            logger.info(f"Skipping {company} — {job_title} (already applied)", SITE)
            return False

        # AI tailor resume
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        easy_btn.click()
        _delay(1.5, 2.5)

        success = _fill_easy_apply_modal(page, resume_path)

        if success:
            record_application(
                site=SITE, company=company, role=job_title,
                location=location, job_url=job_url,
                match_score=match_score, resume_used=resume_path,
            )
            git_sync()

        return success

    except Exception as e:
        logger.warn(f"Failed to apply: {str(e)[:100]}", SITE)
        return False

# ─── EASY APPLY MODAL ────────────────────────────────────────────────────────
def _fill_easy_apply_modal(page, resume_path: str) -> bool:
    phone = _get_phone()

    for step in range(15):  # LinkedIn can have up to 15 steps
        _delay(1, 2)

        # Upload resume
        upload = page.query_selector('input[type="file"]')
        if upload:
            try:
                upload.set_input_files(resume_path)
                _delay(1, 2)
            except Exception:
                pass

        # Fill phone number from profile
        for phone_sel in [
            'input[id*="phoneNumber"]',
            'input[name*="phone"]',
            'input[placeholder*="phone" i]',
            'input[aria-label*="phone" i]',
        ]:
            try:
                el = page.query_selector(phone_sel)
                if el and el.is_visible() and not el.input_value():
                    el.fill(phone)
                    break
            except Exception:
                continue

        # AI fill custom questions
        try:
            fill_form_with_ai(page, site=SITE)
        except Exception as e:
            logger.warn(f"AI form fill step {step}: {str(e)[:60]}", SITE)

        # Navigation buttons
        submit_btn = page.query_selector('button[aria-label="Submit application"]')
        review_btn = page.query_selector('button[aria-label="Review your application"]')
        next_btn   = page.query_selector('button[aria-label="Continue to next step"]')
        unfollow   = page.query_selector('label[for="follow-company-checkbox"]')

        if unfollow:
            try:
                unfollow.click()  # Uncheck "follow company" to avoid spam
            except Exception:
                pass

        if submit_btn and submit_btn.is_visible():
            submit_btn.click()
            _delay(1, 2)
            try:
                page.click('button[aria-label="Dismiss"]', timeout=3000)
            except Exception:
                pass
            logger.success("LinkedIn Easy Apply submitted!", SITE)
            return True
        elif review_btn and review_btn.is_visible():
            review_btn.click()
        elif next_btn and next_btn.is_visible():
            next_btn.click()
        else:
            modal = page.query_selector('.jobs-easy-apply-modal, .artdeco-modal')
            if not modal:
                break

    return False
