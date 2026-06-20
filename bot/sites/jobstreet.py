"""
sites/jobstreet.py — JobStreet Singapore (SEEK) automation with Google SSO login
"""
import time, random, os, urllib.parse
from playwright.sync_api import sync_playwright
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger
from bot.utils.safety import safe_browser_context, check_daily_limit, increment_daily_count

SITE = "jobstreet"
MIN_MATCH = int(os.getenv("MIN_MATCH_SCORE", "60"))

def get_jobstreet_base_url(location: str) -> str:
    loc = location.lower()
    if "malaysia" in loc: return "https://www.jobstreet.com.my"
    elif "singapore" in loc: return "https://www.jobstreet.com.sg"
    elif "philippines" in loc: return "https://www.jobstreet.com.ph"
    elif "indonesia" in loc: return "https://www.jobstreet.co.id"
    elif "australia" in loc: return "https://www.seek.com.au"
    elif "new zealand" in loc: return "https://www.seek.co.nz"
    elif "remote" in loc: return "https://www.jobstreet.com.sg"  # Default remote search to Singapore
    return None  # Skip other countries for SEEK/JobStreet

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_jobstreet_bot():
    creds = CREDENTIALS["jobstreet"]
    logger.info("🚀 Starting JobStreet/SEEK bot", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()

        try:
            logged_in_domains = set()
            failed_domains = set()
            for job_title in JOB_TITLES:
                for location in LOCATIONS:
                    if not check_daily_limit(SITE):
                        logger.info("JobStreet daily limit reached", SITE)
                        return
                    base_url = get_jobstreet_base_url(location)
                    if not base_url:
                        logger.info(f"JobStreet/SEEK does not operate in '{location}' — skipping location", SITE)
                        continue
                    if base_url in failed_domains:
                        continue
                    if base_url not in logged_in_domains:
                        if not _login_portal(page, creds, base_url):
                            logger.error(f"Skipping {location} because login to {base_url} failed", SITE)
                            failed_domains.add(base_url)
                            continue
                        logged_in_domains.add(base_url)
                    _apply_jobstreet_jobs(page, job_title, location, base_url)
        except Exception as e:
            logger.error(f"JobStreet/SEEK bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass

def _login_portal(page, creds, base_url: str) -> bool:
    logger.info(f"Logging into JobStreet portal {base_url}...", SITE)
    try:
        page.goto(f"{base_url}/oauth/login?returnUrl=%2F", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to navigate to JobStreet login: {e}", SITE)
    _human_delay(3, 4)
    
    # Check if already logged in
    if "oauth/login" not in page.url or page.query_selector('[data-automation="user-profile-button"], button[aria-label*="Profile"]'):
        logger.success("JobStreet already logged in via active session", SITE)
        return True

    # Click Continue with Email if visible on first screen
    try:
        email_continue = page.locator('button:has-text("Continue with Email"), a:has-text("Continue with Email"), [data-automation="email-signin"]').first
        if email_continue.is_visible():
            email_continue.click()
            _human_delay(1.5, 2)
    except Exception:
        pass
        
    try:
        # Fill email
        email_field = page.locator('input[type="email"], #emailAddress, input[name="emailAddress"]').first
        if email_field.is_visible():
            from bot.utils.safety import human_fill
            human_fill(email_field, creds["email"], "JobStreet Email", SITE)
            _human_delay(1, 2)
            
            submit_btn = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Continue"), button:has-text("Next")').first
            submit_btn.click()
            _human_delay(3, 4)

        # 1. Try OTP / Sign-in Code Login first
        try:
            code_login_btn = page.locator('button:has-text("Email me a sign in code"), span:has-text("Email me a sign in code")').first
            if code_login_btn.is_visible():
                logger.info("JobStreet Login: Clicking 'Email me a sign in code'...", SITE)
                code_login_btn.click()
                logger.info("JobStreet Login: Sent sign-in code to email. Waiting for code...", SITE)
                _human_delay(3, 4)
                
                # Retrieve OTP
                from bot.utils.gmail_otp import wait_for_otp
                otp = wait_for_otp(site="jobstreet", timeout_seconds=45)
                
                if otp:
                    # Fill OTP into boxes
                    inputs = page.query_selector_all('input[type="text"], input[type="tel"], input[autocomplete="one-time-code"]')
                    visible_inputs = [inp for inp in inputs if inp.is_visible() and inp.get_attribute("type") not in ["email", "password"]]
                    
                    if len(visible_inputs) >= 6:
                        logger.info("JobStreet Login: Filling 6-digit code char-by-char...", SITE)
                        visible_inputs[0].click()
                        _human_delay(0.5, 0.8)
                        for char in otp:
                            page.keyboard.press(char)
                            _human_delay(0.1, 0.2)
                    elif len(visible_inputs) >= 1:
                        logger.info("JobStreet Login: Filling code into input field...", SITE)
                        visible_inputs[0].fill(otp)
                        
                    _human_delay(1, 2)
                    verify_btn = page.locator('button[type="submit"], button:has-text("Confirm"), button:has-text("Verify"), button:has-text("Continue")').first
                    verify_btn.click()
                    _human_delay(5, 7)
                else:
                    logger.info("JobStreet Login: Auto code retrieval unavailable or timed out. Waiting up to 60 seconds for manual login/code entry...", SITE)
                    for i in range(60):
                        if "oauth/login" not in page.url or page.query_selector('[data-automation="user-profile-button"]'):
                            logger.success("JobStreet login successful via manual entry! ✅", SITE)
                            return True
                        time.sleep(1)
                        if (i + 1) % 15 == 0:
                            logger.info(f"Still waiting... {60 - (i + 1)} seconds remaining.", SITE)
                            
                # Check success
                if "oauth/login" not in page.url or page.query_selector('[data-automation="user-profile-button"]'):
                    logger.success("JobStreet login successful via Sign-in Code! ✅", SITE)
                    return True
        except Exception as e:
            logger.warn(f"JobStreet sign-in code flow failed or not available: {e}", SITE)

        # 2. Fallback to Direct Password Login (using password Shiva26@)
        logger.info("JobStreet Login: Falling back to direct password login...", SITE)
        try:
            # Re-navigate/reset if we got stuck
            if "oauth/login" not in page.url:
                page.goto(f"{base_url}/oauth/login?returnUrl=%2F", wait_until="domcontentloaded", timeout=30000)
                _human_delay(3, 4)
                
            # Click Continue with Email if visible
            email_continue = page.locator('button:has-text("Continue with Email"), a:has-text("Continue with Email"), [data-automation="email-signin"]').first
            if email_continue.is_visible():
                email_continue.click()
                _human_delay(1, 2)
                
            email_field = page.locator('input[type="email"], #emailAddress, input[name="emailAddress"]').first
            if email_field.is_visible():
                from bot.utils.safety import human_fill
                human_fill(email_field, creds["email"], "JobStreet Email", SITE)
                _human_delay(1, 2)
                submit_btn = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Continue"), button:has-text("Next")').first
                submit_btn.click()
                _human_delay(3, 4)
                
            pass_field = page.locator('input[type="password"], #password, input[name="password"]').first
            if pass_field.is_visible():
                from bot.utils.safety import human_fill
                password_to_use = "Shiva26@" if "Shiva26@" not in creds["password"] else creds["password"]
                human_fill(pass_field, password_to_use, "JobStreet Password", SITE)
                _human_delay(1, 2)
                
                submit_btn = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in")').first
                submit_btn.click()
                _human_delay(5, 7)
                
                if "oauth/login" not in page.url or page.query_selector('[data-automation="user-profile-button"]'):
                    logger.success("JobStreet password login successful! ✅", SITE)
                    return True
        except Exception as e:
            logger.warn(f"JobStreet direct password login fallback failed: {e}", SITE)

        # 3. Fallback to Google SSO
        logger.info("JobStreet Login: Falling back to Google SSO...", SITE)
        try:
            if "oauth/login" not in page.url:
                page.goto(f"{base_url}/oauth/login?returnUrl=%2F", wait_until="domcontentloaded", timeout=30000)
                _human_delay(3, 4)
                
            google_btn = None
            for sel in ['button:has-text("Continue with Google")', 'a:has-text("Continue with Google")', 'button:has-text("Google")', 'a:has-text("Google")', '[data-automation="google-signin"]']:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    google_btn = el
                    break
                    
            if google_btn:
                popup = None
                try:
                    with page.context.expect_page(timeout=5000) as popup_info:
                        google_btn.click()
                    popup = popup_info.value
                except Exception:
                    pass
                    
                auth_page = popup if popup else page
                try:
                    auth_page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                _human_delay(2, 3)
                
                if not auth_page.is_closed() and "accounts.google.com" in auth_page.url:
                    from bot.utils.safety import handle_google_sso
                    gmail_pass = os.getenv("GMAIL_PASSWORD") or creds.get("password")
                    handle_google_sso(auth_page, "sivashankar.avi6@gmail.com", gmail_pass)
            
            for _ in range(15):
                if "oauth/login" not in page.url or page.query_selector('[data-automation="user-profile-button"]'):
                    logger.success("JobStreet login successful via Google SSO ✅", SITE)
                    return True
                time.sleep(1)
        except Exception as e:
            logger.warn(f"JobStreet Google SSO fallback failed: {e}", SITE)

        logger.error("JobStreet login verification failed", SITE)
        return False
    except Exception as e:
        logger.error(f"JobStreet login failed: {e}", SITE)
        return False

def _apply_jobstreet_jobs(page, job_title: str, location: str, base_url: str):
    from bot.utils.logger import record_application, is_already_applied, git_sync
    from bot.ai_agent_filler import fill_form_with_ai

    logger.info(f"Searching JobStreet: '{job_title}' in '{location}' on {base_url}", SITE)
    search_url = f"{base_url}/jobs?keywords={urllib.parse.quote(job_title)}&where={urllib.parse.quote(location)}"
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to load JobStreet search results: {e}", SITE)
        return
        
    _human_delay(3, 4)

    # Scroll to load jobs
    for _ in range(2):
        page.mouse.wheel(0, 500)
        _human_delay(0.5, 1)

    cards = page.query_selector_all('article[data-card-type], [data-automation="jobCard"], [data-automation="jobTitle"]')
    logger.info(f"Found {len(cards)} job cards on JobStreet page", SITE)

    applied = 0
    for card in cards[:15]:
        if not check_daily_limit(SITE):
            return
        try:
            if not card.is_visible():
                continue
            card.scroll_into_view_if_needed()
            _human_delay(0.3, 0.5)
            
            # Click title link if present, or the card
            title_link = card.query_selector('[data-automation="jobTitle"]')
            if title_link:
                title_link.click()
            else:
                card.click()
            _human_delay(2, 3)

            # Extract details
            def _text(selectors):
                for s in selectors:
                    try:
                        el = page.query_selector(s)
                        if el and el.is_visible():
                            t = el.inner_text().strip()
                            if t: return t
                    except Exception:
                        continue
                return ""

            job_t = _text([
                '[data-automation="job-detail-title"]',
                'h1[data-automation="job-title"]',
                'h1',
                '.job-detail-title h1'
            ]) or job_title

            # Clean job title (remove location keywords)
            job_t = re.sub(r'\s+', ' ', job_t).strip()
            job_t = re.sub(r'\b(Job\s+)?in\s+.*$', '', job_t, flags=re.IGNORECASE).strip()
            job_t = re.sub(r'\b(Johor|Selangor|Kuala Lumpur|Shah Alam|Subang|Bangalore|Chennai|Remote|Singapore|Malaysia|India).*$', '', job_t, flags=re.IGNORECASE).strip()
            job_t = re.sub(r'[\s\-,\/\|\(\)]+$', '', job_t).strip()

            company = _text([
                '[data-automation="advertiser-name"]',
                'span[data-automation="company-name"]',
                '.company-name',
                '[data-automation="jobCardCompany"]'
            ]) or "Company"

            desc = _text([
                '[data-automation="jobDescription"]',
                'div[class*="jobDescription"]',
                '.job-description',
                '#jobDescriptionText'
            ])

            if is_already_applied(SITE, company, job_t):
                logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
                continue

            # Check for Apply button
            apply_btn = None
            for sel in [
                '[data-automation="job-detail-apply"]',
                'a:has-text("Apply")',
                'button:has-text("Quick Apply")',
                'a:has-text("Apply now")'
            ]:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    apply_btn = el
                    break

            if not apply_btn:
                continue

            # Tailor Resume / Match Score
            tailor_result = tailor_resume(job_t, company, desc, site=SITE)
            resume_path = tailor_result["resume_path"]
            match_score = tailor_result["match_score"]

            if not resume_path:
                logger.info(f"Skipping {company} - {job_t} (Tech stack or experience mismatch)", SITE)
                continue

            if match_score < MIN_MATCH:
                logger.info(f"Skipping {company} - {job_t} (Match score {match_score}% < {MIN_MATCH}%)", SITE)
                continue

            logger.info(f"🎯 Applying on JobStreet: {company} - {job_t} ({match_score}%)", SITE)
            
            # Click apply and check if it opens a new tab or redirects the current tab
            new_page = None
            try:
                target_attr = apply_btn.get_attribute("target")
                if target_attr == "_blank":
                    with page.context.expect_page(timeout=8000) as new_page_info:
                        apply_btn.click()
                    new_page = new_page_info.value
                else:
                    try:
                        with page.context.expect_page(timeout=5000) as new_page_info:
                            apply_btn.click()
                        new_page = new_page_info.value
                    except Exception:
                        new_page = page
            except Exception as click_err:
                logger.warn(f"Failed to execute click or page redirect: {click_err}", SITE)
                continue

            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

            # Use AI Form Filler
            success = fill_form_with_ai(new_page, site=SITE, resume_path=resume_path)

            if success:
                record_application(
                    site=SITE, company=company, role=job_t, location=location,
                    job_url=page.url, match_score=match_score,
                    resume_used=resume_path,
                )
                git_sync()
                applied += 1
                increment_daily_count(SITE)
                _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 4)
                
            try:
                if new_page and new_page != page:
                    new_page.close()
            except Exception:
                pass

        except Exception as e:
            logger.warn(f"JobStreet job error: {e}", SITE)
            continue

    logger.info(f"JobStreet: Applied to {applied} jobs for '{job_title}' in {location}", SITE)
