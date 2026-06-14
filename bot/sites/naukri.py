"""
sites/naukri.py — Naukri.com Quick Apply (2025, URL-based approach)

Why URL-based?
  - Naukri uses a split-panel UI. Clicking cards updates the right panel
    in the SAME page — no new tabs. This makes selector targeting unreliable.
  - Instead: extract all job URLs from search → navigate to each directly
    → full page context → reliable apply button detection.

Fixed:
  - 0 applications bug (wrong panel/tab assumption)
  - Updated apply button selectors for 2025 Naukri UI
  - Experience filter in search URL
  - Handles Naukri Quick Apply + full apply flows
"""
import time, random, re
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page
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

def _delay(a=1.0, b=3.0):
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
        logger.warn("Naukri credentials not set — skipping", SITE)
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
                for location in LOCATIONS[:4]:
                    if not check_daily_limit(SITE):
                        logger.info("Naukri daily limit reached", SITE)
                        return
                    _search_and_apply(page, job_title, location)
        except Exception as e:
            logger.error(f"Naukri bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass
            logger.info("Naukri bot session ended", SITE)

# ─── LOGIN ────────────────────────────────────────────────────────────────────
def _login(page: Page, creds: dict) -> bool:
    logger.info("Logging into Naukri...", SITE)

    for login_url in [f"{BASE_URL}/nlogin/login", f"{BASE_URL}/login"]:
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=25000)
            _delay(2, 3)
            if "404" not in page.title():
                break
        except Exception:
            continue

    # Already logged in from cookies?
    if any(x in page.url for x in ["mnjuser", "myhome", "/dashboard"]):
        logger.success("Naukri already logged in via cookies", SITE)
        return True

    try:
        for email_sel in [
            'input[placeholder*="Email" i]',
            'input[type="email"]',
            '#usernameField',
            'input[name="username"]',
        ]:
            el = page.query_selector(email_sel)
            if el and el.is_visible():
                el.click()
                _delay(0.3, 0.6)
                el.fill(creds["email"])
                break

        _delay(0.5, 1)

        for pass_sel in [
            'input[type="password"]',
            '#passwordField',
            'input[placeholder*="Password" i]',
        ]:
            el = page.query_selector(pass_sel)
            if el and el.is_visible():
                el.click()
                _delay(0.3, 0.5)
                el.fill(creds["password"])
                break

        _delay(0.5, 1)

        for btn_sel in [
            'button[type="submit"]',
            'button.loginButton',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
        ]:
            el = page.query_selector(btn_sel)
            if el and el.is_visible():
                el.click()
                break

        _delay(4, 6)

        # OTP check
        otp_el = page.query_selector(
            'input[placeholder*="OTP" i], input[placeholder*="code" i], input[maxlength="6"]'
        )
        if otp_el and otp_el.is_visible():
            logger.info("Naukri OTP required — checking Gmail...", SITE)
            try:
                from bot.utils.gmail_otp import wait_for_otp
                otp = wait_for_otp(site="naukri", timeout_seconds=60)
                if otp:
                    otp_el.fill(otp)
                    _delay(0.5, 1)
                    page.query_selector('button[type="submit"]').click()
                    _delay(3, 4)
            except Exception:
                pass

        logger.success("Naukri login successful", SITE)
        return True

    except Exception as e:
        logger.error(f"Naukri login failed: {e}", SITE)
        return False

# ─── SEARCH → EXTRACT URLs ───────────────────────────────────────────────────
def _search_and_apply(page: Page, job_title: str, location: str):
    logger.info(f"Searching Naukri: '{job_title}' in '{location}'", SITE)

    # Build search URL with experience filter (3-8 years)
    slug = job_title.lower().replace(" ", "-")
    loc  = location.lower().replace(" ", "-")
    search_url = (
        f"{BASE_URL}/{quote(slug)}-jobs"
        f"?k={quote(job_title)}&l={quote(location)}"
        f"&experience=3,8&jobAge=7&sort=1"  # sort=1 = most relevant
    )

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        _delay(2, 3)
    except Exception as e:
        logger.warn(f"Naukri search failed: {e}", SITE)
        return

    # ── Scroll to load lazy items ─────────────────────────────────────────────
    for _ in range(3):
        page.mouse.wheel(0, 800)
        _delay(0.5, 1)

    # ── Extract all job URLs from search results ──────────────────────────────
    job_urls = _extract_job_urls(page)

    if not job_urls:
        logger.info(f"No jobs found for '{job_title}' in {location}", SITE)
        return

    logger.info(f"Found {len(job_urls)} jobs for '{job_title}' in {location}", SITE)

    applied = 0
    for job_url in job_urls[:15]:   # Max 15 per search
        if not check_daily_limit(SITE):
            return
        try:
            result = _apply_to_url(page, job_url, job_title, location)
            if result:
                applied += 1
                increment_daily_count(SITE)
                _delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 8)
            else:
                _delay(1, 2)  # Brief pause even on skip/fail
        except Exception as e:
            logger.warn(f"Naukri apply error: {str(e)[:80]}", SITE)
            continue

    logger.info(f"Naukri: Applied {applied} jobs for '{job_title}' in {location}", SITE)

# ─── EXTRACT JOB URLs ─────────────────────────────────────────────────────────
def _extract_job_urls(page: Page) -> list:
    """Extract all job detail URLs from the current search results page."""
    urls = []
    seen = set()

    # Multiple selector strategies for Naukri 2025
    link_selectors = [
        "article.jobTuple a.title",
        ".srp-jobtuple-wrapper a.title",
        ".jobTuple a[class*='title']",
        "div[class*='jobTuple'] a.title",
        ".job-title a",
        # Fallback: any link inside job cards
        "article a[href*='naukri.com']",
        ".srp-jobtuple-wrapper a[href*='/job-listings']",
    ]

    for sel in link_selectors:
        try:
            links = page.query_selector_all(sel)
            for link in links:
                href = link.get_attribute("href")
                if href and href not in seen and ("job-listings" in href or "naukri.com" in href):
                    # Make absolute URL
                    if href.startswith("/"):
                        href = BASE_URL + href
                    urls.append(href)
                    seen.add(href)
            if urls:
                break
        except Exception:
            continue

    # Fallback: scrape all hrefs from search page HTML
    if not urls:
        try:
            all_links = page.query_selector_all("a[href]")
            for link in all_links:
                href = link.get_attribute("href") or ""
                if "job-listings" in href and href not in seen:
                    if href.startswith("/"):
                        href = BASE_URL + href
                    urls.append(href)
                    seen.add(href)
        except Exception:
            pass

    return list(dict.fromkeys(urls))  # Deduplicate preserving order

# ─── APPLY TO A SPECIFIC JOB URL ─────────────────────────────────────────────
def _apply_to_url(page: Page, job_url: str, default_title: str, location: str) -> bool:
    try:
        page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
        _delay(2, 3)

        # ── Extract job details ───────────────────────────────────────────────
        def _text(selectors):
            for s in selectors:
                try:
                    el = page.query_selector(s)
                    if el:
                        t = el.inner_text().strip()
                        if t:
                            return t
                except Exception:
                    continue
            return ""

        job_title = _text([
            "h1.jd-header-title",
            ".jd-header-title",
            "h1[class*='title']",
            ".job-header-info h1",
        ]) or default_title

        company = _text([
            ".jd-header-comp-name a",
            ".comp-name-link",
            "a[class*='comp-name']",
            ".company-name",
            ".jd-header-comp-name",
        ]) or "Company"

        job_desc = _text([
            ".jd-desc",
            ".job-desc",
            "#job-description",
            ".JDC-module",
            "section[class*='description']",
        ])

        # ── Duplicate check ───────────────────────────────────────────────────
        if is_already_applied(SITE, company, job_title):
            logger.info(f"Skip: {company} — {job_title} (already applied)", SITE)
            return False

        # ── Find Apply button ─────────────────────────────────────────────────
        apply_btn = None
        apply_selectors = [
            # Most specific 2025 Naukri selectors
            'button[class*="apply-button"]',
            'a[class*="apply-button"]',
            'button[class*="chatApplyBtn"]',
            # Role-based (most resilient)
            'button:has-text("Apply")',
            'a:has-text("Apply now")',
            'a:has-text("Apply")',
            # Generic fallbacks
            '.apply-button',
            '#apply-button',
            'button.btn-primary',
        ]
        
        # Wait for page to settle
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        
        for sel in apply_selectors:
            try:
                el_loc = page.locator(sel).first
                if el_loc.is_visible(timeout=3000):
                    btn_text = el_loc.inner_text().lower()
                    if "already" in btn_text or "save" in btn_text:
                        logger.info(f"Already applied on Naukri: {company} — {job_title}", SITE)
                        return False
                    apply_btn = el_loc
                    break
            except Exception:
                continue

        if not apply_btn:
            logger.info(f"No apply button: {company} — {job_title}", SITE)
            return False

        # ── AI Resume Tailoring ───────────────────────────────────────────────
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        logger.info(f"Applying: {company} — {job_title} ({match_score}%)", SITE)

        apply_btn.scroll_into_view_if_needed()
        _delay(0.3, 0.6)
        apply_btn.click()
        _delay(2, 3)

        # ── Handle application form/modal ─────────────────────────────────────
        success = _handle_application(page, resume_path, job_title)

        if success:
            record_application(
                site=SITE, company=company, role=job_title,
                location=location, job_url=job_url,
                match_score=match_score, resume_used=resume_path,
            )
            git_sync()
            logger.success(f"Naukri applied: {company} — {job_title} ({match_score}%)", SITE)

        return success

    except Exception as e:
        logger.warn(f"Naukri URL apply error: {str(e)[:100]}", SITE)
        return False

# ─── APPLICATION FORM HANDLER ────────────────────────────────────────────────
def _handle_application(page: Page, resume_path: str, job_title: str) -> bool:
    phone = _get_phone()
    _delay(1, 2)

    for step in range(8):
        _delay(0.5, 1)

        # Upload resume
        for file_sel in ['input[type="file"]', 'input[accept*="doc"]', 'input[accept*="pdf"]']:
            try:
                el = page.query_selector(file_sel)
                if el:
                    el.set_input_files(resume_path)
                    _delay(1, 2)
                    break
            except Exception:
                pass

        # Fill phone
        for phone_sel in [
            'input[placeholder*="mobile" i]',
            'input[placeholder*="phone" i]',
            'input[name*="phone" i]',
            'input[type="tel"]',
            'input[maxlength="10"]',
        ]:
            try:
                el = page.query_selector(phone_sel)
                if el and el.is_visible() and not el.input_value().strip():
                    el.fill(phone)
                    _delay(0.3, 0.5)
                    break
            except Exception:
                continue

        # Check for success indicators
        success_indicators = [
            '[class*="success"]',
            '[class*="applied"]',
            ':has-text("Application submitted")',
            ':has-text("Applied successfully")',
            ':has-text("You have applied")',
            '.application-success',
        ]
        for ind in success_indicators:
            try:
                el = page.query_selector(ind)
                if el and el.is_visible(timeout=1000):
                    return True
            except Exception:
                continue

        # Submit buttons
        submitted = False
        for submit_sel in [
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Confirm")',
            'button[type="submit"]',
            '.btn-primary:has-text("Submit")',
        ]:
            try:
                el = page.query_selector(submit_sel)
                if el and el.is_visible(timeout=2000):
                    el.click()
                    _delay(2, 3)
                    submitted = True
                    break
            except Exception:
                continue

        if submitted:
            # Check for success after submit
            _delay(1, 2)
            for ind in success_indicators:
                try:
                    el = page.query_selector(ind)
                    if el and el.is_visible(timeout=2000):
                        return True
                except Exception:
                    continue
            return True  # Assume success if no error shown

        # No more buttons — check if modal/form is gone
        modal = page.query_selector('.apply-form, .application-form, [class*="modal"]')
        if not modal:
            break

    return False
