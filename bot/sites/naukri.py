"""
sites/naukri.py — Naukri.com Quick Apply automation
"""
import time, random
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger

SITE = "naukri"
BASE_URL = "https://www.naukri.com"

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_naukri_bot():
    creds = CREDENTIALS["naukri"]
    if not creds["email"] or not creds["password"]:
        logger.warn("Naukri credentials not configured — skipping", SITE)
        return

    logger.info("🚀 Starting Naukri.com bot", SITE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        try:
            if not _login(page, creds):
                return
            for job_title in JOB_TITLES:
                for location in LOCATIONS[:4]:  # Focus on Indian cities first
                    _apply_naukri_jobs(page, job_title, location)
        except Exception as e:
            logger.error(f"Naukri bot crash: {e}", SITE)
        finally:
            browser.close()
            logger.info("Naukri bot session ended", SITE)

def _login(page, creds) -> bool:
    logger.info("Logging into Naukri...", SITE)
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    _human_delay(2, 3)
    try:
        page.fill('input[placeholder*="Email"]', creds["email"])
        _human_delay(0.5, 1)
        page.fill('input[type="password"]', creds["password"])
        _human_delay(0.5, 1)
        page.click('button[type="submit"]')
        _human_delay(3, 5)
        logger.success("Naukri login successful ✅", SITE)
        return True
    except Exception as e:
        logger.error(f"Naukri login failed: {e}", SITE)
        return False

def _apply_naukri_jobs(page, job_title: str, location: str):
    logger.info(f"Searching Naukri: '{job_title}' in '{location}'", SITE)

    from urllib.parse import quote
    search_url = f"{BASE_URL}/{quote(job_title.lower().replace(' ','-'))}-jobs-in-{quote(location.lower())}?jobAge=1"
    page.goto(search_url, wait_until="domcontentloaded")
    _human_delay(2, 3)

    applied = 0
    job_cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple")

    for card in job_cards:
        try:
            card.click()
            _human_delay(1.5, 2.5)
            page.wait_for_selector(".apply-button, button[class*='apply']", timeout=5000)

            title_el   = page.query_selector(".jd-header-title, h1.jd-title")
            company_el = page.query_selector(".jd-header-comp-name a, .comp-name")
            desc_el    = page.query_selector(".job-desc, .JDC-module")

            job_title_txt = title_el.inner_text().strip()   if title_el   else job_title
            company_txt   = company_el.inner_text().strip() if company_el else "Company"
            desc_txt      = desc_el.inner_text().strip()    if desc_el    else ""

            tailor_result = tailor_resume(job_title_txt, company_txt, desc_txt, site=SITE)
            resume_path   = tailor_result["resume_path"]
            match_score   = tailor_result["match_score"]

            apply_btn = page.query_selector(".apply-button, button.btn-primary[class*='apply']")
            if apply_btn:
                apply_btn.click()
                _human_delay(1, 2)

                # Upload resume if prompted
                upload = page.query_selector('input[type="file"]')
                if upload:
                    upload.set_input_files(resume_path)
                    _human_delay(1, 2)
                    submit = page.query_selector('button[type="submit"]')
                    if submit:
                        submit.click()

                from bot.utils.logger import record_application
                record_application(
                    site=SITE, company=company_txt, role=job_title_txt,
                    location=location, job_url=page.url,
                    match_score=match_score, resume_used=resume_path,
                )
                applied += 1
                _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 5)

        except Exception as e:
            logger.warn(f"Naukri job error: {e}", SITE)
            continue

    logger.info(f"Applied to {applied} jobs on Naukri for '{job_title}' in {location}", SITE)
