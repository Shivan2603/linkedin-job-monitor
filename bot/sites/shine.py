"""
sites/shine.py — Shine.com automation
"""
import time, random, os
from playwright.sync_api import sync_playwright
from bot.utils.safety import safe_browser_context, select_best_resume_file
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
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()

        try:
            if _login_portal(page, creds):
                # Update profile / upload resume
                _update_shine_profile(page)
                
                # Apply for jobs
                for job_title in JOB_TITLES[:4]:  # Shine has less jobs, limit
                    for location in LOCATIONS:
                        _apply_shine_jobs(page, job_title, location)
        except Exception as e:
            logger.error(f"Shine bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass

def _login_portal(page, creds) -> bool:
    logger.info("Logging into Shine...", SITE)
    try:
        page.goto("https://www.shine.com/login/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to navigate to Shine login: {e}", SITE)
    _human_delay(3, 4)
    
    # Check if already logged in (redirected to dashboard/profile)
    if "login" not in page.url or page.query_selector('.profile_Name, a[href*="myprofile"], a[href*="logout"]'):
        logger.success("Shine already logged in via cookies", SITE)
        return True
        
    try:
        email_field = page.locator('#id_email_login').first
        pass_field = page.locator('#id_password').first
        
        if email_field.is_visible() and pass_field.is_visible():
            logger.info("Shine Login: Attempting direct email/password login...", SITE)
            from bot.utils.safety import human_fill
            human_fill(email_field, creds["email"], "Shine Email", SITE)
            human_fill(pass_field, creds["password"], "Shine Password", SITE)
            _human_delay(1, 2)
            
            submit_btn = page.locator('button:has-text("Login"), .cls_login_btn, button[type="submit"]').first
            submit_btn.click()
            _human_delay(5, 7)
            
            # Verify redirection/success
            for _ in range(10):
                if "login" not in page.url or page.query_selector('.profile_Name, a[href*="myprofile"]'):
                    logger.success("Shine login successful ✅", SITE)
                    return True
                time.sleep(1)
                
        # Google SSO Fallback
        logger.info("Shine Login: Falling back to Google SSO...", SITE)
        google_btn = page.locator('button:has-text("Google"), .google-login-btn, a[href*="google"]').first
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
                
            # Verify login status
            for _ in range(15):
                if "login" not in page.url or page.query_selector('.profile_Name, a[href*="myprofile"]'):
                    logger.success("Shine login successful via SSO ✅", SITE)
                    return True
                time.sleep(1)
                
        logger.error("Shine login verification failed", SITE)
        return False
    except Exception as e:
        logger.error(f"Shine login failed: {e}", SITE)
        return False

def _update_shine_profile(page):
    logger.info("Attempting to update Shine profile and upload resume...", SITE)
    try:
        profile_url = "https://www.shine.com/myshine/myprofile/"
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        _human_delay(3, 4)
        
        # Upload Latest Base Resume
        from bot.config import BASE_RESUME_DOCX
        if os.path.exists(BASE_RESUME_DOCX):
            upload_input = page.locator('input[type="file"], input[id*="resume"], input[name*="resume"]').first
            if upload_input.is_visible():
                logger.info(f"Uploading base resume to Shine: {BASE_RESUME_DOCX}...", SITE)
                upload_input.set_input_files(BASE_RESUME_DOCX)
                _human_delay(4, 5)
                logger.success("Base resume uploaded successfully to Shine profile ✅", SITE)
            else:
                upload_btn = page.locator('button:has-text("Upload"), a:has-text("Upload"), [class*="upload"]').first
                if upload_btn.is_visible():
                    logger.info("Clicking upload button to select file...", SITE)
                    with page.expect_file_chooser() as fc_info:
                        upload_btn.click()
                    file_chooser = fc_info.value
                    file_chooser.set_files(BASE_RESUME_DOCX)
                    _human_delay(4, 5)
                    logger.success("Base resume uploaded successfully via file chooser ✅", SITE)
        else:
            logger.warn(f"Base resume not found at {BASE_RESUME_DOCX} — skipping upload", SITE)
            
        page.screenshot(path="shine_profile_updated.png")
        logger.info("Saved profile update confirmation screenshot to shine_profile_updated.png", SITE)
        
    except Exception as e:
        logger.warn(f"Failed to update Shine profile: {e}", SITE)

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

            from bot.utils.logger import record_application, is_already_applied, git_sync

            if is_already_applied(SITE, company, job_t):
                logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
                continue

            tailor_result = tailor_resume(job_t, company, desc, site=SITE)
            resume_path = tailor_result.get("resume_path", "")
            if not resume_path:
                logger.info(f"Skipping {company} - {job_t} (Tech stack or experience mismatch)", SITE)
                continue

            apply_btn.click()
            _human_delay(2, 3)

            upload = page.query_selector('input[type="file"]')
            if upload:
                best_resume = select_best_resume_file(
                    page, upload,
                    tailor_result.get("resume_path", ""),
                    tailor_result.get("resume_pdf_path", "")
                )
                upload.set_input_files(best_resume)
                _human_delay(1, 2)

            submit = page.query_selector('button[type="submit"]')
            if submit:
                submit.click()

                record_application(
                    site=SITE, company=company, role=job_t, location=location,
                    job_url=page.url, match_score=tailor_result["match_score"],
                    resume_used=tailor_result["resume_path"],
                )
                git_sync()
            applied += 1
            _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 4)

        except Exception as e:
            logger.warn(f"Shine job error: {e}", SITE)
            continue

    logger.info(f"Shine: Applied to {applied} jobs", SITE)
