"""
sites/indeed.py — Indeed Multi-Country Automation with Login Detection
"""
import time, random, os
from playwright.sync_api import sync_playwright
from bot.utils.safety import safe_browser_context, check_daily_limit, increment_daily_count, select_best_resume_file
from bot.config import CREDENTIALS, JOB_TITLES, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger

SITE = "indeed"

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def check_and_handle_cloudflare(page, timeout_seconds=180) -> bool:
    """
    Detects if Indeed displays a Cloudflare challenge page.
    If detected, pauses and requests user interaction.
    """
    if page.is_closed():
        return False
        
    cf_indicators = [
        "additional verification required",
        "please verify you are a human",
        "verify you are human",
        "ray id:",
        "cf-challenge",
        "cloudflare-challenge",
        "just a moment...",
        "checking your browser",
        "enable cookies and javascript"
    ]
    
    try:
        title = page.title().lower()
        content = page.content().lower()
    except Exception:
        return False
        
    is_cf = any(ind in title or ind in content for ind in cf_indicators)
    
    if is_cf:
        logger.warn("⚠️ Cloudflare Human Verification detected! Please complete the verification in the browser window.", SITE)
        # Audible beep warning to get the user's attention
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 500)
                time.sleep(0.2)
        except Exception:
            pass
        
        # Poll the page until the challenge is resolved or timeout
        start = time.time()
        while time.time() - start < timeout_seconds:
            time.sleep(2)
            if page.is_closed():
                return False
            try:
                current_title = page.title().lower()
                current_content = page.content().lower()
                still_cf = any(ind in current_title or ind in current_content for ind in cf_indicators)
                if not still_cf:
                    logger.success("Cloudflare challenge resolved! Resuming bot...", SITE)
                    time.sleep(2)  # short delay for page to settle
                    return True
            except Exception:
                pass
        logger.error("Timed out waiting for Cloudflare challenge resolution.", SITE)
        return False
        
    return True

def is_indeed_logged_in(page) -> bool:
    if page.is_closed():
        return False
        
    # Check for PPID cookie (Indeed persistent authenticated user token)
    try:
        cookies = page.context.cookies()
        ppid_cookie = next((c for c in cookies if c['name'] == 'PPID'), None)
        if ppid_cookie:
            return True
    except Exception:
        pass
        
    url = page.url.lower()
    if "accounts.google.com" in url or "appleid.apple.com" in url:
        return False
    if "/auth" in url or "/passkey" in url or "/mfa" in url:
        return False
        
    cf_indicators = [
        "additional verification required",
        "please verify you are a human",
        "verify you are human",
        "ray id:",
        "cf-challenge",
        "cloudflare-challenge",
        "just a moment...",
        "checking your browser",
        "enable cookies and javascript"
    ]
    try:
        title = page.title().lower()
        content = page.content().lower()
    except Exception:
        return False

    # If currently encountering Cloudflare, we are NOT considered logged in!
    if any(ind in title or ind in content for ind in cf_indicators):
        return False
        
    logged_in_selectors = [
        '.icl-NavigationHeader',
        '[class*="Nav-header"]',
        'a[href*="myjobs"]',
        'button[id="acctSectionHeader"]',
        'button[aria-label="Account"]',
        'a[href*="/resume"]',
        'a[href*="/notifications"]',
        'a[href*="/messages"]',
        'a[href*="/logout"]',
        'button:has-text("Sign out")',
        'a:has-text("Sign out")'
    ]
    for selector in logged_in_selectors:
        try:
            if page.query_selector(selector):
                return True
        except Exception:
            pass
            
    if "indeed.com" in url:
        try:
            has_signin = page.query_selector('a[href*="secure.indeed.com/auth"], a:has-text("Sign in")')
            if not has_signin:
                return True
        except Exception:
            pass
            
    return False

def _ensure_logged_in(page, base_url: str) -> bool:
    """
    Navigates to Indeed base domain, checks if logged in.
    If not, navigates to Indeed login page and waits for user to log in manually.
    """
    logger.info(f"Checking login status for Indeed domain: {base_url}...", SITE)
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to navigate to {base_url}: {e}", SITE)
        
    _human_delay(2, 3)
    if not check_and_handle_cloudflare(page):
        return False
    
    if is_indeed_logged_in(page):
        logger.success(f"Indeed already logged in on {base_url} ✅", SITE)
        return True

    # If not logged in, go to Indeed auth page
    auth_url = f"{base_url}/auth" if "indeed.com" in base_url else "https://secure.indeed.com/auth"
    logger.info(f"Indeed login required. Opening auth portal: {auth_url}...", SITE)
    try:
        page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to navigate to auth page: {e}", SITE)
        
    _human_delay(2, 3)
    if not check_and_handle_cloudflare(page):
        return False

    # Try email/pwd autofill to assist
    creds = CREDENTIALS["indeed"]
    if creds["email"] and creds["password"]:
        try:
            email_input = page.locator('input[type="email"], input[name="__email"]').first
            if email_input.is_visible():
                from bot.utils.safety import human_fill
                human_fill(email_input, creds["email"], "Indeed Email", SITE)
                _human_delay(1, 1.5)
                page.locator('button[type="submit"]').first.click()
                _human_delay(2, 3)
                if not check_and_handle_cloudflare(page):
                    return False
                
                pass_input = page.locator('input[type="password"]').first
                if pass_input.is_visible():
                    human_fill(pass_input, creds["password"], "Indeed Password", SITE)
                    _human_delay(1, 1.5)
                    page.locator('button[type="submit"]').first.click()
                    _human_delay(2, 3)
                    if not check_and_handle_cloudflare(page):
                        return False
        except Exception:
            pass

    # Wait for user to complete login manually
    logger.info("\n" + "="*80 + f"\n⚠️ ACTION REQUIRED: INDEED LOGIN NEEDED FOR {base_url}\n"
                "Please complete the login manually (Email/Google/OTP/Passkey/CAPTCHA) in the browser.\n"
                "The bot will wait here until it detects a successful login session...\n" + "="*80, SITE)

    timeout_sec = 600  # 10 minutes wait
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if page.is_closed():
            return False
        if not check_and_handle_cloudflare(page):
            return False
        
        # Auto-dismiss Indeed's passkey setup prompt if it appears
        try:
            for selector in [
                'button:has-text("Not now")', 
                'a:has-text("Not now")', 
                'button:has-text("Skip")', 
                'a:has-text("Skip")',
                'button:has-text("Ask me later")',
                '[data-testid*="skip"]',
                '#skip-passkey'
            ]:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    logger.info(f"Indeed Login: Auto-dismissing passkey/skip prompt using selector '{selector}'", SITE)
                    el.click()
                    _human_delay(1.5, 2.5)
                    break
        except Exception:
            pass

        if is_indeed_logged_in(page):
            logger.success(f"Indeed login successful on {base_url}! Detected active session ✅", SITE)
            # Save cookies
            from bot.utils.safety import save_cookies
            save_cookies(page.context, SITE)
            return True
            
        time.sleep(2)
        
    logger.error(f"Indeed login verification timed out after 10 minutes on {base_url}", SITE)
    return False

def _apply_indeed_jobs(page, job_title: str, location: str, base_url: str):
    if not check_daily_limit(SITE):
        logger.info("Indeed daily limit reached — stopping", SITE)
        return

    from urllib.parse import quote
    logger.info(f"Searching Indeed: '{job_title}' in '{location}' on {base_url}", SITE)
    url = f"{base_url}/jobs?q={quote(job_title)}&l={quote(location)}&iafilter=1"
    
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        logger.warn(f"Failed to navigate to job list: {e}", SITE)
        return
        
    _human_delay(2, 3)
    if not check_and_handle_cloudflare(page):
        return

    # Extract all job cards matching standard or test ID elements
    cards = page.query_selector_all('div[data-testid="slider_item"]')
    if not cards:
        cards = page.query_selector_all(".job_seen_beacon, .tapItem")

    jobs_to_process = []
    for card in cards:
        try:
            # Check if indeed apply tag or button is present
            indeed_apply = card.query_selector('[data-testid="indeedApply"], .ia-continueButton, [id*="indeedApplyButton"]')
            if not indeed_apply:
                card_text = card.inner_text().lower()
                if "indeed apply" not in card_text and "candidature simplifiée" not in card_text:
                    continue
            
            # Find the job title and link
            link_el = card.query_selector('a.jcs-JobTitle, a[id*="job_"]')
            if not link_el:
                continue
                
            job_url = link_el.get_attribute('href')
            if not job_url:
                continue
                
            if job_url.startswith('/'):
                job_url = f"{base_url}{job_url}"
                
            title_el = card.query_selector(".jobTitle, a.jcs-JobTitle")
            company_el = card.query_selector('.companyName, [data-company-name="true"], [data-testid="company-name"]')
            
            job_t = title_el.inner_text().strip() if title_el else job_title
            company = company_el.inner_text().strip() if company_el else "Company"
            
            jobs_to_process.append({
                "url": job_url,
                "title": job_t,
                "company": company
            })
        except Exception as e:
            logger.warn(f"Error parsing job card metadata: {e}", SITE)

    logger.info(f"Found {len(jobs_to_process)} Indeed Apply jobs to process on search page", SITE)
    applied = 0
    from bot.utils.logger import record_application, is_already_applied, git_sync

    for job in jobs_to_process:
        if not check_daily_limit(SITE):
            logger.info("Indeed daily limit reached — stopping", SITE)
            return
            
        job_url = job["url"]
        job_t = job["title"]
        company = job["company"]
        
        if is_already_applied(SITE, company, job_t):
            logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
            continue
            
        logger.info(f"Opening job page: {company} - {job_t}...", SITE)
        
        # Open in a fresh page context to prevent split-pane overlay bugs
        job_page = page.context.new_page()
        try:
            job_page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            _human_delay(2, 3)
            if not check_and_handle_cloudflare(job_page):
                job_page.close()
                continue
                
            desc_el = job_page.query_selector("#jobDescriptionText")
            desc = desc_el.inner_text().strip() if desc_el else ""
            
            # Match tech stack and experience
            tailor_result = tailor_resume(job_t, company, desc, site=SITE)
            resume_path = tailor_result.get("resume_path", "")
            if not resume_path:
                logger.info(f"Skipping {company} - {job_t} (Tech stack or experience mismatch)", SITE)
                job_page.close()
                continue
                
            # Locate the indeed apply button
            apply_btn = None
            for _ in range(5):
                # 1. Custom styled classes (e.g. css-1ebo7dz)
                apply_btn = job_page.query_selector('button:has(span[class*="css-1ebo7dz"]), button[class*="css-1ebo7dz"]')
                if not apply_btn:
                    apply_btn = job_page.query_selector('button[id*="indeedApplyButton"], button.ia-continueButton')
                # 2. Text fallbacks
                if not apply_btn:
                    apply_btn = job_page.query_selector('button:visible:has-text("Apply"), button:visible:has-text("Apply Now"), button:visible:has-text("Postuler")')
                # 3. Visible button heuristic
                if not apply_btn:
                    btns = job_page.query_selector_all('button:visible')
                    for btn in btns:
                        text = (btn.inner_text() or "").lower()
                        if "apply" in text or "postuler" in text:
                            apply_btn = btn
                            break
                if apply_btn:
                    break
                time.sleep(1)
                
            if not apply_btn:
                logger.warn(f"No Apply button found for job page: {job_url}", SITE)
                job_page.close()
                continue
                
            logger.info("Clicking 'Apply' to enter application wizard...", SITE)
            apply_btn.click()
            _human_delay(3, 4)
            if not check_and_handle_cloudflare(job_page):
                job_page.close()
                continue
                
            # Dynamically fill out the multi-step form wizard using our AI Form Filler
            from bot.ai_agent_filler import fill_form_with_ai
            success = fill_form_with_ai(job_page, site=SITE, resume_path=resume_path)
            
            if success:
                logger.success(f"Successfully applied to {company} - {job_t} ✅", SITE)
                record_application(
                    site=SITE, company=company, role=job_t, location=location,
                    job_url=job_url, match_score=tailor_result["match_score"],
                    resume_used=resume_path,
                )
                increment_daily_count(SITE)
                git_sync()
                applied += 1
                _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 5)
            else:
                logger.warn(f"Failed to submit application wizard for {company} - {job_t}", SITE)
                
        except Exception as e:
            logger.error(f"Error applying to job {company} - {job_t}: {e}", SITE)
        finally:
            try:
                job_page.close()
            except Exception:
                pass
            _human_delay(1.5, 3.0)
            
    logger.info(f"Applied to {applied} jobs on Indeed for '{job_title}' in {location}", SITE)

def run_indeed_bot():
    if not check_daily_limit(SITE):
        logger.info("Indeed daily limit reached — skipping bot execution", SITE)
        return

    logger.info("🚀 Starting Indeed Multi-Country bot", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()

        try:
            logged_in_domains = set()
            failed_domains = set()
            
            # List of all indeed country base domains and target locations
            indeed_countries = [
                ("https://in.indeed.com", ["Remote", "Bangalore", "Chennai", "Hyderabad"]),
                ("https://sg.indeed.com", ["Remote", "Singapore"]),
                ("https://malaysia.indeed.com", ["Remote", "Malaysia", "Kuala Lumpur"]),
                ("https://uk.indeed.com", ["Remote", "London", "United Kingdom"]),
                ("https://au.indeed.com", ["Remote", "Sydney", "Australia"]),
                ("https://ca.indeed.com", ["Remote", "Toronto", "Canada"]),
                ("https://www.indeed.com", ["Remote", "United States"]),
                ("https://ae.indeed.com", ["Remote", "Dubai", "UAE"]),
                ("https://ie.indeed.com", ["Remote", "Dublin", "Ireland"]),
                ("https://nz.indeed.com", ["Remote", "Auckland", "New Zealand"]),
                ("https://de.indeed.com", ["Remote", "Germany"]),
                ("https://nl.indeed.com", ["Remote", "Netherlands"]),
                ("https://se.indeed.com", ["Remote", "Sweden"]),
                ("https://dk.indeed.com", ["Remote", "Denmark"])
            ]

            for base_url, locations in indeed_countries:
                if not check_daily_limit(SITE):
                    logger.info("Indeed daily limit reached — stopping", SITE)
                    return

                if base_url in failed_domains:
                    continue
                if base_url not in logged_in_domains:
                    if not _ensure_logged_in(page, base_url):
                        logger.error(f"Skipping Indeed portal {base_url} because login failed", SITE)
                        failed_domains.add(base_url)
                        continue
                    logged_in_domains.add(base_url)

                for job_title in JOB_TITLES:
                    for location in locations:
                        _apply_indeed_jobs(page, job_title, location, base_url)
                        
        except Exception as e:
            logger.error(f"Indeed bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass
            logger.info("Indeed bot session ended", SITE)
