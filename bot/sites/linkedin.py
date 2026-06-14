"""
sites/linkedin.py — LinkedIn Easy Apply (Production Grade, 2025)

Key design principles:
  1. Role-based & label-based locators (resilient to UI changes)
  2. Persistent login via li_at cookie + user data dir
  3. Full form field handler: text, number, dropdown, radio, checkbox, textarea, file
  4. AI answers for unknown questions using profile.yaml as primary source
  5. Phone country code dropdown handled
  6. OTP/checkpoint auto-handled via Gmail
  7. Daily limit: 25/day (LinkedIn safe threshold)
  8. All actions mimic human behaviour (delays, scroll, click offset)
"""

import time, random, os, yaml
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.ai_router import ai_complete
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import (
    safe_browser_context, save_cookies,
    check_daily_limit, increment_daily_count,
    long_delay, medium_delay, short_delay
)

SITE     = "linkedin"
BASE_URL = "https://www.linkedin.com"

# ─── PROFILE LOADER ──────────────────────────────────────────────────────────
def _load_profile() -> dict:
    try:
        return yaml.safe_load(open("profile.yaml", encoding="utf-8"))
    except Exception:
        return {}

PROFILE = _load_profile()

def _get(key_path: str, default=""):
    """Get nested profile value by dot-path e.g. 'personal_info.phone'"""
    try:
        parts = key_path.split(".")
        val = PROFILE
        for p in parts:
            val = val[p]
        return str(val) if val is not None else default
    except Exception:
        return default

def _delay(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))

def _encode(t):
    return quote(str(t))

# ─── MAIN ENTRY ───────────────────────────────────────────────────────────────
def run_linkedin_bot():
    creds = CREDENTIALS["linkedin"]
    if not creds["email"] or not creds["password"]:
        logger.warn("LinkedIn credentials not set — skipping", SITE)
        return
    if not check_daily_limit(SITE):
        return

    logger.info("Starting LinkedIn Easy Apply bot — Production Mode", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()

        try:
            if not _login(page, creds):
                return
            save_cookies(context, SITE)

            for job_title in JOB_TITLES:
                for location in LOCATIONS:
                    if not check_daily_limit(SITE):
                        logger.info("LinkedIn daily limit (25) reached — stopping", SITE)
                        return
                    _search_and_apply(page, job_title, location)
        except Exception as e:
            logger.error(f"LinkedIn bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass
            logger.info("LinkedIn bot session ended", SITE)

# ─── LOGIN ────────────────────────────────────────────────────────────────────
def _login(page: Page, creds: dict) -> bool:
    logger.info("Logging into LinkedIn...", SITE)
    try:
        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=45000)
        _delay(2, 3)

        # Check if already logged in from cookies
        if any(x in page.url for x in ["/feed", "/jobs", "/mynetwork"]):
            logger.success("LinkedIn: already logged in via saved cookies", SITE)
            return True

        # Fill credentials using resilient locators
        email_loc = page.locator('#username, #session_key, input[name="session_key"], [autocomplete="username"]').first
        if email_loc.is_visible(timeout=5000):
            email_loc.fill(creds["email"])
        else:
            page.get_by_label(re.compile(r"email|phone", re.I)).first.fill(creds["email"])

        _delay(0.6, 1.2)

        pass_loc = page.locator('#password, #session_password, input[name="session_password"], [autocomplete="current-password"]').first
        if pass_loc.is_visible(timeout=5000):
            pass_loc.fill(creds["password"])
        else:
            page.get_by_label(re.compile(r"password", re.I)).first.fill(creds["password"])
        _delay(0.5, 1.0)
        # Click Sign in button
        for btn_sel in ['button[type="submit"]', '[data-litms-control-urn*="sign_in"]']:
            try:
                el = page.query_selector(btn_sel)
                if el and el.is_visible():
                    el.click()
                    break
            except Exception:
                continue
        _delay(3, 5)

        # Handle OTP / security checkpoint / CAPTCHA
        if any(x in page.url for x in ["checkpoint", "challenge", "pin"]):
            logger.info("LinkedIn security check — auto-reading OTP from Gmail...", SITE)
            try:
                from bot.utils.gmail_otp import fill_otp_on_page
                filled = fill_otp_on_page(page, site="linkedin", timeout=90)
                if not filled:
                    logger.warn("OTP not auto-filled — please enter it manually in the browser", SITE)
                    # Wait up to 2 minutes for user to solve manually
                    page.wait_for_url(re.compile(r".*/(feed|jobs|mynetwork).*"), timeout=120000)
            except Exception as e:
                logger.warn(f"OTP handler error: {e}", SITE)
                page.wait_for_url(re.compile(r".*/(feed|jobs|mynetwork).*"), timeout=120000)

        # Wait longer for CAPTCHAs that don't change URL immediately
        logger.info("Waiting for login success... (Solve CAPTCHA if it appears)", SITE)
        page.wait_for_url(re.compile(r".*/(feed|jobs|mynetwork).*"), timeout=60000)
        logger.success("LinkedIn login successful", SITE)
        return True

    except PWTimeout:
        logger.error("LinkedIn login timeout — check credentials or solve CAPTCHA", SITE)
        return False
    except Exception as e:
        logger.error(f"LinkedIn login failed: {e}", SITE)
        return False

# ─── JOB SEARCH ───────────────────────────────────────────────────────────────
def _search_and_apply(page: Page, job_title: str, location: str):
    logger.info(f"LinkedIn search: '{job_title}' in '{location}'", SITE)

    # Target Visa Sponsorship for international locations
    search_keyword = job_title
    india_locs = ["bangalore", "chennai", "hyderabad", "pune", "mumbai", "delhi", "india"]
    if not any(loc in location.lower() for loc in india_locs):
        search_keyword = f"{job_title} visa sponsorship"

    search_url = (
        f"{BASE_URL}/jobs/search/?keywords={_encode(search_keyword)}"
        f"&location={_encode(location)}"
        f"&f_AL=true"       # Easy Apply only
        f"&f_TPR=r86400"    # Last 24 hours
        f"&f_E=4"           # Mid-Senior level (typically 4-8 years)
        f"&sortBy=DD"       # Most recent first
    )

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Search page load failed: {e}", SITE)
        return

    _delay(2, 4)

    # Scroll to load all jobs
    for _ in range(3):
        page.mouse.wheel(0, 600)
        _delay(0.5, 1)

    applied_count = 0

    for page_num in range(3):  # Max 3 pages per search
        # Resilient job card selectors
        jobs = page.query_selector_all(
            "li.jobs-search-results__list-item, "
            ".scaffold-layout__list-item, "
            "li[class*='ember-view'][class*='result']"
        )

        if not jobs:
            logger.info(f"No more jobs on page {page_num + 1}", SITE)
            break

        logger.info(f"Found {len(jobs)} jobs on page {page_num + 1}", SITE)

        for job_el in jobs:
            if not check_daily_limit(SITE):
                return
            try:
                result = _apply_to_job(page, job_el)
                if result:
                    applied_count += 1
                    increment_daily_count(SITE)
                    _delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 8)
            except Exception as e:
                logger.warn(f"Job error: {str(e)[:80]}", SITE)
                # Close any open modal before continuing
                try:
                    page.keyboard.press("Escape")
                    _delay(0.5, 1)
                except Exception:
                    pass
                continue

        # Navigate to next page
        try:
            next_btn = page.get_by_role("button", name="View next page")
            if next_btn.is_visible(timeout=3000):
                next_btn.click()
                _delay(2, 4)
            else:
                break
        except Exception:
            break

    logger.info(f"LinkedIn: Applied {applied_count} jobs for '{job_title}' in {location}", SITE)

# ─── SINGLE JOB APPLICATION ──────────────────────────────────────────────────
def _apply_to_job(page: Page, job_el) -> bool:
    try:
        # Click job card
        job_el.scroll_into_view_if_needed()
        _delay(0.3, 0.6)
        job_el.click()
        _delay(1.5, 2.5)

        # Extract job details — using resilient multi-selector approach
        def _text(selectors: list) -> str:
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        txt = el.inner_text().strip()
                        if txt:
                            return txt
                except Exception:
                    continue
            return ""

        job_title = _text([
            "h1.t-24", "h1.t-bold",
            ".job-details-jobs-unified-top-card__job-title h1",
            ".jobs-unified-top-card__job-title h1",
            ".jobs-unified-top-card__job-title",
        ]) or "Unknown Role"

        company = _text([
            ".job-details-jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__company-name",
            ".job-details-jobs-unified-top-card__company-name",
        ]) or "Unknown Company"

        location = _text([
            ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
            ".jobs-unified-top-card__bullet",
            ".jobs-unified-top-card__workplace-type",
        ]) or "Unknown"

        job_desc = _text([
            "#job-details",
            ".jobs-description__content .jobs-box__html-content",
            ".jobs-description-content__text",
        ])

        job_url = page.url

        # Check Easy Apply button — use role-based (resilient)
        easy_btn = None
        for btn_locator in [
            page.get_by_role("button", name="Easy Apply"),
            page.locator(".jobs-apply-button--top-card button"),
            page.locator("button.jobs-apply-button"),
            page.locator("button[aria-label*='Easy Apply']"),
        ]:
            try:
                if btn_locator.first.is_visible(timeout=2000):
                    easy_btn = btn_locator.first
                    break
            except Exception:
                continue

        if not easy_btn:
            return False  # Not Easy Apply

        if is_already_applied(SITE, company, job_title):
            logger.info(f"Skip: {company} — {job_title} (already applied)", SITE)
            return False

        # AI tailor resume
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        logger.info(f"Applying: {company} — {job_title} ({match_score}% match)", SITE)

        easy_btn.scroll_into_view_if_needed()
        _delay(0.3, 0.6)
        easy_btn.click()
        _delay(1.5, 2.5)

        # Fill Easy Apply modal
        success = _fill_easy_apply_modal(page, resume_path, job_title, company, job_desc)

        if success:
            record_application(
                site=SITE, company=company, role=job_title,
                location=location, job_url=job_url,
                match_score=match_score, resume_used=resume_path,
            )
            git_sync()

        return success

    except Exception as e:
        logger.warn(f"Apply error: {str(e)[:100]}", SITE)
        return False

# ─── EASY APPLY MODAL (PRODUCTION GRADE) ────────────────────────────────────
def _fill_easy_apply_modal(page: Page, resume_path: str,
                            job_title: str, company: str, job_desc: str) -> bool:
    """
    Step through LinkedIn Easy Apply modal.
    Handles: resume upload, phone, all question types, multi-step navigation.
    """
    phone      = _get("personal_info.phone", "+916383149155")
    phone_local = _get("personal_info.phone_local", "6383149155")

    for step in range(20):  # LinkedIn can have up to ~15 steps
        _delay(1, 2)

        modal = page.query_selector(
            ".jobs-easy-apply-modal, "
            ".artdeco-modal--layer-confirmation, "
            "[data-test-modal]"
        )
        if not modal:
            break

        # ── 1. Resume upload ─────────────────────────────────────────────────
        file_input = page.query_selector('input[type="file"]')
        if file_input:
            try:
                file_input.set_input_files(resume_path)
                _delay(1, 2)
            except Exception:
                pass

        # ── 2. Phone number (country code + number) ──────────────────────────
        _fill_phone(page, phone, phone_local)

        # ── 3. Handle all form fields on this step ───────────────────────────
        _fill_all_form_fields(page, job_title, company, job_desc)

        # ── 4. Unfollow company (avoid spam emails) ───────────────────────────
        try:
            follow_label = page.query_selector('label[for*="follow"]')
            if follow_label:
                checkbox = page.query_selector('input[id*="follow"]')
                if checkbox and checkbox.is_checked():
                    follow_label.click()
                    _delay(0.2, 0.4)
        except Exception:
            pass

        # ── 5. Navigation ─────────────────────────────────────────────────────
        # Submit
        try:
            submit = page.get_by_role("button", name="Submit application")
            if submit.is_visible(timeout=2000):
                submit.click()
                _delay(1.5, 2.5)
                # Dismiss success dialog
                try:
                    page.get_by_role("button", name="Dismiss").click(timeout=3000)
                except Exception:
                    pass
                logger.success(f"LinkedIn Easy Apply submitted: {company} — {job_title}", SITE)
                return True
        except Exception:
            pass

        # Review
        try:
            review = page.get_by_role("button", name="Review your application")
            if review.is_visible(timeout=1000):
                review.click()
                _delay(1, 2)
                continue
        except Exception:
            pass

        # Next
        try:
            nxt = page.get_by_role("button", name="Continue to next step")
            if nxt.is_visible(timeout=1000):
                nxt.click()
                _delay(1, 2)
                continue
        except Exception:
            pass

        # Nothing to click — modal may have closed or errored
        if not page.query_selector(".jobs-easy-apply-modal, .artdeco-modal"):
            break

    # If we exited without submitting, discard
    try:
        page.get_by_role("button", name="Discard").click(timeout=3000)
        _delay(0.5, 1)
        page.get_by_role("button", name="Discard").click(timeout=3000)
    except Exception:
        pass

    return False

# ─── PHONE FILLER ────────────────────────────────────────────────────────────
def _fill_phone(page: Page, phone: str, phone_local: str):
    try:
        # Country code dropdown
        country_dropdown = page.query_selector(
            'select[id*="phoneNumber-country"], '
            '.phone-number__country-code select, '
            'select[aria-label*="Phone country code"]'
        )
        if country_dropdown:
            try:
                country_dropdown.select_option(value="in")  # India
            except Exception:
                country_dropdown.select_option(index=1)

        # Phone number input
        for sel in [
            'input[id*="phoneNumber-nationalNumber"]',
            'input[name*="phoneNumber"]',
            'input[id*="phone"]',
            'input[aria-label*="Phone number" i]',
            page.get_by_label("Phone number"),
        ]:
            try:
                if isinstance(sel, str):
                    el = page.query_selector(sel)
                    if el and el.is_visible() and not el.input_value().strip():
                        el.click()
                        el.fill(phone_local)
                        break
                else:
                    # Playwright locator
                    if sel.is_visible(timeout=1000) and not sel.input_value().strip():
                        sel.fill(phone_local)
                        break
            except Exception:
                continue
    except Exception:
        pass

# ─── ALL FORM FIELDS HANDLER ─────────────────────────────────────────────────
def _fill_all_form_fields(page: Page, job_title: str, company: str, job_desc: str):
    """
    Detect and fill ALL form fields on the current modal step.
    Uses profile.yaml first, then AI for unknown questions.
    """
    standard = PROFILE.get("standard_answers", {})

    # ── Text / Textarea inputs ────────────────────────────────────────────────
    inputs = page.query_selector_all(
        '.jobs-easy-apply-form-section__grouping input[type="text"],'
        '.jobs-easy-apply-form-section__grouping input[type="number"],'
        '.jobs-easy-apply-form-section__grouping textarea'
    )
    for el in inputs:
        try:
            if not el.is_visible() or el.input_value().strip():
                continue  # Skip hidden or already filled
            label = _get_field_label(page, el)
            answer = _answer_for(label, job_title, company, job_desc, standard)
            if answer:
                el.click()
                _delay(0.2, 0.4)
                el.fill(str(answer))
                _delay(0.2, 0.5)
        except Exception:
            continue

    # ── Select dropdowns ──────────────────────────────────────────────────────
    selects = page.query_selector_all(
        '.jobs-easy-apply-form-section__grouping select'
    )
    for sel in selects:
        try:
            if not sel.is_visible():
                continue
            current = sel.evaluate("e => e.value")
            if current and current != "Select an option":
                continue  # Already selected
            label   = _get_field_label(page, sel)
            options = sel.evaluate("e => Array.from(e.options).map(o => o.text)")
            answer  = _answer_for_dropdown(label, options, job_title, company, job_desc, standard)
            if answer:
                try:
                    sel.select_option(label=answer)
                except Exception:
                    sel.select_option(index=1)  # Pick first real option
            _delay(0.2, 0.4)
        except Exception:
            continue

    # ── Radio buttons ─────────────────────────────────────────────────────────
    radio_groups = page.query_selector_all(
        '.jobs-easy-apply-form-section__grouping fieldset'
    )
    for group in radio_groups:
        try:
            question = group.query_selector("legend")
            if not question:
                continue
            q_text = question.inner_text().strip()

            # Check if already answered
            checked = group.query_selector('input[type="radio"]:checked')
            if checked:
                continue

            radios = group.query_selector_all('input[type="radio"]')
            labels = group.query_selector_all('label')
            options = [l.inner_text().strip() for l in labels]

            answer = _answer_for(q_text, job_title, company, job_desc, standard)
            if not answer:
                answer = _ai_answer(q_text, options, job_title, company, job_desc)

            # Click matching label
            answered = False
            for label in labels:
                if answer.lower() in label.inner_text().lower():
                    label.click()
                    answered = True
                    break
            if not answered and labels:
                # Default: click "Yes" or first option
                for label in labels:
                    if "yes" in label.inner_text().lower():
                        label.click()
                        break
                else:
                    labels[0].click()
            _delay(0.2, 0.4)
        except Exception:
            continue

# ─── LABEL EXTRACTOR ─────────────────────────────────────────────────────────
def _get_field_label(page: Page, el) -> str:
    """Get the label text associated with a form element."""
    try:
        # Try aria-label
        aria = el.get_attribute("aria-label")
        if aria:
            return aria.strip()

        # Try associated <label>
        el_id = el.get_attribute("id")
        if el_id:
            label = page.query_selector(f'label[for="{el_id}"]')
            if label:
                return label.inner_text().strip()

        # Try parent label
        parent = el.evaluate("e => e.closest('.jobs-easy-apply-form-element')?.querySelector('label')?.textContent")
        if parent:
            return parent.strip()

        # Try placeholder
        ph = el.get_attribute("placeholder")
        if ph:
            return ph.strip()
    except Exception:
        pass
    return ""

# ─── ANSWER ENGINE ────────────────────────────────────────────────────────────
def _answer_for(question: str, job_title: str, company: str,
                job_desc: str, standard: dict) -> str:
    """Find best answer: profile standard_answers → profile fields → AI."""
    q_lower = question.lower()

    # 1. Direct match in standard_answers
    for key, val in standard.items():
        if key.lower() in q_lower or q_lower in key.lower():
            return str(val)

    # 2. Common field matching from profile
    pi = PROFILE.get("personal_info", {})
    if any(x in q_lower for x in ["first name", "firstname"]):
        return pi.get("first_name", "Siva Shankar")
    if any(x in q_lower for x in ["last name", "lastname", "surname"]):
        return pi.get("last_name", "V")
    if any(x in q_lower for x in ["full name", "your name"]):
        return pi.get("full_name", "Siva Shankar V")
    if any(x in q_lower for x in ["email", "e-mail"]):
        return pi.get("email", "sivashankar.avi6@gmail.com")
    if any(x in q_lower for x in ["phone", "mobile", "contact number"]):
        return pi.get("phone_local", "6383149155")
    if any(x in q_lower for x in ["linkedin", "linkedin url", "linkedin profile"]):
        return pi.get("linkedin", "")
    if any(x in q_lower for x in ["github", "portfolio"]):
        return pi.get("github", "")
    if any(x in q_lower for x in ["city", "location", "where are you"]):
        return pi.get("city", "Chennai")
    if any(x in q_lower for x in ["years of experience", "total experience"]):
        return str(PROFILE.get("experience_summary", {}).get("total_years", 5))
    if any(x in q_lower for x in ["notice period", "notice"]):
        return "30 days"
    if any(x in q_lower for x in ["salary", "ctc", "compensation", "expected"]):
        return PROFILE.get("preferences", {}).get("expected_salary", "Open to negotiation")
    if any(x in q_lower for x in ["relocat"]):
        return "Yes"
    if any(x in q_lower for x in ["sponsor", "visa", "work authoriz"]):
        return "Yes, I will require sponsorship for positions outside India"
    if any(x in q_lower for x in ["authorized", "authorised", "eligible to work"]):
        return "Yes" if "india" in q_lower else "No"

    # 3. Years of experience for specific tech
    exp = PROFILE.get("experience_summary", {})
    if "years" in q_lower or "experience with" in q_lower:
        skills = [".net", "c#", "azure", "react", "sql", "python", "javascript"]
        for skill in skills:
            if skill in q_lower:
                return "5" if skill in [".net", "c#", "sql"] else "3"
        return str(exp.get("total_years", 5))

    return ""  # Let AI handle it

def _answer_for_dropdown(question: str, options: list, job_title: str,
                          company: str, job_desc: str, standard: dict) -> str:
    """Find the best dropdown option."""
    answer = _answer_for(question, job_title, company, job_desc, standard)
    if answer:
        # Find best matching option
        for opt in options:
            if answer.lower() in opt.lower() or opt.lower() in answer.lower():
                return opt
    # Use AI for unknown dropdowns
    return _ai_answer_dropdown(question, options, job_title, company, job_desc)

def _ai_answer(question: str, options: list, job_title: str,
               company: str, job_desc: str) -> str:
    """Use Groq AI to answer an unknown question."""
    try:
        system = (
            "You are filling a job application form for Siva Shankar V, "
            "a Senior .NET Developer with 5 years experience from Chennai, India. "
            "Give the most appropriate, professional answer. Be concise."
        )
        user = (
            f"Job: {job_title} at {company}\n"
            f"Question: {question}\n"
            f"Options (if multiple choice): {options}\n"
            f"Answer with just the value, no explanation:"
        )
        return ai_complete(system, user, task="form_fill", max_tokens=100).strip()
    except Exception:
        return options[0] if options else "Yes"

def _ai_answer_dropdown(question: str, options: list, job_title: str,
                         company: str, job_desc: str) -> str:
    """Use AI to pick the best dropdown option."""
    try:
        system = (
            "You are filling a job application form. Pick the EXACT option text "
            "from the list that best fits. Reply with ONLY the option text."
        )
        user = (
            f"Question: {question}\n"
            f"Options: {options}\n"
            f"Candidate: Senior .NET Developer, 5yrs exp, India"
        )
        ai_answer = ai_complete(system, user, task="form_fill", max_tokens=50).strip()
        # Validate it's actually one of the options
        for opt in options:
            if ai_answer.lower() in opt.lower() or opt.lower() in ai_answer.lower():
                return opt
        return options[0] if len(options) > 0 else ""
    except Exception:
        return options[0] if options else ""
