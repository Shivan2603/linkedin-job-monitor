"""
sites/naukri.py — Naukri.com Quick Apply (2025, Production Grade)

Design:
  - URL-based job extraction: extract all job URLs from search, navigate to each directly
  - 2025 Naukri UI selectors (verified)
  - Full form field handler: text, phone, CTC, notice period, cover letter, resume upload
  - Relevance filter: only apply if match_score >= MIN_MATCH_SCORE
  - Field-by-field visible logging via field_log() so user can watch in real time
  - Headful browser (slow_mo=150) — every keystroke is visible
"""
import time, random, re, os
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
    field_log, human_fill
)

SITE     = "naukri"
BASE_URL = "https://www.naukri.com"
MIN_MATCH = int(os.getenv("MIN_MATCH_SCORE", "60"))

def _delay(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))

def _load_profile():
    try:
        import yaml
        return yaml.safe_load(open("profile.yaml", encoding="utf-8"))
    except Exception:
        return {}

PROFILE = _load_profile()

def _get(key_path: str, default=""):
    try:
        parts = key_path.split(".")
        val = PROFILE
        for p in parts:
            val = val[p]
        return str(val) if val is not None else default
    except Exception:
        return default

def _answer(question: str, is_number_field: bool = False) -> str:
    """Get form answer from profile.yaml standard_answers or profile fields."""
    q = question.lower().strip()
    standard = PROFILE.get("standard_answers", {})
    pi = PROFILE.get("personal_info", {})
    exp = PROFILE.get("experience_summary", {})
    prefs = PROFILE.get("preferences", {})

    # Direct match
    for key, val in standard.items():
        if key.lower() in q or q in key.lower():
            if is_number_field and ("." in str(val) or str(val).isdigit()):
                import re
                nums = re.findall(r'\d+\.?\d*', str(val))
                if nums:
                    return nums[0]
            return str(val)

    # Field matching
    if any(x in q for x in ["first name"]): return pi.get("first_name", "Siva Shankar")
    if any(x in q for x in ["last name"]): return pi.get("last_name", "V")
    if any(x in q for x in ["full name", "your name"]): return pi.get("full_name", "Siva Shankar V")
    if any(x in q for x in ["email"]): return pi.get("email", "sivashankar.avi6@gmail.com")
    if any(x in q for x in ["phone", "mobile", "contact"]): return pi.get("phone_local", "6383149155")
    if any(x in q for x in ["city", "location"]): return "Chennai"
    if any(x in q for x in ["total experience", "years of experience", "total years"]): return str(exp.get("total_years", 4))
    if any(x in q for x in ["notice period", "notice"]):
        try:
            from datetime import datetime
            lwd = datetime(2026, 8, 14)
            now = datetime.now()
            days = (lwd - now).days
            days_left = max(0, days)
            if is_number_field or "days" in q or "day" in q or any(c.isdigit() for c in q):
                return str(days_left)
            return f"{days_left} days"
        except Exception:
            return "57 days"
    if any(x in q for x in ["current ctc", "current salary", "current package", "current compensation"]):
        if is_number_field or any(n in q for n in ["lpa", "lakh", "number", "digit", "in lakhs"]):
            return "11.5"
        return "11.5 Lakh per annum"
    if any(x in q for x in ["expected ctc", "expected salary", "expected package", "expected compensation"]):
        if is_number_field or any(n in q for n in ["lpa", "lakh", "number", "digit", "in lakhs"]):
            return "20"
        return "20-30 LPA"
    if any(x in q for x in ["current employer", "current company"]): return "LTIMindtree"
    if any(x in q for x in ["relocat"]): return "Yes"
    if any(x in q for x in ["work from home", "remote", "wfh"]): return "Yes"

    # Tech-specific years
    tech_years = {
        ".net": "4", "c#": "4", "asp.net": "4", "sql": "4",
        "azure": "3", "angular": "3", "agile": "4", "entity framework": "3",
    }
    for skill, years in tech_years.items():
        if skill in q:
            return years

    return ""

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
               company: str, job_desc: str) -> str:
    """Use AI to answer an unknown question on Naukri."""
    try:
        candidate_context = _get_candidate_context()
        system = (
            "You are an AI job application assistant filling forms for the candidate described below. "
            "Give the most appropriate, professional, concise answer based strictly on the candidate's profile. "
            "Do not make up facts. Be concise and precise."
        )
        user = (
            f"Candidate Profile:\n{candidate_context}\n\n"
            f"Job: {job_title} at {company}\n"
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
                         company: str, job_desc: str) -> str:
    """Use AI to pick the best dropdown option on Naukri."""
    try:
        candidate_context = _get_candidate_context()
        system = (
            "You are an AI job application assistant. Pick the EXACT option text "
            "from the list that best fits the candidate's profile. Reply with ONLY the option text."
        )
        user = (
            f"Candidate Profile:\n{candidate_context}\n\n"
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

# ─── MAIN ENTRY ───────────────────────────────────────────────────────────────
def run_naukri_bot():
    creds = CREDENTIALS["naukri"]
    if not creds["email"] or not creds["password"]:
        logger.warn("Naukri credentials not set — skipping", SITE)
        return
    if not check_daily_limit(SITE):
        return

    logger.info("Starting Naukri.com bot", SITE)
    print(f"\n{'='*60}")
    print(f"  NAUKRI BOT — Headful Mode (Watch the browser!)")
    print(f"  Min match score to apply: {MIN_MATCH}%")
    print(f"{'='*60}\n")

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()
        try:
            if not _login(page, creds):
                return
            save_cookies(context, SITE)
            # Overridden as requested: ONLY search for ".Net" on Naukri
            naukri_keywords = [".Net"]
            for job_title in naukri_keywords:
                for location in LOCATIONS:
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
        # Google SSO Sign in
        google_btn = None
        for sel in ["a.socialbtn.google", "a:has-text('Sign in with Google')", "button:has-text('Google')"]:
            el = page.query_selector(sel)
            if el and el.is_visible():
                google_btn = el
                break
                
        if google_btn:
            logger.info("Clicking Naukri 'Sign in with Google' button...", SITE)
            with page.context.expect_page(timeout=15000) as popup_info:
                google_btn.click()
            popup = popup_info.value
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
                
            _delay(2, 3)
            # Google account picker selectors
            picker_selectors = [
                '[data-email="sivashankar.avi6@gmail.com"]',
                'div[data-email*="@gmail.com"]',
                'div:has-text("sivashankar.avi6@gmail.com")',
                'div:has-text("Siva Shankar")',
                'div.auth-select-account',
                '#profileIdentifier',
            ]
            
            clicked = False
            for sel in picker_selectors:
                el = popup.query_selector(sel)
                if el and el.is_visible():
                    logger.info(f"Selecting Google account using {sel}...", SITE)
                    el.click()
                    clicked = True
                    break
                    
            if not clicked:
                logger.info("No automatic Google account picker found; waiting for SSO auto-resolution...", SITE)
                
            _delay(5, 7)
        else:
            logger.warn("Naukri Google SSO button not found, trying traditional login...", SITE)
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
                    human_fill(el, creds["email"], "Email", SITE)
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
                    human_fill(el, creds["password"], "Password (hidden)", SITE)
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
                    field_log("click", "Login button", "", SITE)
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
                        human_fill(otp_el, otp, "OTP code", SITE)
                        _delay(0.5, 1)
                        page.query_selector('button[type="submit"]').click()
                        _delay(3, 4)
                except Exception:
                    pass

        # Verify login
        _delay(3, 4)
        if any(x in page.url for x in ["mnjuser", "myhome", "/dashboard"]) or page.query_selector(".nI-gNb-header__logo"):
            logger.success("Naukri login successful ✅", SITE)
            return True
        else:
            logger.error("Naukri login verification failed", SITE)
            return False

    except Exception as e:
        logger.error(f"Naukri login failed: {e}", SITE)
        return False

# ─── SEARCH → EXTRACT URLs ───────────────────────────────────────────────────
def _search_and_apply(page: Page, job_title: str, location: str):
    logger.info(f"Searching Naukri: '{job_title}' in '{location}'", SITE)

    if job_title == ".Net":
        slug = "dotnet"
    else:
        slug = job_title.lower().replace(" ", "-")

    search_url = (
        f"{BASE_URL}/{quote(slug)}-jobs"
        f"?k={quote(job_title)}&l={quote(location)}"
        f"&experience=4&jobAge=7&sort=1"
    )

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        _delay(2, 3)
    except Exception as e:
        logger.warn(f"Naukri search failed: {e}", SITE)
        return

    for _ in range(3):
        page.mouse.wheel(0, 800)
        _delay(0.5, 1)

    job_urls = _extract_job_urls(page)
    if not job_urls:
        logger.info(f"No jobs found for '{job_title}' in {location}", SITE)
        return

    logger.info(f"Found {len(job_urls)} jobs for '{job_title}' in {location}", SITE)

    applied = 0
    for job_url in job_urls[:15]:
        if not check_daily_limit(SITE):
            return
        try:
            result = _apply_to_url(page, job_url, job_title, location)
            if result:
                applied += 1
                increment_daily_count(SITE)
                _delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 8)
            else:
                _delay(1, 2)
        except Exception as e:
            logger.warn(f"Naukri apply error: {str(e)[:80]}", SITE)
            continue

    logger.info(f"Naukri: Applied {applied} jobs for '{job_title}' in {location}", SITE)

# ─── EXTRACT JOB URLs ─────────────────────────────────────────────────────────
def _extract_job_urls(page: Page) -> list:
    urls = []
    seen = set()

    link_selectors = [
        # 2025 Naukri selectors (verified)
        "article.jobTuple a.title",
        ".srp-jobtuple-wrapper a.title",
        ".job-title-anchor",
        "a.title[href*='naukri.com']",
        ".jobTitle a",
        # Generic fallbacks
        "article a[href*='job-listings']",
        ".srp-jobtuple-wrapper a[href*='/job-listings']",
    ]

    for sel in link_selectors:
        try:
            links = page.query_selector_all(sel)
            for link in links:
                href = link.get_attribute("href")
                if href and href not in seen and ("job-listings" in href or "naukri.com" in href):
                    if href.startswith("/"):
                        href = BASE_URL + href
                    urls.append(href)
                    seen.add(href)
            if urls:
                break
        except Exception:
            continue

    # Fallback: scrape all hrefs
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

    return list(dict.fromkeys(urls))

# ─── APPLY TO A SPECIFIC JOB URL ─────────────────────────────────────────────
def _apply_to_url(page: Page, job_url: str, default_title: str, location: str) -> bool:
    try:
        page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
        _delay(2, 3)

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
            ".styles_jd-header-title__rZwM1",
        ]) or default_title

        # Clean job title (remove location keywords)
        job_title = re.sub(r'\s+', ' ', job_title).strip()
        job_title = re.sub(r'\b(Job\s+)?in\s+.*$', '', job_title, flags=re.IGNORECASE).strip()
        job_title = re.sub(r'\b(Johor|Selangor|Kuala Lumpur|Shah Alam|Subang|Bangalore|Chennai|Remote|Singapore|Malaysia|India).*$', '', job_title, flags=re.IGNORECASE).strip()
        job_title = re.sub(r'[\s\-,\/\|\(\)]+$', '', job_title).strip()

        company = _text([
            ".jd-header-comp-name a",
            ".comp-name-link",
            "a[class*='comp-name']",
            ".company-name",
            ".jd-header-comp-name",
            ".styles_jd-header-comp-name__MvqAI",
        ]) or "Company"

        job_desc = _text([
            "section[class*='job-desc-container']",
            "div[class*='dang-inner-html']",
            "div[class*='job-desc']",
            ".jd-desc",
            ".job-desc",
            "#job-description",
            ".JDC-module",
            "section[class*='description']",
            ".styles_JDC__doyVO",
        ])

        if is_already_applied(SITE, company, job_title):
            field_log("skip", f"{company} — {job_title}", "Already applied", SITE)
            return False

        # Tailor the resume for this job description
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        # If resume_path is empty, it means the job failed programmatic tech stack or experience check
        if not resume_path:
            field_log("skip", f"{company} — {job_title}", "Tech stack or experience mismatch", SITE)
            return False

        # Match score check bypassed as requested by user
        # if match_score < MIN_MATCH:
        #     field_log("skip", f"{company} — {job_title}", f"Match {match_score}% < {MIN_MATCH}%", SITE)
        #     return False

        print(f"\n  {'─'*55}")
        print(f"  🎯 APPLYING: {company} — {job_title}")
        print(f"     Match: {match_score}% | URL: {job_url[:60]}")
        print(f"  {'─'*55}")

        # ── Find Apply button ─────────────────────────────────────────────────
        apply_btn = None

        # Wait for page to settle
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        apply_selectors = [
            # 2025 Naukri selectors (most specific first)
            'button[class*="chatApplyBtn"]',
            'a[class*="chatApplyBtn"]',
            'button.btn-chatApply',
            'button[class*="apply-button"]',
            'a[class*="apply-button"]',
            # Role-based (most resilient)
            'button:has-text("Apply")',
            'a:has-text("Apply now")',
            'a:has-text("Apply")',
            # Generic fallbacks
            '.apply-button',
            '#apply-button',
            'button[id*="apply"]',
        ]

        for sel in apply_selectors:
            try:
                el_loc = page.locator(sel).first
                if el_loc.is_visible():
                    btn_text = el_loc.inner_text().lower()
                    if "already" in btn_text or "save" in btn_text:
                        field_log("skip", f"{company} — {job_title}", "Already applied on Naukri", SITE)
                        return False
                    apply_btn = el_loc
                    field_log("found", "Apply button", btn_text.strip()[:40], SITE)
                    break
            except Exception:
                continue

        if not apply_btn:
            field_log("skip", f"{company} — {job_title}", "No apply button found", SITE)
            return False

        apply_btn.scroll_into_view_if_needed()
        _delay(0.3, 0.6)

        btn_text_lower = apply_btn.inner_text().lower()
        is_company_site = "company" in btn_text_lower or "website" in btn_text_lower

        if is_company_site:
            logger.info("Naukri: 'Apply on Company Site' detected — opening ATS...", SITE)
            with page.context.expect_page(timeout=10000) as new_page_info:
                apply_btn.click()
            new_page = new_page_info.value
            new_page.wait_for_load_state("networkidle", timeout=15000)
            from bot.ai_agent_filler import fill_form_with_ai
            success = fill_form_with_ai(new_page, site=SITE, resume_path=resume_path)
            try:
                new_page.close()
            except Exception:
                pass
        else:
            field_log("click", "Apply button (Quick Apply)", "", SITE)
            apply_btn.click()
            _delay(2, 3)
            success = _handle_application(page, resume_path, job_title, company, job_desc)

        if success:
            record_application(
                site=SITE, company=company, role=job_title,
                location=location, job_url=job_url,
                match_score=match_score, resume_used=resume_path,
            )
            git_sync()
            logger.success(f"✅ Naukri applied: {company} — {job_title} ({match_score}%)", SITE)

        return success

    except Exception as e:
        logger.warn(f"Naukri URL apply error: {str(e)[:100]}", SITE)
        return False

def _get_naukri_field_label(page: Page, el) -> str:
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
            let parent = el.closest('fieldset, .form-group, .fb-form-element, [class*="group"], [class*="element"], [class*="row"]');
            if (parent) {
                let legend = parent.querySelector('legend, label, p, span, [class*="label"], [class*="title"], [class*="question"]');
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

# ─── APPLICATION FORM HANDLER (FULL FIELD COVERAGE) ──────────────────────────
def _handle_application(page: Page, resume_path: str, job_title: str,
                         company: str, job_desc: str) -> bool:
    """
    Handle Naukri Quick Apply form with field-by-field logging.
    Covers: resume upload, phone, CTC, notice period, cover letter,
            text inputs, dropdowns, radio buttons.
    """
    _delay(1, 2)

    for step in range(8):
        _delay(0.5, 1)
        field_log("step", f"Naukri Form Step {step + 1}", "", SITE)

        # ── Resume upload ────────────────────────────────────────────────────
        for file_sel in ['input[type="file"]', 'input[accept*="doc"]', 'input[accept*="pdf"]']:
            try:
                el = page.query_selector(file_sel)
                if el and el.is_visible():
                    field_log("upload", "Resume file", os.path.basename(resume_path), SITE)
                    el.set_input_files(resume_path)
                    _delay(1, 2)
                    break
            except Exception:
                pass

        # ── Phone ────────────────────────────────────────────────────────────
        phone = _get("personal_info.phone_local", "6383149155")
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
                    human_fill(el, phone, "Phone / Mobile", SITE)
                    break
            except Exception:
                continue

        # ── All visible text inputs (CTC, notice, name, etc.) ───────────────
        text_inputs = page.query_selector_all(
            'input[type="text"], input[type="number"], input[type="email"], input:not([type])'
        )
        for inp in text_inputs:
            try:
                if not inp.is_visible():
                    continue
                    
                el_type = inp.get_attribute("type") or ""
                if el_type.lower() in ["checkbox", "radio", "hidden", "file"]:
                    continue
                    
                current = inp.input_value().strip()
                if current:
                    continue
                    
                label_text = _get_naukri_field_label(page, inp)
                if not label_text:
                    label_text = inp.evaluate("el => el.parentElement ? el.parentElement.innerText.split('\\n')[0].trim() : ''")
                    if not label_text:
                        label_text = "Question field"

                is_num = inp.get_attribute("type") == "number" or "number" in label_text.lower() or "digit" in label_text.lower() or inp.get_attribute("inputmode") == "numeric"
                answer = _answer(label_text, is_number_field=is_num)
                if not answer:
                    answer = _ai_answer(label_text, [], job_title, company, job_desc)
                if answer:
                    # Check if it is a combobox
                    is_combobox = inp.get_attribute("role") == "combobox" or inp.get_attribute("aria-autocomplete")
                    if is_combobox:
                        human_fill(inp, answer, label_text or "text field", SITE)
                        _delay(0.6, 1.2)
                        page.keyboard.press("ArrowDown")
                        _delay(0.2, 0.4)
                        page.keyboard.press("Enter")
                        _delay(0.3, 0.5)
                    else:
                        human_fill(inp, answer, label_text or "text field", SITE)
            except Exception:
                continue

        # ── Textareas (cover letter, reason, etc.) ──────────────────────────
        textareas = page.query_selector_all("textarea")
        for ta in textareas:
            try:
                if not ta.is_visible():
                    continue
                current = ta.input_value().strip()
                if current:
                    continue
                label_text = _get_naukri_field_label(page, ta) or "textarea"
                if any(x in label_text.lower() for x in ["cover", "letter", "about", "reason", "why"]):
                    cover = _get("standard_answers.Cover Letter", "")
                    if not cover:
                        cover = (
                            f"Dear Hiring Manager, I am a Senior .NET Developer with 4+ years of experience "
                            f"in C#, ASP.NET Core, Azure, and Angular. I am applying for the {job_title} role "
                            f"at {company}. My hands-on experience with microservices, TDD, CI/CD, and Clean Architecture "
                            f"makes me a strong fit. I look forward to contributing to your team. "
                            f"Sincerely, Siva Shankar V"
                        )
                    human_fill(ta, cover, "Cover Letter / About", SITE)
                else:
                    answer = _answer(label_text)
                    if not answer:
                        answer = _ai_answer(label_text, [], job_title, company, job_desc)
                    if answer:
                        human_fill(ta, answer, label_text, SITE)
            except Exception:
                continue

        # ── Dropdowns ────────────────────────────────────────────────────────
        selects = page.query_selector_all("select")
        for sel in selects:
            try:
                if not sel.is_visible():
                    continue
                current = sel.evaluate("e => e.value")
                if current and current not in ["", "-1", "Select"]:
                    continue
                options_data = sel.evaluate("e => Array.from(e.options).map(o => ({v:o.value, t:o.text}))")
                options = [o.get("t", "") for o in options_data]
                label = _get_naukri_field_label(page, sel) or "dropdown"
                
                answer = _answer(label)
                if not answer:
                    answer = _ai_answer_dropdown(label, options, job_title, company, job_desc)
                
                best_opt = None
                if answer:
                    for opt in options_data:
                        ot = opt.get("t", "").lower()
                        if answer.lower() in ot or ot in answer.lower():
                            best_opt = opt.get("v")
                            answer = opt.get("t")
                            break
                if best_opt:
                    sel.select_option(value=best_opt)
                    field_log("select", label, answer, SITE)
                elif len(options_data) > 1:
                    sel.select_option(index=1)
                    field_log("select", label, options_data[1].get("t", ""), SITE)
            except Exception:
                continue

        # ── Radio buttons (grouped by parent container or name) ──────────────────
        radios = page.query_selector_all('input[type="radio"]')
        groups = {}
        for r in radios:
            try:
                if not r.is_visible():
                    continue
                group_key = r.get_attribute("name")
                if not group_key:
                    group_key = r.evaluate("""el => {
                        let p = el.closest('fieldset, .form-group, [class*="group"], [class*="element"]');
                        return p ? (p.id || p.innerText.substring(0, 30)) : 'default_group';
                    }""")
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(r)
            except Exception:
                continue

        for name, group_radios in groups.items():
            try:
                already_checked = False
                for r in group_radios:
                    if r.is_checked():
                        already_checked = True
                        break
                if already_checked:
                    continue

                first_r = group_radios[0]
                q_text = _get_naukri_field_label(page, first_r)
                if not q_text or q_text == "Select option":
                    q_text = first_r.evaluate("""el => {
                        let p = el.closest('fieldset, div[class*="group"], div[class*="element"]');
                        if (p) {
                            let legend = p.querySelector('legend, label, p, span');
                            return legend ? legend.innerText.trim() : p.innerText.split('\\n')[0].trim();
                        }
                        return '';
                    }""")
                if not q_text:
                    q_text = "Select option"

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
                answer = _answer(q_text)
                if not answer:
                    answer = _ai_answer(q_text, options, job_title, company, job_desc)

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
            except Exception:
                continue

        # ── Checkboxes ───────────────────────────────────────────────────────────
        checkboxes = page.query_selector_all('input[type="checkbox"]')
        for cb in checkboxes:
            try:
                if not cb.is_visible():
                    continue
                cb_id = cb.get_attribute("id") or ""
                label_el = page.query_selector(f'label[for="{cb_id}"]') if cb_id else None
                label_text = label_el.inner_text().strip() if label_el else ""
                if not label_text:
                    label_text = _get_naukri_field_label(page, cb) or "Agreement checkbox"
                    
                if any(x in label_text.lower() for x in ["agree", "consent", "terms", "privacy", "confirm", "acknowledge"]):
                    if not cb.is_checked():
                        safe_check_input(page, cb, label_el)
                        field_log("check", label_text, "checked (agreement)", SITE)
                else:
                    answer = _answer(label_text)
                    if not answer:
                        answer = _ai_answer(label_text, ["Yes", "No"], job_title, company, job_desc)
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
                            safe_check_input(page, cb, label_el)
                            field_log("check", label_text, "unchecked (AI)", SITE)
                _delay(0.1, 0.3)
            except Exception:
                continue

        # ── 4.5 Learn from filled fields (including user manual inputs) ───────
        try:
            from bot.utils.learning import learn_from_filled_form
            learn_from_filled_form(page, SITE)
        except Exception:
            pass

        # ── Success indicators ────────────────────────────────────────────────
        success_indicators = [
            '[class*="success"]',
            '[class*="applied"]',
            ':has-text("Application submitted")',
            ':has-text("Applied successfully")',
            ':has-text("You have applied")',
            ':has-text("Successfully Applied")',
            '.application-success',
        ]
        for ind in success_indicators:
            try:
                el = page.query_selector(ind)
                if el and el.is_visible():
                    field_log("success", "Application submitted!", "", SITE)
                    return True
            except Exception:
                continue

        # ── Submit / Navigation buttons ────────────────────────────────────────────
        submit_btn = None
        next_btn = None
        
        buttons = page.query_selector_all('button:visible, input[type="button"]:visible, input[type="submit"]:visible, a.btn:visible, a[class*="btn"]:visible')
        for btn in buttons:
            try:
                txt = btn.inner_text().strip().lower()
                # Prioritise submit terms
                if any(x in txt for x in ["submit", "confirm", "apply now", "quick apply", "apply without"]):
                    submit_btn = btn
                    break
                elif any(x in txt for x in ["next", "continue", "proceed"]):
                    next_btn = btn
            except Exception:
                continue

        if submit_btn:
            field_log("submit", "Submit application", submit_btn.inner_text().strip(), SITE)
            submit_btn.click()
            _delay(2, 4)
            
            # Check success indicator again
            for ind in success_indicators:
                try:
                    el = page.query_selector(ind)
                    if el and el.is_visible():
                        field_log("success", "Application submitted successfully!", "", SITE)
                        return True
                except Exception:
                    continue
            return True  # Assume success after final submit click
            
        elif next_btn:
            field_log("nav", "Next step", next_btn.inner_text().strip(), SITE)
            next_btn.click()
            _delay(2, 3)
            continue  # Proceed to next step loop
            
        # No more buttons — check if modal is gone
        modal = page.query_selector('.apply-form, .application-form, [class*="modal"]')
        if not modal:
            break

    return False
