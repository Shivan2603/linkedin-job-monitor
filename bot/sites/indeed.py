"""
sites/indeed.py — Indeed India automation
"""
import time, random
from playwright.sync_api import sync_playwright
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger

SITE = "indeed"
BASE_URL = "https://in.indeed.com"

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_indeed_bot():
    creds = CREDENTIALS["indeed"]
    if not creds["email"] or not creds["password"]:
        logger.warn("Indeed credentials not configured — skipping", SITE)
        return

    logger.info("🚀 Starting Indeed India bot", SITE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()

        try:
            if not _login(page, creds):
                return
            for job_title in JOB_TITLES:
                for location in LOCATIONS[:5]:
                    _apply_indeed_jobs(page, job_title, location)
        except Exception as e:
            logger.error(f"Indeed bot crash: {e}", SITE)
        finally:
            browser.close()

def _login(page, creds) -> bool:
    logger.info("Logging into Indeed...", SITE)
    page.goto("https://secure.indeed.com/auth", wait_until="domcontentloaded")
    _human_delay(2, 3)
    try:
        page.fill('input[type="email"], input[name="__email"]', creds["email"])
        _human_delay(0.5, 1)
        page.click('button[type="submit"]')
        _human_delay(1, 2)
        page.fill('input[type="password"]', creds["password"])
        _human_delay(0.5, 1)
        page.click('button[type="submit"]')
        _human_delay(3, 4)
        logger.success("Indeed login successful ✅", SITE)
        return True
    except Exception as e:
        logger.error(f"Indeed login failed: {e}", SITE)
        return False

def _apply_indeed_jobs(page, job_title: str, location: str):
    from urllib.parse import quote
    logger.info(f"Searching Indeed: '{job_title}' in '{location}'", SITE)
    url = f"{BASE_URL}/jobs?q={quote(job_title)}&l={quote(location)}&iafilter=1"
    page.goto(url, wait_until="domcontentloaded")
    _human_delay(2, 3)

    applied = 0
    cards = page.query_selector_all(".job_seen_beacon, .tapItem")

    for card in cards:
        try:
            card.click()
            _human_delay(1.5, 2)

            title_el   = page.query_selector(".jobsearch-JobInfoHeader-title span:first-child")
            company_el = page.query_selector('[data-company-name="true"]')
            desc_el    = page.query_selector("#jobDescriptionText")

            job_t   = title_el.inner_text().strip()   if title_el   else job_title
            company = company_el.inner_text().strip()  if company_el else "Company"
            desc    = desc_el.inner_text().strip()     if desc_el    else ""

            # Indeed Apply button
            apply_btn = page.query_selector('.ia-continueButton, [id*="indeedApplyButton"]')
            if not apply_btn:
                continue

            from bot.utils.logger import record_application, is_already_applied, git_sync

            if is_already_applied(SITE, company, job_t):
                logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
                continue

            tailor_result = tailor_resume(job_t, company, desc, site=SITE)
            apply_btn.click()
            _human_delay(2, 3)

            # Handle Indeed Apply flow
            for _ in range(8):
                _human_delay(1, 2)
                next_b = page.query_selector('button[type="submit"]')
                if next_b:
                    upload = page.query_selector('input[type="file"]')
                    if upload:
                        upload.set_input_files(tailor_result["resume_path"])
                        _human_delay(1, 2)
                    next_b.click()
                else:
                    break

            record_application(
                site=SITE, company=company, role=job_t, location=location,
                job_url=page.url, match_score=tailor_result["match_score"],
                resume_used=tailor_result["resume_path"],
            )
            git_sync()
            applied += 1
            _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 5)

        except Exception as e:
            logger.warn(f"Indeed job error: {e}", SITE)
            continue

    logger.info(f"Applied to {applied} jobs on Indeed for '{job_title}' in {location}", SITE)
