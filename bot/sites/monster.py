"""
sites/monster.py — Foundit (formerly Monster India) automation with Google SSO login
"""
import time, random, os
from playwright.sync_api import sync_playwright
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger
from bot.utils.safety import safe_browser_context

SITE = "monster"
MIN_MATCH = int(os.getenv("MIN_MATCH_SCORE", "60"))

def get_foundit_base_url(location: str) -> str:
    loc = location.lower()
    if "singapore" in loc: return "https://www.foundit.sg"
    elif "malaysia" in loc: return "https://www.foundit.my"
    elif "philippines" in loc: return "https://www.foundit.com.ph"
    elif "hong kong" in loc: return "https://www.foundit.com.hk"
    elif "indonesia" in loc: return "https://www.foundit.id"
    elif "thailand" in loc: return "https://www.foundit.in.th"
    elif "gulf" in loc or "uae" in loc or "dubai" in loc or "saudi" in loc: return "https://gulf.foundit.in"
    elif any(x in loc for x in ["india", "bangalore", "chennai", "hyderabad", "delhi", "mumbai", "pune"]): return "https://www.foundit.in"
    elif "remote" in loc: return "https://www.foundit.in"  # Default remote to India portal
    return None  # Skip other countries for Foundit

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_monster_bot():
    creds = CREDENTIALS["monster"]
    if not creds["email"] or not creds["password"]:
        logger.warn("Monster/Foundit credentials not configured — skipping", SITE)
        return

    logger.info("🚀 Starting Foundit (formerly Monster) bot", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()

        try:
            logged_in_domains = set()
            failed_domains = set()
            for job_title in JOB_TITLES:
                for location in LOCATIONS:
                    base_url = get_foundit_base_url(location)
                    if not base_url:
                        logger.info(f"Foundit does not operate in '{location}' — skipping location", SITE)
                        continue
                    if base_url in failed_domains:
                        continue
                    if base_url not in logged_in_domains:
                        if not _login_portal(page, creds, base_url):
                            logger.error(f"Skipping {location} because login to {base_url} failed", SITE)
                            failed_domains.add(base_url)
                            continue
                        logged_in_domains.add(base_url)
                    _apply_monster_jobs(page, job_title, location, base_url)
        except Exception as e:
            logger.error(f"Foundit bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass

def _login_portal(page, creds, base_url: str) -> bool:
    logger.info(f"Logging into Foundit portal: {base_url}...", SITE)
    try:
        page.goto(f"{base_url}/rio/login/seeker?return_url=/user", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to navigate to Foundit login page: {e}", SITE)
    _human_delay(3, 4)
    
    # Check if already logged in (redirected away from login URL or has logout/profile indicator)
    if "login" not in page.url or page.query_selector('a[href*="logout"], a[href*="signout"], .usr-profile-name'):
        logger.success(f"Foundit already logged in on {base_url} (URL: {page.url})", SITE)
        return True

    # 1. Attempt OTP Login (using email and login code/OTP)
    try:
        logger.info("Foundit Login: Attempting login via OTP / Login Code...", SITE)
        email_field = page.locator('input[name="userName"], input[name="emailAddress"], input[type="email"]').first
        if email_field.is_visible():
            from bot.utils.safety import human_fill
            human_fill(email_field, creds["email"], "Foundit Email", SITE)
            _human_delay(1, 2)
            
            # Click Send OTP button (which is button#loginSubmit on the default OTP view)
            send_otp_btn = page.locator('button#loginSubmit, #loginSubmit, button:has-text("Send OTP"), .send-otp-btn').first
            if send_otp_btn.is_visible():
                send_otp_btn.click()
                logger.info("Foundit Login: Sent OTP to email. Waiting for code...", SITE)
                _human_delay(3, 4)
                
                # Retrieve OTP
                from bot.utils.gmail_otp import wait_for_otp
                otp = wait_for_otp(site="monster", timeout_seconds=45)
                
                if otp:
                    # Fill OTP
                    inputs = page.query_selector_all('input[type="text"], input[type="tel"]')
                    # Filter out the email field and location selector if present
                    visible_inputs = [inp for inp in inputs if inp.is_visible() and inp.get_attribute("id") not in ["userName", "India", "SE_home_autocomplete", "SE_home_autocomplete_location"]]
                    
                    if len(visible_inputs) >= 6:
                        logger.info("Foundit Login: Filling 6-digit OTP code char-by-char...", SITE)
                        visible_inputs[0].click()
                        _human_delay(0.5, 0.8)
                        for char in otp:
                            page.keyboard.press(char)
                            _human_delay(0.1, 0.2)
                    elif len(visible_inputs) >= 1:
                        logger.info("Foundit Login: Filling OTP code into input field...", SITE)
                        visible_inputs[0].fill(otp)
                        
                    _human_delay(1, 2)
                    submit_btn = page.locator('button#loginSubmit, #loginSubmit, button:has-text("Verify"), button:has-text("Submit"), button:has-text("Login")').first
                    submit_btn.click()
                    _human_delay(4, 5)
                else:
                    logger.info("Foundit Login: Auto OTP retrieval unavailable or timed out. Waiting up to 60 seconds for manual login/code entry...", SITE)
                    for i in range(60):
                        if "login" not in page.url or page.query_selector('a[href*="logout"], a[href*="signout"], .usr-profile-name'):
                            logger.success("Foundit login successful via manual entry! ✅", SITE)
                            return True
                        time.sleep(1)
                        if (i + 1) % 15 == 0:
                            logger.info(f"Still waiting... {60 - (i + 1)} seconds remaining.", SITE)
                            
                # Check if we logged in successfully
                if "login" not in page.url or page.query_selector('a[href*="logout"], a[href*="signout"], .usr-profile-name'):
                    logger.success(f"Foundit login successful via OTP! ✅", SITE)
                    return True
    except Exception as e:
        logger.warn(f"Foundit OTP login flow failed: {e}", SITE)

    # 2. Fallback to Direct Password Login (using password Shiva26@)
    logger.info("Foundit Login: Falling back to direct Password login...", SITE)
    try:
        page.goto(f"{base_url}/rio/login/seeker?return_url=/user", wait_until="domcontentloaded", timeout=30000)
        _human_delay(3, 4)
        
        pwd_toggle = page.locator('text="Login via Password", text="Login with Password", .login-pwd-btn, span:has-text("Password")').first
        if pwd_toggle.is_visible():
            pwd_toggle.click()
            _human_delay(2, 3)
            
        email_field = page.locator('input[name="userName"], input[name="emailAddress"], input[type="email"]').first
        pass_field = page.locator('input[name="password"], input[type="password"]').first
        
        if email_field.is_visible() and pass_field.is_visible():
            from bot.utils.safety import human_fill
            human_fill(email_field, creds["email"], "Foundit Email", SITE)
            # Use the requested password "Shiva26@" as fallback
            password_to_use = "Shiva26@" if "Shiva26@" not in creds["password"] else creds["password"]
            human_fill(pass_field, password_to_use, "Foundit Password", SITE)
            _human_delay(1, 2)
            
            submit_btn = page.locator('button#loginSubmit, #loginSubmit').first
            submit_btn.click()
            _human_delay(5, 7)
            
            if "login" not in page.url or page.query_selector('a[href*="logout"], a[href*="signout"], .usr-profile-name'):
                logger.success(f"Foundit password login successful! ✅", SITE)
                return True
    except Exception as e:
        logger.warn(f"Foundit password fallback failed: {e}", SITE)

    # 3. Fallback to Google SSO
    logger.info("Foundit Login: Falling back to Google SSO...", SITE)
    try:
        page.goto(f"{base_url}/rio/login/seeker?return_url=/user", wait_until="domcontentloaded", timeout=30000)
        _human_delay(3, 4)
        
        google_btn = page.locator('button:has-text("Google"), a:has-text("Google"), .google-login-btn').first
        if google_btn.is_visible():
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
                if "login" not in page.url or page.query_selector('a[href*="logout"], a[href*="signout"], .usr-profile-name'):
                    logger.success("Foundit login successful via Google SSO ✅", SITE)
                    return True
                time.sleep(1)
    except Exception as e:
        logger.warn(f"Foundit Google SSO fallback failed: {e}", SITE)
        
    return False
def _dismiss_foundit_popups(page):
    try:
        # Check standard close buttons
        for sel in [
            'button.popupClose', 'button.close', '.modal-close',
            'button[class*="close"]', '.popup-close-btn', 'button:has-text("x")',
            'button:has-text("Close")', 'a:has-text("Not Now")', 'button:has-text("Not Now")',
            'a:has-text("Skip")', 'button:has-text("Skip")', '#acceptAll'
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    logger.info(f"Dismissing Foundit popup via button click: '{sel}'", SITE)
                    el.click()
                    _human_delay(1, 2)
            except Exception:
                continue

        # Use DOM cleanup script to remove modal backdrops/overlays intercepting clicks
        page.evaluate("""() => {
            const overlays = Array.from(document.querySelectorAll('div')).filter(el => {
                const id = el.id || '';
                const cls = el.className || '';
                return id.includes('global-ui-modal') || id.includes('modal') || cls.includes('modal') || cls.includes('overlay');
            });
            overlays.forEach(el => {
                if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                    const closeBtns = el.querySelectorAll('[class*="close"], button, .popupClose');
                    let clicked = false;
                    for (let btn of closeBtns) {
                        const txt = (btn.innerText || btn.value || '').toLowerCase();
                        if (txt.includes('x') || txt.includes('close') || txt.includes('not now') || txt.includes('skip') || btn.className.includes('close')) {
                            btn.click();
                            clicked = true;
                            break;
                        }
                    }
                    if (!clicked) {
                        el.remove();
                    }
                }
            });
            const backdrops = document.querySelectorAll('.fixed.inset-0.bg-black, [class*="modal-backdrop"], .bg-black');
            backdrops.forEach(el => el.remove());
        }""")
        page.keyboard.press("Escape")
    except Exception:
        pass

def _apply_monster_jobs(page, job_title: str, location: str, base_url: str):
    from urllib.parse import quote
    from bot.utils.logger import record_application, is_already_applied, git_sync
    from bot.ai_agent_filler import fill_form_with_ai

    logger.info(f"Searching Foundit: '{job_title}' in '{location}' on {base_url}", SITE)
    url = f"{base_url}/srp/results?query={quote(job_title)}&locations={quote(location)}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to load Foundit SRP URL: {e}", SITE)
        return
        
    _human_delay(3, 4)
    _dismiss_foundit_popups(page)

    # Scroll to load jobs
    for _ in range(2):
        page.mouse.wheel(0, 500)
        _human_delay(0.5, 1)

    applied = 0
    cards = page.query_selector_all(".card-body, .job-tittle, .jobCardWrapper, div[class*='card']")
    logger.info(f"Found {len(cards)} job cards on Foundit page", SITE)

    for card in cards[:15]:
        try:
            _dismiss_foundit_popups(page)
            if not card.is_visible():
                continue
            card.scroll_into_view_if_needed()
            _human_delay(0.3, 0.5)
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
                "h1.title", "h1.job-title", "h1[class*='title']",
                ".job-header h1", ".title", ".job-tittle"
            ]) or job_title

            company = _text([
                ".company-name", "a[class*='company']",
                ".comp-name", ".comp-name-link"
            ]) or "Company"

            desc = _text([
                ".job-description", ".jd-description",
                "div[class*='description']", "#jobDescriptionText",
                ".description"
            ])

            if is_already_applied(SITE, company, job_t):
                logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
                continue

            # Check for Apply button
            apply_btn = None
            for sel in [
                'button:has-text("Apply")', 'a:has-text("Apply")',
                'button[class*="apply"]', 'a[class*="apply"]',
                '.applyBtn', '.apply-button'
            ]:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    apply_btn = el
                    break

            if not apply_btn:
                continue

            # Match Score / Tailor Resume
            tailor_result = tailor_resume(job_t, company, desc, site=SITE)
            resume_path = tailor_result["resume_path"]
            match_score = tailor_result["match_score"]

            if not resume_path:
                logger.info(f"Skipping {company} - {job_t} (Tech stack or experience mismatch)", SITE)
                continue

            if match_score < MIN_MATCH:
                logger.info(f"Skipping {company} - {job_t} (Match score {match_score}% < {MIN_MATCH}%)", SITE)
                continue

            logger.info(f"🎯 Applying to Foundit: {company} - {job_t} ({match_score}%)", SITE)
            _dismiss_foundit_popups(page)
            apply_btn.click()
            _human_delay(2, 3)

            # Fill any form (upload resume/cv, answer questions)
            success = fill_form_with_ai(page, site=SITE, resume_path=resume_path)

            if success:
                submit_btn = page.locator('button[type="submit"], button:has-text("Submit"), button:has-text("Apply Now")').first
                if submit_btn.is_visible():
                    _dismiss_foundit_popups(page)
                    submit_btn.click()
                    _human_delay(2, 3)

                record_application(
                    site=SITE, company=company, role=job_t, location=location,
                    job_url=page.url, match_score=match_score,
                    resume_used=resume_path,
                )
                git_sync()
                applied += 1
                _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 4)

        except Exception as e:
            logger.warn(f"Foundit job error: {e}", SITE)
            continue

    logger.info(f"Foundit: Applied to {applied} jobs for '{job_title}' in {location}", SITE)
