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
  9. VISIBLE field-by-field form filling with console logging
  10. Relevance filter: skip jobs below MIN_MATCH_SCORE
"""

import time, random, os, yaml, re
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume, check_tech_stack_relevance, check_experience_relevance
from bot.ai_router import ai_complete
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import (
    safe_browser_context, save_cookies,
    check_daily_limit, increment_daily_count,
    long_delay, medium_delay, short_delay,
    field_log, human_fill, select_best_resume_file
)

SITE       = "linkedin"
BASE_URL   = "https://www.linkedin.com"
MIN_MATCH  = int(os.getenv("MIN_MATCH_SCORE", "60"))   # Only apply if >= this % match

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

def _generate_profile_query() -> str:
    """Dynamically build an optimized boolean search query from the candidate's profile.yaml stack."""
    try:
        primary_stack = PROFILE.get("experience_summary", {}).get("primary_stack", [])
        if not primary_stack:
            return ".Net"
        
        languages = []
        frameworks = []
        others = []
        
        for skill in primary_stack:
            s_clean = skill.strip()
            s_lower = s_clean.lower()
            if s_lower in ["c#", "csharp"]:
                if "C#" not in languages:
                    languages.append("C#")
            elif s_lower in [".net core", ".net", "dotnet", "asp.net web api", "asp.net mvc", "asp.net"]:
                if ".NET" not in frameworks:
                    frameworks.append(".NET")
            elif s_lower in ["azure", "angular", "sql server", "sql"]:
                val = "SQL Server" if s_lower == "sql server" else s_clean
                if val not in others:
                    others.append(val)
                    
        core_parts = []
        if languages:
            langs_str = '" OR "'.join(languages)
            core_parts.append(f'("{langs_str}")')
        if frameworks:
            frams_str = '" OR "'.join(frameworks)
            core_parts.append(f'("{frams_str}")')
            
        core_query = " AND ".join(core_parts) if core_parts else ".NET"
        
        # Exclude unwanted roles dynamically in search keywords to keep quality high
        exclusions = 'NOT ("QA" OR "Tester" OR "Scrum Master" OR "Java" OR "Python" OR "PHP" OR "Android" OR "iOS")'
        
        if others:
            others_str = '" OR "'.join(others)
            other_query = f'("{others_str}")'
            query = f'{core_query} AND {other_query} {exclusions}'
        else:
            query = f'{core_query} {exclusions}'
            
        return query
    except Exception:
        return ".Net"

# ─── MAIN ENTRY ───────────────────────────────────────────────────────────────
def run_linkedin_bot():
    creds = CREDENTIALS["linkedin"]
    if not creds["email"] or not creds["password"]:
        logger.warn("LinkedIn credentials not set — skipping", SITE)
        return
    if not check_daily_limit(SITE):
        return

    logger.info("Starting LinkedIn Easy Apply bot — Production Mode", SITE)
    print(f"\n{'='*60}")
    print(f"  LINKEDIN BOT — Headful Mode (Watch the browser!)")
    print(f"  Min match score to apply: {MIN_MATCH}%")
    print(f"{'='*60}\n")

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            if not _login(page, creds):
                return
            save_cookies(context, SITE)

            for job_title in JOB_TITLES:
                if not check_daily_limit(SITE):
                    logger.info("LinkedIn daily limit (25) reached — stopping", SITE)
                    return
                _search_and_apply(page, job_title, "Worldwide")
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

        # Check if already logged in natively
        try:
            url = page.url
            if any(x in url for x in ["/feed", "/jobs", "/mynetwork", "/messaging", "/notifications"]):
                logger.success("LinkedIn: already logged in via persistent session (URL check)", SITE)
                return True
            for sel in [".global-nav", "#global-nav", "a[href*='/feed/']", "button[aria-label*='Primary Navigation']"]:
                if page.locator(sel).first.is_visible():
                    logger.success("LinkedIn: already logged in via persistent session (selector check)", SITE)
                    return True
        except Exception:
            pass

        # Fill credentials
        email_loc = page.locator('#username, #session_key, input[name="session_key"], [autocomplete="username"]').first
        if email_loc.is_visible():
            field_log("fill", "Email", creds["email"], SITE)
            email_loc.fill(creds["email"])
            _delay(0.6, 1.2)

            pass_loc = page.locator('#password, #session_password, input[name="session_password"], [autocomplete="current-password"]').first
            if pass_loc.is_visible():
                field_log("fill", "Password", "***", SITE)
                pass_loc.fill(creds["password"])
            _delay(0.5, 1.0)

            for btn_sel in ['button[type="submit"]', '[data-litms-control-urn*="sign_in"]']:
                try:
                    el = page.query_selector(btn_sel)
                    if el and el.is_visible():
                        field_log("click", "Sign In button", "", SITE)
                        el.click()
                        break
                except Exception:
                    continue
            _delay(3, 5)
        else:
            logger.info("Login fields not found — may already be logged in or CAPTCHA present", SITE)

        # Handle OTP / security checkpoint
        if any(x in page.url for x in ["checkpoint", "challenge", "pin"]):
            logger.info("LinkedIn security check — auto-reading OTP from Gmail...", SITE)
            try:
                from bot.utils.gmail_otp import fill_otp_on_page
                filled = fill_otp_on_page(page, site="linkedin", timeout=90)
                if not filled:
                    logger.warn("OTP not auto-filled — please enter it manually in the browser", SITE)
                    page.wait_for_url(re.compile(r".*/(feed|jobs|mynetwork).*"), timeout=120000)
            except Exception as e:
                logger.warn(f"OTP handler error: {e}", SITE)
                page.wait_for_url(re.compile(r".*/(feed|jobs|mynetwork).*"), timeout=120000)

        logger.info("Waiting for login success... (Solve CAPTCHA manually if shown — 3 min window)", SITE)
        success = False
        for _ in range(90):  # 90 * 2 = 180 seconds (3 mins)
            try:
                url = page.url
                if any(x in url for x in ["/feed", "/jobs", "/mynetwork", "/messaging", "/notifications", "/search"]):
                    success = True
                    break
                for sel in [".global-nav", "#global-nav", "a[href*='/feed/']", "button[aria-label*='Primary Navigation']"]:
                    if page.locator(sel).first.is_visible():
                        success = True
                        break
                if success:
                    break
            except Exception:
                pass
            time.sleep(2)

        if success:
            logger.success("LinkedIn login successful", SITE)
            return True
        else:
            raise PWTimeout("LinkedIn login timeout")

    except PWTimeout:
        logger.error("LinkedIn login timeout — check credentials or solve CAPTCHA", SITE)
        return False
    except Exception as e:
        logger.error(f"LinkedIn login failed: {e}", SITE)
        return False

# ─── JOB SEARCH ───────────────────────────────────────────────────────────────
def _search_and_apply(page: Page, job_title: str, location: str):
    logger.info(f"LinkedIn search: '{job_title}' in '{location}'", SITE)

    if job_title.lower() in [".net", "dotnet"]:
        search_query = _generate_profile_query()
    else:
        search_query = job_title

    time_range = "r604800"  # Past week (to find more opportunities worldwide)
    logger.info(f"Searching for: {search_query} (Past Week)", SITE)

    search_url = (
        f"{BASE_URL}/jobs/search/?keywords={_encode(search_query)}"
        f"&location={_encode(location)}"
        f"&f_TPR={time_range}"
        f"&f_E=4"           # Mid-Senior level
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
            try:
                res = _apply_to_job(page, job_el)
                if isinstance(res, tuple):
                    success, apply_type = res
                else:
                    success, apply_type = res, "easy"

                if success:
                    applied_count += 1
                    if apply_type == "easy":
                        increment_daily_count(SITE)
                    _delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 8)
            except Exception as e:
                logger.warn(f"Job error: {str(e)[:80]}", SITE)
                try:
                    page.keyboard.press("Escape")
                    _delay(0.5, 1)
                except Exception:
                    pass
                continue

        # Navigate to next page
        try:
            next_btn = page.get_by_role("button", name="View next page")
            if next_btn.is_visible():
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
        # Scroll and click job link or element robustly
        try:
            job_link = job_el.query_selector("a.job-card-container__link, a[href*='/jobs/view/'], .job-card-list__title")
            if job_link:
                job_link.scroll_into_view_if_needed()
                _delay(0.3, 0.6)
                job_link.click(timeout=8000)
            else:
                job_el.scroll_into_view_if_needed()
                _delay(0.3, 0.6)
                job_el.click(timeout=8000)
        except Exception:
            try:
                job_el.scroll_into_view_if_needed()
                _delay(0.3, 0.6)
                job_el.click(timeout=10000)
            except Exception as click_err:
                logger.warn(f"Failed to click job element: {str(click_err)[:80]}", SITE)
                return False
        _delay(1.5, 2.5)

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

        # Clean job title (remove location keywords)
        job_title = re.sub(r'\s+', ' ', job_title).strip()
        job_title = re.sub(r'\b(Job\s+)?in\s+.*$', '', job_title, flags=re.IGNORECASE).strip()
        job_title = re.sub(r'\b(Johor|Selangor|Kuala Lumpur|Shah Alam|Subang|Bangalore|Chennai|Remote|Singapore|Malaysia|India).*$', '', job_title, flags=re.IGNORECASE).strip()
        job_title = re.sub(r'[\s\-,\/\|\(\)]+$', '', job_title).strip()

        company = _text([
            ".job-details-jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__company-name",
            ".job-details-jobs-unified-top-card__company-name",
        ]) or "Unknown Company"

        location = _text([
            ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
            ".job-details-jobs-unified-top-card__primary-description",
            ".jobs-unified-top-card__primary-description",
            ".jobs-unified-top-card__bullet",
            ".jobs-unified-top-card__workplace-type",
        ]) or "Unknown"

        # India Exclusions Filter
        india_keywords = {"india", "bangalore", "bengaluru", "chennai", "hyderabad", "mumbai", "pune", "delhi", "noida", "gurgaon", "gurugram", "kolkata", "kochi", "coimbatore", "kerala"}
        if any(k in location.lower() for k in india_keywords):
            field_log("skip", f"{company} — {job_title}", f"Location is India ({location}) — skipping", SITE)
            return False

        job_desc = _text([
            "#job-details",
            ".jobs-description__content .jobs-box__html-content",
            ".jobs-description-content__text",
        ])

        # 2. Technology Stack Check (Fast Filter)
        is_tech_ok, tech_reason = check_tech_stack_relevance(job_title, job_desc)
        if not is_tech_ok:
            field_log("skip", f"{company} — {job_title}", f"Tech stack mismatch: {tech_reason}", SITE)
            return False

        # 3. Experience Relevance Check (Fast Filter)
        is_exp_ok, exp_reason = check_experience_relevance(job_desc, job_title)
        if not is_exp_ok:
            field_log("skip", f"{company} — {job_title}", f"Experience mismatch: {exp_reason}", SITE)
            return False

        job_url = page.url

        if is_already_applied(SITE, company, job_title):
            field_log("skip", f"{company} — {job_title}", "Already applied", SITE)
            return False

        # Check Easy Apply or regular Apply buttons
        easy_btn = None
        for btn_locator in [
            page.get_by_role("button", name="Easy Apply"),
            page.locator("button[aria-label*='Easy Apply' i]"),
            page.locator("button:has-text('Easy Apply')"),
            page.locator("button:has-text('easy apply')"),
        ]:
            try:
                if btn_locator.first.is_visible():
                    easy_btn = btn_locator.first
                    break
            except Exception:
                continue

        apply_btn = None
        if not easy_btn:
            for btn_locator in [
                page.locator("button[aria-label*='Apply to' i]:not([aria-label*='Easy Apply' i])"),
                page.locator("a[aria-label*='Apply to' i]:not([aria-label*='Easy Apply' i])"),
                page.locator("button:has-text('Apply')").locator("visible=true"),
                page.locator("a:has-text('Apply')").locator("visible=true"),
                page.locator(".jobs-apply-button"),
            ]:
                try:
                    if btn_locator.first.is_visible():
                        apply_btn = btn_locator.first
                        break
                except Exception:
                    continue

        if not easy_btn and not apply_btn:
            field_log("skip", f"{company} — {job_title}", "No apply buttons found", SITE)
            return False

        if easy_btn:
            if not check_daily_limit(SITE):
                field_log("skip", f"{company} — {job_title}", "Easy Apply daily limit reached", SITE)
                return False

            # ── RELEVANCE FILTER ────────────────────────────────────────────────
            tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
            resume_path   = tailor_result["resume_path"]
            match_score   = tailor_result["match_score"]

            if not resume_path:
                field_log("skip", f"{company} — {job_title}", "Tech stack or experience mismatch (tailoring)", SITE)
                return False

            if match_score < MIN_MATCH:
                field_log("skip", f"{company} — {job_title}", f"Match {match_score}% < {MIN_MATCH}% threshold", SITE)
                return False

            print(f"\n  {'─'*55}")
            print(f"  🎯 APPLYING (EASY APPLY): {company} — {job_title}")
            print(f"     Match: {match_score}% | Location: {location}")
            print(f"  {'─'*55}")

            easy_btn.scroll_into_view_if_needed()
            _delay(0.3, 0.6)
            field_log("click", "Easy Apply button", "", SITE)
            easy_btn.click()
            _delay(1.5, 2.5)

            success = _fill_easy_apply_modal(
                page, resume_path, job_title, company, job_desc, location,
                resume_pdf_path=tailor_result.get("resume_pdf_path", "")
            )

            if success:
                record_application(
                    site=SITE, company=company, role=job_title,
                    location=location, job_url=job_url,
                    match_score=match_score, resume_used=resume_path,
                )
                git_sync()

            return success, "easy"

        elif apply_btn:
            print(f"\n  {'─'*55}")
            print(f"  🎯 CAPTURING EXTERNAL APPLY: {company} — {job_title}")
            print(f"     Location: {location}")
            print(f"  {'─'*55}")

            apply_btn.scroll_into_view_if_needed()
            _delay(0.3, 0.6)
            field_log("click", "Apply (External) button", "", SITE)

            # Click and wait for the redirected external page in a popup
            external_url = None
            try:
                with page.context.expect_page(timeout=15000) as new_page_info:
                    apply_btn.click()
                new_page = new_page_info.value
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                _delay(1, 2)
                external_url = new_page.url
                new_page.close()
            except Exception as pop_err:
                logger.warn(f"Failed to capture external redirect popup: {pop_err}", SITE)
                try:
                    href = apply_btn.get_attribute("href")
                    if href:
                        external_url = urljoin(BASE_URL, href)
                except Exception:
                    pass

            if not external_url:
                field_log("error", f"{company} — {job_title}", "Could not capture external URL", SITE)
                return False

            if "linkedin.com/jobs/view/" in external_url or "linkedin.com/jobs/search/" in external_url:
                field_log("warn", f"{company} — {job_title}", "Redirected back to LinkedIn. Saving original job URL.", SITE)
                external_url = job_url

            bulk_file = r"E:\SivaShankar\jobbot\data\bulk_urls.txt"
            os.makedirs(os.path.dirname(bulk_file), exist_ok=True)

            already_in_bulk = False
            if os.path.exists(bulk_file):
                try:
                    with open(bulk_file, "r", encoding="utf-8") as f:
                        bulk_content = f.read()
                        if external_url in bulk_content:
                            already_in_bulk = True
                except Exception:
                    pass

            if already_in_bulk:
                field_log("skip", f"{company} — {job_title}", "URL already in bulk_urls.txt", SITE)
                return False

            try:
                with open(bulk_file, "a", encoding="utf-8") as f:
                    f.write(f"\n# {company} — {job_title} ({location})\n{external_url}\n")
                logger.success(f"Saved external URL for {company} — {job_title} to bulk_urls.txt", SITE)
                return True, "external"
            except Exception as write_err:
                logger.error(f"Failed to save external URL: {write_err}", SITE)
                return False

    except Exception as e:
        logger.warn(f"Apply error: {str(e)[:100]}", SITE)
        return False

# ─── EASY APPLY MODAL (PRODUCTION GRADE) ────────────────────────────────────
def _fill_easy_apply_modal(page: Page, resume_path: str,
                            job_title: str, company: str, job_desc: str,
                            location: str = "Worldwide", resume_pdf_path: str = "") -> bool:
    """
    Step through LinkedIn Easy Apply modal with FULL field coverage.
    Handles: resume upload, phone, text, number, textarea,
             dropdown, radio, checkbox — ALL logged field-by-field.
    """
    phone       = _get("personal_info.phone", "+916383149155")
    phone_local = _get("personal_info.phone_local", "6383149155")

    for step in range(20):  # LinkedIn can have up to ~15 steps
        _delay(1, 1.5)

        modal = page.query_selector(
            ".jobs-easy-apply-modal, "
            ".artdeco-modal--layer-confirmation, "
            "[data-test-modal]"
        )
        if not modal:
            break

        field_log("step", f"Modal Step {step + 1}", "", SITE)

        # ── 1. Resume upload ─────────────────────────────────────────────────
        file_input = page.query_selector('input[type="file"]')
        if file_input:
            try:
                best_resume = select_best_resume_file(page, file_input, resume_path, resume_pdf_path)
                field_log("upload", "Resume file", os.path.basename(best_resume), SITE)
                file_input.set_input_files(best_resume)
                _delay(1, 2)
            except Exception as e:
                field_log("error", f"Resume upload failed: {e}", "", SITE)

        # ── 2. Phone number (country code + number) ──────────────────────────
        _fill_phone(page, phone, phone_local)

        # ── 3. Handle ALL form fields on this step ────────────────────────────
        _fill_all_form_fields(page, job_title, company, job_desc, location)

        # ── 3.5 Learn from filled fields (including user manual inputs) ───────
        try:
            from bot.utils.learning import learn_from_filled_form
            learn_from_filled_form(page, SITE)
        except Exception:
            pass

        # ── 4. Unfollow company (avoid spam emails) ───────────────────────────
        try:
            follow_label = page.query_selector('label[for*="follow"]')
            if follow_label:
                checkbox = page.query_selector('input[id*="follow"]')
                if checkbox and checkbox.is_checked():
                    follow_label.click()
                    field_log("check", "Unfollow company", "unchecked", SITE)
                    _delay(0.2, 0.4)
        except Exception:
            pass

        # ── 5. Navigation buttons ─────────────────────────────────────────────
        # Submit
        try:
            submit = page.get_by_role("button", name="Submit application")
            if submit.is_visible():
                field_log("submit", "Submit application", "", SITE)
                submit.click()
                _delay(1.5, 2.5)
                try:
                    page.get_by_role("button", name="Dismiss").click(timeout=3000)
                except Exception:
                    pass
                logger.success(f"✅ LinkedIn Easy Apply submitted: {company} — {job_title}", SITE)
                return True
        except Exception:
            pass

        # Review
        try:
            review = page.get_by_role("button", name="Review your application")
            if review.is_visible():
                field_log("nav", "Review application", "", SITE)
                review.click()
                _delay(1, 2)
                continue
        except Exception:
            pass

        # Next
        try:
            nxt = page.get_by_role("button", name="Continue to next step")
            if nxt.is_visible():
                field_log("nav", "Next step", "", SITE)
                nxt.click()
                _delay(1, 2)
                continue
        except Exception:
            pass

        # Nothing to click — modal may have closed or errored
        if not page.query_selector(".jobs-easy-apply-modal, .artdeco-modal"):
            break

    # Discard if we exited without submitting
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
        country_dropdown = page.query_selector(
            'select[id*="phoneNumber-country"], '
            '.phone-number__country-code select, '
            'select[aria-label*="Phone country code"]'
        )
        if country_dropdown:
            try:
                country_dropdown.select_option(value="in")
                field_log("select", "Phone country code", "India (+91)", SITE)
            except Exception:
                country_dropdown.select_option(index=1)

        for sel in [
            'input[id*="phoneNumber-nationalNumber"]',
            'input[name*="phoneNumber"]',
            'input[id*="phone"]',
            'input[aria-label*="Phone number" i]',
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    current = el.input_value().strip()
                    if not current:
                        human_fill(el, phone_local, "Phone number", SITE)
                    break
            except Exception:
                continue

        # Playwright locator fallback
        try:
            ph = page.get_by_label("Phone number")
            if ph.is_visible() and not ph.input_value().strip():
                human_fill(ph, phone_local, "Phone number", SITE)
        except Exception:
            pass

    except Exception:
        pass

# ─── ALL FORM FIELDS HANDLER (FULL COVERAGE) ─────────────────────────────────
def _fill_all_form_fields(page: Page, job_title: str, company: str, job_desc: str, location: str = "Worldwide"):
    """
    Detect and fill ALL form fields on the current modal step.
    Uses profile.yaml first, then AI for unknown questions.
    Logs every action with field_log() for console visibility.
    """
    standard = PROFILE.get("standard_answers", {})
    
    # Target elements inside the active modal if present, otherwise page
    modal = page.query_selector(".jobs-easy-apply-modal, .artdeco-modal, [data-test-modal]")
    container = modal if modal else page

    # ── Text / Number / Textarea inputs ─────────────────────────────────────
    inputs = container.query_selector_all(
        'input[type="text"], input[type="number"], input[type="email"], input:not([type]), textarea'
    )
    for el in inputs:
        try:
            if not el.is_visible():
                continue
            
            # Skip hidden checkbox/radio inputs if they are returned
            el_type = el.get_attribute("type") or ""
            if el_type.lower() in ["checkbox", "radio", "hidden", "file"]:
                continue
                
            current_val = ""
            try:
                current_val = el.input_value().strip()
            except Exception:
                pass
            if current_val:
                field_log("skip", _get_field_label(page, el) or "input", f"already has: {current_val}", SITE)
                continue
                
            label = _get_field_label(page, el)
            if not label:
                # Fallback: parent text node
                label = el.evaluate("el => el.parentElement ? el.parentElement.innerText.split('\\n')[0].trim() : ''")
                if not label:
                    label = "Question field"

            is_num = el.get_attribute("type") == "number" or "number" in label.lower() or "digit" in label.lower() or el.get_attribute("inputmode") == "numeric"
            answer = _answer_for(label, job_title, company, job_desc, standard, location=location, is_number_field=is_num)
            if not answer:
                answer = _ai_answer(label, [], job_title, company, job_desc, location=location)
                
            if answer:
                # If it is a combobox, type and select the suggestion
                is_combobox = el.get_attribute("role") == "combobox" or el.get_attribute("aria-autocomplete")
                if is_combobox:
                    human_fill(el, str(answer), label, SITE)
                    _delay(0.6, 1.2)
                    page.keyboard.press("ArrowDown")
                    _delay(0.2, 0.4)
                    page.keyboard.press("Enter")
                    _delay(0.3, 0.5)
                else:
                    human_fill(el, str(answer), label, SITE)
        except Exception:
            continue

    # ── Select dropdowns ─────────────────────────────────────────────────────
    selects = container.query_selector_all('select')
    for sel in selects:
        try:
            if not sel.is_visible():
                continue
            current = sel.evaluate("e => e.value")
            if current and current not in ["", "Select an option", "-1"]:
                field_log("skip", _get_field_label(page, sel) or "select", f"already: {current}", SITE)
                continue
            label = _get_field_label(page, sel)
            if not label:
                label = "dropdown selection"
            options = sel.evaluate("e => Array.from(e.options).map(o => o.text)")
            answer  = _answer_for_dropdown(label, options, job_title, company, job_desc, standard, location=location)
            if answer:
                try:
                    sel.select_option(label=answer)
                    field_log("select", label, answer, SITE)
                except Exception:
                    sel.select_option(index=1)
                    field_log("select", label, "index=1 fallback", SITE)
            _delay(0.2, 0.4)
        except Exception:
            continue

    # ── Radio buttons (grouped by parent container or name) ──────────────────
    radios = container.query_selector_all('input[type="radio"]')
    groups = {}
    for r in radios:
        try:
            if not r.is_visible():
                continue
            # Group by parent container or name attribute
            group_key = r.get_attribute("name")
            if not group_key:
                group_key = r.evaluate("""el => {
                    let p = el.closest('fieldset, .jobs-easy-apply-form-section__grouping, .fb-form-element, [class*="group"], [class*="element"]');
                    return p ? (p.id || p.innerText.substring(0, 30)) : 'default_group';
                }""")
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(r)
        except Exception:
            continue

    for name, group_radios in groups.items():
        try:
            # Check if group is already answered
            already_checked = False
            for r in group_radios:
                if r.is_checked():
                    already_checked = True
                    break
            if already_checked:
                continue

            # Find question text using robust label extractor on the first element's container
            first_r = group_radios[0]
            q_text = _get_field_label(page, first_r)
            if not q_text or q_text == "Select option":
                q_text = first_r.evaluate("""el => {
                    let p = el.closest('fieldset, .fb-form-element, div[class*="group"], div[class*="element"]');
                    if (p) {
                        let legend = p.querySelector('legend, label, p, span, [class*="label"], [class*="question"]');
                        return legend ? legend.innerText.trim() : p.innerText.split('\\n')[0].trim();
                    }
                    return '';
                }""")
            if not q_text:
                q_text = "Select option"

            # Find options (labels)
            labels_map = []
            for r in group_radios:
                r_id = r.get_attribute("id")
                label_el = page.query_selector(f'label[for="{r_id}"]') if r_id else None
                if not label_el:
                    label_el = r.evaluate_handle("el => el.parentElement")
                
                label_text = label_el.as_element().inner_text().strip() if label_el else ""
                if label_text:
                    labels_map.append((r, label_el.as_element(), label_text))

            options = [lbl_txt for _, _, lbl_txt in labels_map]
            answer = _answer_for(q_text, job_title, company, job_desc, standard, location=location)
            if not answer:
                answer = _ai_answer(q_text, options, job_title, company, job_desc, location=location)

            clicked = False
            for r_el, lbl_el, lbl_txt in labels_map:
                if answer and (answer.lower() in lbl_txt.lower() or lbl_txt.lower() in answer.lower()):
                    safe_check_input(page, r_el, lbl_el)
                    field_log("click", q_text, lbl_txt, SITE)
                    clicked = True
                    break
            
            if not clicked and labels_map:
                for r_el, lbl_el, lbl_txt in labels_map:
                    if "yes" in lbl_txt.lower():
                        safe_check_input(page, r_el, lbl_el)
                        field_log("click", q_text, lbl_txt + " (default)", SITE)
                        clicked = True
                        break
                if not clicked:
                    safe_check_input(page, labels_map[0][0], labels_map[0][1])
                    field_log("click", q_text, labels_map[0][2] + " (first fallback)", SITE)
            _delay(0.2, 0.4)
        except Exception as ex:
            logger.warn(f"Radio button grouping failed: {ex}", SITE)
            continue

    # ── Checkboxes ───────────────────────────────────────────────────────────
    checkboxes = container.query_selector_all('input[type="checkbox"]')
    for cb in checkboxes:
        try:
            if not cb.is_visible():
                continue
            cb_id = cb.get_attribute("id") or ""
            if "follow" in cb_id.lower():
                continue
                
            label_el = page.query_selector(f'label[for="{cb_id}"]') if cb_id else None
            label_text = label_el.inner_text().strip() if label_el else ""
            if not label_text:
                label_text = _get_field_label(page, cb) or "Agreement checkbox"
                
            # Agreement checks
            if any(x in label_text.lower() for x in ["agree", "consent", "terms", "privacy", "confirm", "acknowledge"]):
                if not cb.is_checked():
                    safe_check_input(page, cb, label_el)
                    field_log("check", label_text, "checked (agreement)", SITE)
            else:
                # Ask AI if we should check it
                answer = _answer_for(label_text, job_title, company, job_desc, standard, location=location)
                if not answer:
                    answer = _ai_answer(label_text, ["Yes", "No"], job_title, company, job_desc, location=location)
                
                should_check = False
                if answer.lower() in ["check", "true", "yes", "checked", "y"]:
                    should_check = True
                elif any(x in label_text.lower() for x in ["c#", ".net", "azure", "sql", "angular"]):
                    should_check = True
                    
                if should_check:
                    if not cb.is_checked():
                        safe_check_input(page, cb, label_el)
                        field_log("check", label_text, "checked (AI)", SITE)
                else:
                    if cb.is_checked():
                        safe_check_input(page, cb, label_el) # Toggles it off
                        field_log("check", label_text, "unchecked (AI)", SITE)
                    else:
                        field_log("skip", label_text, "skipped (AI)", SITE)
            _delay(0.1, 0.3)
        except Exception:
            continue

# ─── LABEL EXTRACTOR ─────────────────────────────────────────────────────────
def _get_field_label(page: Page, el) -> str:
    """Get the label text associated with a form element using robust JS DOM traversal."""
    try:
        q_text = el.evaluate("""el => {
            // 1. Check aria-label
            let aria = el.getAttribute('aria-label');
            if (aria && aria.trim()) return aria.trim();
            
            // 2. Check associated label
            let id = el.getAttribute('id');
            if (id) {
                let label = document.querySelector('label[for="' + id + '"]');
                if (label && label.innerText.trim()) return label.innerText.trim();
            }
            
            // 3. Check parent label or surrounding text
            let parent = el.closest('.jobs-easy-apply-form-element, .fb-form-element, .jobs-easy-apply-form-section__grouping, fieldset, div[class*="group"], div[class*="element"]');
            if (parent) {
                let legend = parent.querySelector('legend, label, .fb-form-element-label, [class*="label"], [class*="title"], [class*="question"]');
                if (legend && legend.innerText.trim()) return legend.innerText.trim();
                
                // Try parent's first text line
                let firstLine = parent.innerText.trim().split('\\n')[0];
                if (firstLine && firstLine.trim()) return firstLine.trim();
            }
            
            // 4. Try previous sibling
            let sib = el.previousElementSibling;
            while (sib) {
                if (sib.tagName.match(/H[1-6]|LABEL|P|SPAN/i) && sib.innerText.trim()) {
                    return sib.innerText.trim();
                }
                sib = sib.previousElementSibling;
            }
            
            // 5. Placeholder
            let ph = el.getAttribute('placeholder');
            if (ph && ph.trim()) return ph.trim();
            
            // 6. Name attribute
            let name = el.getAttribute('name');
            if (name && name.trim()) return name.trim();
            
            return '';
        }""")
        return q_text.strip()
    except Exception:
        return ""

def _estimate_expected_salary(question_label: str, job_title: str, company: str,
                              job_desc: str, location: str, is_number_field: bool = False) -> str:
    """
    Uses AI or rules to estimate the expected salary in the correct currency and format
    based on the job description, location, company, and candidate's 4 years of experience.
    """
    try:
        loc_lower = location.lower()
        # Fallback values
        currency = "USD"
        currency_symbol = "$"
        
        # Comprehensive country mapping for fallback
        if any(x in loc_lower for x in ["united kingdom", "uk", "london", "england", "scotland", "wales", "great britain"]):
            currency = "GBP"
            currency_symbol = "£"
        elif any(x in loc_lower for x in ["australia", "sydney", "melbourne", "brisbane", "perth"]):
            currency = "AUD"
            currency_symbol = "A$"
        elif any(x in loc_lower for x in ["singapore"]):
            currency = "SGD"
            currency_symbol = "S$"
        elif any(x in loc_lower for x in ["malaysia", "kuala lumpur", "selangor", "johor", "shah alam"]):
            currency = "MYR"
            currency_symbol = "RM"
        elif any(x in loc_lower for x in ["canada", "toronto", "vancouver", "montreal", "ottawa"]):
            currency = "CAD"
            currency_symbol = "C$"
        elif any(x in loc_lower for x in ["united states", "us", "usa", "america", "new york", "california", "texas"]):
            currency = "USD"
            currency_symbol = "$"
        elif any(x in loc_lower for x in ["europe", "germany", "netherlands", "romania", "portugal", "ireland", "spain", "france", "italy", "poland", "sweden", "belgium", "austria"]):
            currency = "EUR"
            currency_symbol = "€"
        elif any(x in loc_lower for x in ["switzerland", "zurich", "geneva"]):
            currency = "CHF"
            currency_symbol = "CHF"
        elif any(x in loc_lower for x in ["japan", "tokyo"]):
            currency = "JPY"
            currency_symbol = "¥"
        elif any(x in loc_lower for x in ["india", "bangalore", "bengaluru", "chennai", "hyderabad", "pune", "mumbai", "delhi"]):
            currency = "INR"
            currency_symbol = "₹"
            
        system = (
            "You are an expert compensation analyst and recruiter. Your job is to estimate the expected annual salary "
            "for a candidate applying to the specified job. The candidate is a Software Engineer with exactly 4 years of "
            "experience in C#, .NET, Azure, and Angular.\n\n"
            "Rules:\n"
            "1. Read the Job Description carefully. If the JD explicitly mentions a salary range, extract it and suggest a value/range near the mid-to-high end of that range.\n"
            "2. If the JD does not mention a salary, estimate the fair market value for a 4-year experience .NET developer at this company and location.\n"
            "3. Identify the expected currency from the Job Location, Job Description, or the Question Label. Correct the currency accordingly:\n"
            "   - USA/Remote/Worldwide: Format in USD ($), e.g. '110000' (numeric) or '$100,000 - $120,000 per year' (text).\n"
            "   - UK: Format in GBP (£), e.g. '70000' (numeric) or '£65,000 - £75,000 per year' (text).\n"
            "   - Europe (Germany, Netherlands, etc.): Format in EUR (€), e.g. '70000' (numeric) or '€65,000 - €75,000 per year' (text).\n"
            "   - Canada: Format in CAD (C$), e.g. '100000' (numeric) or 'C$90,000 - C$110,000 per year' (text).\n"
            "   - Australia: Format in AUD (A$), e.g. '120000' (numeric) or 'A$110,000 - A$130,000 per year' (text).\n"
            "   - Singapore: Format in SGD (S$), e.g. '90000' (numeric) or 'S$80,000 - S$95,000 per year' (text).\n"
            "   - Malaysia: Format in MYR (RM), e.g. '100000' (numeric) or 'RM96,000 - RM120,000 per year' (text).\n"
            "   - India: Format in INR (₹), e.g. '2200000' (numeric) or '20-25 LPA' (text).\n"
            "4. If the question label explicitly specifies a currency (e.g. 'in USD', 'in CAD', 'in EUR'), you MUST return the estimate in that requested currency, converting if necessary.\n"
            "5. If is_number_field is true, return ONLY a single integer representing the annual salary amount (e.g. '110000') without symbols, commas, spaces, or words. Do NOT output the years of experience or any other number.\n"
            "6. If is_number_field is false, return ONLY the formatted salary range/expression (e.g. '$110,000 - $120,000 per year' or '20-25 LPA') without explanations or extra words.\n"
            "CRITICAL: Do NOT include any introduction, conversational fluff, markdown fences, notes, or explanations. Just output the final value itself."
        )
        
        user = (
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Location: {location} (Inferred Default Currency: {currency} {currency_symbol})\n"
            f"Field Label: {question_label}\n"
            f"Is Numeric Field Only: {is_number_field}\n\n"
            f"Job Description Snippet:\n{job_desc[:2000]}\n"
        )
        
        from bot.ai_router import ai_complete
        result = ai_complete(system, user, task="form_fill", max_tokens=100).strip()
        
        if is_number_field:
            # Extract numbers
            nums = re.findall(r'\d+', result.replace(',', ''))
            if nums:
                # Filter out numbers that look like years (e.g. 4) or standard text numbers
                # Let's sort or find a number that matches a reasonable salary scale
                # e.g., > 10000
                valid_salaries = [n for n in nums if int(n) >= 1000]
                if valid_salaries:
                    return valid_salaries[0]
                return nums[0]
            # Fallback regex search
            digits = re.sub(r'[^\d\.]', '', result)
            if digits:
                return digits
        return result
    except Exception as e:
        logger.warn(f"Failed to estimate expected salary: {e}", SITE)
        if is_number_field:
            return "2200000" if currency == "INR" else "90000"
        return "20-25 LPA" if currency == "INR" else f"{currency_symbol}80,000 - {currency_symbol}100,000 per year"

# ─── ANSWER ENGINE ────────────────────────────────────────────────────────────
def _answer_for(question: str, job_title: str, company: str,
                job_desc: str, standard: dict, location: str = "Worldwide", is_number_field: bool = False) -> str:
    """Find best answer: profile standard_answers → profile fields → AI."""
    if not question:
        return ""
    q_lower = question.lower().strip()

    # 1. Direct match in standard_answers
    for key, val in standard.items():
        if key.lower() in q_lower or q_lower in key.lower():
            if is_number_field and ("." in str(val) or str(val).isdigit()):
                import re
                nums = re.findall(r'\d+\.?\d*', str(val))
                if nums:
                    return nums[0]
            return str(val)

    # 2. Common field matching from profile
    pi = PROFILE.get("personal_info", {})
    exp = PROFILE.get("experience_summary", {})
    prefs = PROFILE.get("preferences", {})

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
    if any(x in q_lower for x in ["city", "location", "where are you based", "current location"]):
        return pi.get("city", "Chennai")
    if any(x in q_lower for x in ["country"]):
        return "India"
    if any(x in q_lower for x in ["state", "province"]):
        return "Tamil Nadu"

    # Experience
    if any(x in q_lower for x in ["total years", "total experience", "years of experience"]):
        return str(exp.get("total_years", 4))
    if any(x in q_lower for x in ["notice period", "notice"]):
        try:
            from datetime import datetime
            lwd = datetime(2026, 8, 14)
            now = datetime.now()
            days = (lwd - now).days
            days_left = max(0, days)
            if is_number_field or "days" in q_lower or "day" in q_lower or any(c.isdigit() for c in q_lower):
                return str(days_left)
            return f"{days_left} days"
        except Exception:
            return "57 days"
    if any(x in q_lower for x in ["salary", "ctc", "compensation", "expected", "package"]):
        if "current" in q_lower:
            if is_number_field or any(n in q_lower for n in ["lpa", "lakh", "number", "digit", "in lakhs"]):
                return "11.5"
            return "11.5 Lakh per annum"
        # Expected
        return _estimate_expected_salary(question, job_title, company, job_desc, location, is_number_field)
    if any(x in q_lower for x in ["relocat"]):
        return "Yes"
    if any(x in q_lower for x in ["sponsor", "visa", "work authoriz"]):
        return "Yes" if "india" in q_lower else "No, I will require visa sponsorship"
    if any(x in q_lower for x in ["authorized", "authorised", "eligible to work", "right to work"]):
        if "india" in q_lower or "in" in q_lower:
            return "Yes"
        return "No"

    # Tech-specific experience years
    if "years" in q_lower or "experience with" in q_lower or "experience in" in q_lower:
        skill_years = {
            ".net": "4", "c#": "4", "asp.net": "4", "sql": "4", "sql server": "4",
            "azure": "3", "angular": "3", "entity framework": "3",
            "react": "2", "docker": "2", "tdd": "2", "ci/cd": "3",
            "microservices": "3", "agile": "4", "scrum": "4",
        }
        for skill, years in skill_years.items():
            if skill in q_lower:
                return years
        return str(exp.get("total_years", 4))

    return ""  # Let AI handle it

def _answer_for_dropdown(question: str, options: list, job_title: str,
                          company: str, job_desc: str, standard: dict, location: str = "Worldwide") -> str:
    """Find the best dropdown option."""
    answer = _answer_for(question, job_title, company, job_desc, standard, location, is_number_field=False)
    if answer:
        for opt in options:
            if answer.lower() in opt.lower() or opt.lower() in answer.lower():
                return opt
    return _ai_answer_dropdown(question, options, job_title, company, job_desc, location)

def _get_candidate_context() -> str:
    """Generate a compact but complete text representation of the candidate profile for the AI."""
    try:
        pi = PROFILE.get("personal_info", {})
        exp = PROFILE.get("experience_summary", {})
        prefs = PROFILE.get("preferences", {})
        
        summary = [
            f"Candidate Name: {pi.get('full_name', 'Siva Shankar V')}",
            f"Email: {pi.get('email', 'sivashankar.avi6@gmail.com')}",
            f"Phone: {pi.get('phone_local', '6383149155')}",
            f"Current Location: {pi.get('city', 'Chennai')}, {pi.get('country', 'India')}",
            f"Relocation Preference: {prefs.get('relocation', 'Yes, open to relocate')}",
            f"Notice Period: {prefs.get('notice_period', '30 days')}",
            f"Current Salary: {prefs.get('current_salary', '10.5 LPA')}",
            f"Expected Salary: {prefs.get('expected_salary', '20-30 LPA')}",
            f"Total Experience: {exp.get('total_years', 4)} years",
            f"Current Role: Senior .NET Developer at LTIMindtree (client: Deloitte)",
            f"Core Skills: C#, .NET Core 7/8, ASP.NET Web API, Azure App Services, Azure SQL, SQL Server, Angular 15+, Entity Framework Core, Microservices, CQRS, Docker, RabbitMQ, JWT, OAuth2",
            f"Education: B.E. Electronics & Communication Engineering (GPA 8.6)"
        ]
        return "\n".join(summary)
    except Exception:
        return (
            "Candidate: Siva Shankar V, Senior .NET Developer, 4+ years experience. "
            "Skills: C#, ASP.NET Core, Azure, Angular, SQL. Expected CTC: 20-30 LPA. Notice: 30 days."
        )

def safe_check_input(page: Page, el, lbl_el) -> bool:
    """Safely check a checkbox or radio button, bypassing potential element obscurities."""
    try:
        el.check(force=True)
        return True
    except Exception:
        try:
            if lbl_el:
                lbl_el.click(force=True)
                return True
        except Exception:
            try:
                el.evaluate("el => el.click()")
                return True
            except Exception:
                pass
    return False

def _ai_answer(question: str, options: list, job_title: str,
               company: str, job_desc: str, location: str = "Worldwide") -> str:
    """Use AI to answer an unknown question."""
    try:
        candidate_context = _get_candidate_context()
        system = (
            "You are an AI job application assistant filling forms for the candidate described below. "
            "Give the most appropriate, professional, concise answer based strictly on the candidate's profile. "
            "Do not make up facts. Be concise and precise."
        )
        user = (
            f"Candidate Profile:\n{candidate_context}\n\n"
            f"Job: {job_title} at {company} (Location: {location})\n"
            f"Question: {question}\n"
            f"Options (if multiple choice): {options}\n\n"
            f"Rules:\n"
            f"1. If options are provided, you MUST pick the best option from the list and return it EXACTLY. Do not add any other words, explanations, or punctuation.\n"
            f"2. If the question is a Yes/No question, answer 'Yes' or 'No' strictly.\n"
            f"3. If no options are provided, answer with the value only (e.g., a number or brief text) without surrounding quotes or extra commentary."
        )
        return ai_complete(system, user, task="form_fill", max_tokens=100).strip()
    except Exception:
        return options[0] if options else "Yes"

def _ai_answer_dropdown(question: str, options: list, job_title: str,
                         company: str, job_desc: str, location: str = "Worldwide") -> str:
    """Use AI to pick the best dropdown option."""
    try:
        candidate_context = _get_candidate_context()
        system = (
            "You are an AI job application assistant. Pick the EXACT option text "
            "from the list that best fits the candidate's profile. Reply with ONLY the option text."
        )
        user = (
            f"Candidate Profile:\n{candidate_context}\n\n"
            f"Job: {job_title} at {company} (Location: {location})\n"
            f"Question: {question}\n"
            f"Options: {options}\n"
        )
        ai_answer = ai_complete(system, user, task="form_fill", max_tokens=50).strip()
        for opt in options:
            if ai_answer.lower() in opt.lower() or opt.lower() in ai_answer.lower():
                return opt
        return options[0] if options else ""
    except Exception:
        return options[0] if options else ""
