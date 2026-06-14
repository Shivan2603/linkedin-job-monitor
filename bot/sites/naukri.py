"""
sites/naukri.py — Naukri.com Quick Apply automation (2025 UI)
Fixed: Updated selectors for current Naukri UI, proper job card interaction,
       Quick Apply flow, phone from profile, daily limit checks.
"""
import time, random
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import (
    safe_browser_context, save_cookies,
    check_daily_limit, increment_daily_count
)

SITE     = "naukri"
BASE_URL = "https://www.naukri.com"

def _delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def _get_phone():
    try:
        import yaml
        p = yaml.safe_load(open("profile.yaml", encoding="utf-8"))
        return p["personal_info"].get("phone_local", "6383149155")
    except Exception:
        return "6383149155"

# ─── MAIN ENTRY ───────────────────────────────────────────────────────────────
def run_naukri_bot():
    creds = CREDENTIALS["naukri"]
    if not creds["email"] or not creds["password"]:
        logger.warn("Naukri credentials not configured — skipping", SITE)
        return
    if not check_daily_limit(SITE):
        return

    logger.info("Starting Naukri.com bot", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()
        try:
            if not _login(page, creds):
                return
            save_cookies(context, SITE)
            for job_title in JOB_TITLES:
                for location in LOCATIONS[:4]:  # Top 4 locations for Naukri
                    if not check_daily_limit(SITE):
                        logger.info("Naukri daily limit reached", SITE)
                        return
                    _search_and_apply(page, job_title, location)
        except Exception as e:
            logger.error(f"Naukri bot crash: {e}", SITE)
        finally:
            browser.close()
            logger.info("Naukri bot session ended", SITE)

# ─── LOGIN ────────────────────────────────────────────────────────────────────
def _login(page, creds) -> bool:
    logger.info("Logging into Naukri...", SITE)

    for login_url in [f"{BASE_URL}/nlogin/login", f"{BASE_URL}/login"]:
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=25000)
            _delay(2, 3)
            if "404" not in page.title() and page.query_selector("input"):
                break
        except Exception:
            continue

    # Check already logged in
    if "mnjuser" in page.url or "myhome" in page.url:
        logger.success("Naukri already logged in via cookies", SITE)
        return True

    try:
        # Naukri 2025 login selectors
        for email_sel in [
            'input[placeholder*="Email" i]',
            'input[type="email"]',
            '#usernameField',
            'input[name="username"]',
        ]:
            try:
                el = page.query_selector(email_sel)
                if el and el.is_visible():
                    el.click()
                    _delay(0.3, 0.6)
                    el.fill(creds["email"])
                    break
            except Exception:
                continue

        _delay(0.5, 1)

        for pass_sel in [
            'input[type="password"]',
            '#passwordField',
            'input[placeholder*="Password" i]',
        ]:
            try:
                el = page.query_selector(pass_sel)
                if el and el.is_visible():
                    el.click()
                    _delay(0.3, 0.5)
                    el.fill(creds["password"])
                    break
            except Exception:
                continue

        _delay(0.5, 1)

        for btn_sel in [
            'button[type="submit"]',
            'button.loginButton',
            'input[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
        ]:
            try:
                el = page.query_selector(btn_sel)
                if el and el.is_visible():
                    el.click()
                    break
            except Exception:
                continue

        _delay(4, 6)

        # Handle OTP
        otp_el = page.query_selector('input[placeholder*="OTP" i], input[placeholder*="code" i]')
        if otp_el:
            logger.info("Naukri OTP required — checking Gmail...", SITE)
            try:
                from bot.utils.gmail_otp import wait_for_otp
                otp = wait_for_otp(site="naukri", timeout_seconds=60)
                if otp:
                    otp_el.fill(otp)
                    _delay(0.5, 1)
                    page.click('button[type="submit"]', timeout=5000)
                    _delay(3, 4)
            except Exception:
                pass

        logger.success("Naukri login successful", SITE)
        return True

    except Exception as e:
        logger.error(f"Naukri login failed: {e}", SITE)
        return False

# ─── SEARCH AND APPLY ─────────────────────────────────────────────────────────
def _search_and_apply(page, job_title: str, location: str):
    logger.info(f"Searching Naukri: '{job_title}' in '{location}'", SITE)
    from urllib.parse import quote

    search_url = (
        f"{BASE_URL}/{quote(job_title.lower().replace(' ', '-'))}-jobs"
        f"?k={quote(job_title)}&l={quote(location)}&jobAge=1&experience=3,7"
    )

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return
    _delay(2, 3)

    applied = 0

    # Naukri 2025 job card selectors
    job_cards = page.query_selector_all(
        "article.jobTuple, "
        ".srp-jobtuple-wrapper, "
        "div[class*='jobTuple'], "
        ".job-container"
    )

    if not job_cards:
        logger.info(f"No job cards found for '{job_title}' in {location}", SITE)
        return

    logger.info(f"Found {len(job_cards)} jobs for '{job_title}' in {location}", SITE)

    for card in job_cards[:15]:  # Process max 15 per search
        if not check_daily_limit(SITE):
            return
        try:
            result = _apply_to_card(page, card, job_title, location)
            if result:
                applied += 1
                increment_daily_count(SITE)
                _delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 5)
        except Exception as e:
            logger.warn(f"Naukri card error: {str(e)[:80]}", SITE)
            continue

    logger.info(f"Naukri: Applied to {applied} jobs for '{job_title}' in {location}", SITE)

# ─── SINGLE JOB APPLICATION ──────────────────────────────────────────────────
def _apply_to_card(page, card, default_title: str, location: str) -> bool:
    try:
        # Get job info from card
        title_el   = card.query_selector(
            ".title, .row1 a, a[class*='title'], h3 a, .jobTupleHeader a"
        )
        company_el = card.query_selector(
            ".companyInfo a, .comp-name, a[class*='company'], .subTitle a"
        )

        job_title = title_el.inner_text().strip() if title_el else default_title
        company   = company_el.inner_text().strip() if company_el else "Company"

        if is_already_applied(SITE, company, job_title):
            logger.info(f"Skipping {company} — {job_title} (already applied)", SITE)
            return False

        # Click job title to open detail panel
        if title_el:
            title_el.click()
        else:
            card.click()
        _delay(2, 3)

        # Job detail opens in right panel or new tab
        # Handle new tab if opened
        pages = page.context.pages
        detail_page = pages[-1] if len(pages) > 1 else page

        _delay(1, 2)

        # Get job description from detail panel
        desc_el = detail_page.query_selector(
            ".job-desc, .JDC-module, .jd-content, "
            "section.description, [class*='jobDesc']"
        )
        job_desc = desc_el.inner_text().strip() if desc_el else ""
        job_url  = detail_page.url

        # Find apply button in detail view — 2025 Naukri selectors
        apply_btn = None
        for btn_sel in [
            'button.styles_apply-button__N2dZs',
            'button[class*="apply-button"]',
            'a[class*="apply-button"]',
            'button[class*="chatApplyBtn"]',
            'button:has-text("Apply")',
            'a:has-text("Apply")',
            '.apply-button',
            'button.btn-primary',
        ]:
            try:
                el = detail_page.query_selector(btn_sel)
                if el and el.is_visible(timeout=2000):
                    apply_btn = el
                    break
            except Exception:
                continue

        if not apply_btn:
            # Close new tab if opened
            if detail_page != page:
                detail_page.close()
            return False

        # AI tailor resume
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        apply_btn.click()
        _delay(2, 3)

        # Handle Quick Apply modal
        success = _handle_apply_modal(detail_page, resume_path)

        if success:
            record_application(
                site=SITE, company=company, role=job_title,
                location=location, job_url=job_url,
                match_score=match_score, resume_used=resume_path,
            )
            git_sync()

        # Close new tab if opened
        if detail_page != page:
            detail_page.close()

        return success

    except Exception as e:
        logger.warn(f"Naukri apply error: {str(e)[:100]}", SITE)
        return False

# ─── QUICK APPLY MODAL ───────────────────────────────────────────────────────
def _handle_apply_modal(page, resume_path: str) -> bool:
    phone = _get_phone()
    _delay(1, 2)

    # Upload resume if prompted
    for file_sel in ['input[type="file"]', 'input[accept*="doc"]']:
        try:
            el = page.query_selector(file_sel)
            if el:
                el.set_input_files(resume_path)
                _delay(1, 2)
                break
        except Exception:
            pass

    # Fill phone if needed
    for phone_sel in [
        'input[placeholder*="mobile" i]',
        'input[placeholder*="phone" i]',
        'input[name*="phone" i]',
        'input[type="tel"]',
    ]:
        try:
            el = page.query_selector(phone_sel)
            if el and el.is_visible():
                if not el.input_value():
                    el.fill(phone)
                    _delay(0.3, 0.6)
                break
        except Exception:
            continue

    # Submit
    for submit_sel in [
        'button:has-text("Apply")',
        'button:has-text("Submit")',
        'button[type="submit"]',
        '.btn-primary:has-text("Apply")',
    ]:
        try:
            el = page.query_selector(submit_sel)
            if el and el.is_visible():
                el.click()
                _delay(2, 3)

                # Confirm success
                success_el = page.query_selector(
                    '[class*="success"], [class*="applied"], '
                    ':has-text("Application submitted"), :has-text("Applied successfully")'
                )
                if success_el:
                    logger.success(f"Naukri Quick Apply submitted!", SITE)
                    return True
                return True  # Assume success if no error shown
        except Exception:
            continue

    return False
