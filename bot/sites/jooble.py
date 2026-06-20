"""
sites/jooble.py — Jooble.org job aggregator automation
"""
import time, random, os, urllib.parse
from playwright.sync_api import sync_playwright
from bot.config import CREDENTIALS, JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.utils import logger
from bot.utils.safety import safe_browser_context, check_daily_limit, increment_daily_count

SITE = "jooble"
BASE_URL = "https://jooble.org"
MIN_MATCH = int(os.getenv("MIN_MATCH_SCORE", "60"))

def _human_delay(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))

def run_jooble_bot():
    logger.info("🚀 Starting Jooble bot", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.new_page()

        try:
            for job_title in JOB_TITLES:
                for location in LOCATIONS:
                    if not check_daily_limit(SITE):
                        logger.info("Jooble daily limit reached", SITE)
                        return
                    _apply_jooble_jobs(page, job_title, location)
        except Exception as e:
            logger.error(f"Jooble bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass

def _apply_jooble_jobs(page, job_title: str, location: str):
    from bot.utils.logger import record_application, is_already_applied, git_sync
    from bot.ai_agent_filler import fill_form_with_ai

    logger.info(f"Searching Jooble: '{job_title}' in '{location}'", SITE)
    search_url = f"{BASE_URL}/jobs?q={urllib.parse.quote(job_title)}&l={urllib.parse.quote(location)}"
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warn(f"Failed to load Jooble search results: {e}", SITE)
        return
        
    _human_delay(3, 4)

    # Scroll to load jobs
    for _ in range(2):
        page.mouse.wheel(0, 500)
        _human_delay(0.5, 1)

    # Scrape job card URLs
    job_urls = []
    seen = set()
    links = page.query_selector_all('a[href*="/desc/"]')
    for link in links:
        href = link.get_attribute("href")
        if href and href not in seen:
            if href.startswith("/"):
                href = BASE_URL + href
            job_urls.append(href)
            seen.add(href)

    logger.info(f"Found {len(job_urls)} jobs on Jooble page", SITE)

    applied = 0
    for u in job_urls[:10]:
        if not check_daily_limit(SITE):
            return
        try:
            page.goto(u, wait_until="domcontentloaded", timeout=25000)
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
                "h1[class*='title']",
                "h1",
                ".job-title",
                "h2"
            ]) or job_title

            company = _text([
                "[class*='company']",
                ".company-name",
                ".comp-name",
                "h3"
            ]) or "Company"

            desc = _text([
                "[class*='description']",
                ".job-description",
                ".description",
                "div[id*='desc']"
            ])

            if is_already_applied(SITE, company, job_t):
                logger.info(f"Skipping {company} - {job_t} (Already applied)", SITE)
                continue

            # Look for apply redirection button
            apply_btn = None
            for sel in [
                'a[href*="/away/"]',
                'a:has-text("Apply")',
                'button:has-text("Apply")',
                'a[target="_blank"]'
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

            logger.info(f"🎯 Applying to Jooble: {company} - {job_t} ({match_score}%)", SITE)
            
            # Click apply which redirects to target ATS
            with page.context.expect_page(timeout=15000) as new_page_info:
                apply_btn.click()
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded", timeout=15000)

            # Fill details on target ATS using AI agent filler
            success = fill_form_with_ai(new_page, site=SITE, resume_path=resume_path)

            if success:
                # Fill form and record success
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
                new_page.close()
            except Exception:
                pass

        except Exception as e:
            logger.warn(f"Jooble job error: {e}", SITE)
            continue

    logger.info(f"Jooble: Applied to {applied} jobs for '{job_title}' in {location}", SITE)
