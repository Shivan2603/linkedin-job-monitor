"""
sites/shine.py — Shine.com automation
"""
import time, random
from playwright.sync_api import sync_playwright
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger

SITE = "shine"

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_shine_bot():
    creds = CREDENTIALS["shine"]
    if not creds["email"] or not creds["password"]:
        logger.warn("Shine credentials not configured — skipping", SITE)
        return

    logger.info("🚀 Starting Shine.com bot", SITE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            _login(page, creds)
            for job_title in JOB_TITLES[:4]:  # Shine has less jobs, limit
                for location in ["Bangalore", "Chennai", "Hyderabad", "Remote"]:
                    _apply_shine_jobs(page, job_title, location)
        except Exception as e:
            logger.error(f"Shine bot crash: {e}", SITE)
        finally:
            browser.close()

def _login(page, creds) -> bool:
    logger.info("Logging into Shine...", SITE)
    page.goto("https://www.shine.com/login/", wait_until="domcontentloaded")
    _human_delay(2, 3)
    try:
        page.fill('input[name="email"]', creds["email"])
        page.fill('input[name="password"]', creds["password"])
        page.click('button[type="submit"]')
        _human_delay(3, 4)
        logger.success("Shine login successful ✅", SITE)
        return True
    except Exception as e:
        logger.error(f"Shine login failed: {e}", SITE)
        return False

def _apply_shine_jobs(page, job_title: str, location: str):
    from urllib.parse import quote
    logger.info(f"Searching Shine: '{job_title}' in '{location}'", SITE)
    url = f"https://www.shine.com/job-search/{quote(job_title.lower().replace(' ','-'))}-jobs-in-{quote(location.lower())}/"
    page.goto(url, wait_until="domcontentloaded")
    _human_delay(2, 3)

    applied = 0
    cards = page.query_selector_all(".jobCard, .job-card-wrapper")

    for card in cards[:30]:
        try:
            card.click()
            _human_delay(1.5, 2.5)

            title_el   = page.query_selector("h1.job-header__title")
            company_el = page.query_selector(".job-header__company-name")
            desc_el    = page.query_selector(".job-description")

            job_t   = title_el.inner_text().strip()   if title_el   else job_title
            company = company_el.inner_text().strip()  if company_el else "Company"
            desc    = desc_el.inner_text().strip()     if desc_el    else ""

            apply_btn = page.query_selector('.apply-btn, button[class*="apply"]')
            if not apply_btn:
                continue

            tailor_result = tailor_resume(job_t, company, desc, site=SITE)
            apply_btn.click()
            _human_delay(2, 3)

            upload = page.query_selector('input[type="file"]')
            if upload:
                upload.set_input_files(tailor_result["resume_path"])
                _human_delay(1, 2)

            submit = page.query_selector('button[type="submit"]')
            if submit:
                submit.click()

            from bot.utils.logger import record_application
            record_application(
                site=SITE, company=company, role=job_t, location=location,
                job_url=page.url, match_score=tailor_result["match_score"],
                resume_used=tailor_result["resume_path"],
            )
            applied += 1
            _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 4)

        except Exception as e:
            logger.warn(f"Shine job error: {e}", SITE)
            continue

    logger.info(f"Shine: Applied to {applied} jobs", SITE)
