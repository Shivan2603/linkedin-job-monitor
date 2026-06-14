"""
sites/company_careers.py — Universal Company Career Website Automation
Discovers jobs on Lever, Greenhouse, Workday, and direct career portals.
Uses ai_agent_filler to dynamically navigate and submit applications.
Applies broadly to any matching position — no salary/visa filter.
"""
import time, random, re
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import JOB_TITLES, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.ai_agent_filler import fill_form_with_ai
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync

SITE = "company_careers"

# ─── DYNAMIC SEARCH QUERIES — covers 15+ job boards ─────────────────────────
def _build_search_queries() -> list:
    """Build dynamic Google search queries for all job titles across all major ATS platforms."""
    from bot.config import JOB_TITLES

    # Core ATS platforms used by thousands of companies
    ATS_DOMAINS = [
        "lever.co",
        "greenhouse.io",
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "job-boards.eu.greenhouse.io",
        "jobs.ashbyhq.com",
        "apply.workable.com",
        "jobs.smartrecruiters.com",
        "careers.jobvite.com",
        "app.breezy.hr",
        "jobs.rippling.com",
        "recruiting.ultipro.com",
        "careers.icims.com",
    ]

    ROLE_KEYWORDS = [
        '"senior .net developer"',
        '"senior software engineer" ".net"',
        '"c# developer"',
        '"dotnet developer"',
        '"full stack developer" ".net"',
        '"software engineer" "asp.net"',
        '"backend developer" "c#"',
    ]

    queries = []
    # 1. ATS-specific searches (most reliable)
    for domain in ATS_DOMAINS[:8]:  # Top 8 to avoid too many queries
        kw = " OR ".join(ROLE_KEYWORDS[:3])
        queries.append(f'site:{domain} {kw}')

    # 2. General Google job search (picks up company career pages)
    for title in JOB_TITLES[:3]:
        queries.append(f'"{title}" job "apply now" -.net site:lever.co OR site:greenhouse.io')
        queries.append(f'"{title}" remote "easy apply" site:linkedin.com/jobs')

    # 3. India-specific tech company boards
    queries += [
        'site:careers.zoho.com "software engineer" OR "developer"',
        'site:jobs.freshworks.com "engineer"',
        '"senior .net" OR "c# developer" site:instahyre.com OR site:wellfound.com',
    ]

    return queries

SEARCH_QUERIES = _build_search_queries()


# ─── KNOWN TARGET COMPANIES — direct apply URLs ─────────────────────────────
# These are added directly. Format: {"company": str, "portal": str, "search_url": str}
TARGET_COMPANIES = [
    # Lever.co (common for startups)
    {"company": "Various (Lever)", "portal": "lever",
     "search_url": "https://jobs.lever.co/?search=.net+developer"},

    # Greenhouse.io (used by many mid-size tech cos)
    {"company": "Various (Greenhouse)", "portal": "greenhouse",
     "search_url": "https://boards.greenhouse.io/embed/job_board?for="},

    # India MNCs & product companies
    {"company": "Zoho", "portal": "direct",
     "search_url": "https://careers.zoho.com/portal/zohorecruit/en/jobs"},
    {"company": "Freshworks", "portal": "direct",
     "search_url": "https://jobs.freshworks.com/"},
    {"company": "Razorpay", "portal": "lever",
     "search_url": "https://jobs.lever.co/razorpay?search=engineer"},
    {"company": "CRED", "portal": "lever",
     "search_url": "https://jobs.lever.co/cred?search=engineer"},

    # International companies with remote roles
    {"company": "Automattic", "portal": "lever",
     "search_url": "https://automattic.com/work-with-us/"},
    {"company": "GitLab", "portal": "greenhouse",
     "search_url": "https://boards.greenhouse.io/gitlab"},
]

def _human_delay(a=2.0, b=4.0):
    time.sleep(random.uniform(a, b))

def run_company_careers_bot():
    """Main entry — discovers and applies to jobs on company career portals"""
    logger.info("🏢 Starting Universal Company Career Pages bot", SITE)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        applied = 0
        job_urls = []

        try:
            # Step 1: Discover job URLs via Google
            discovered = _discover_jobs_from_google(page)
            job_urls.extend(discovered)
            logger.info(f"Discovered {len(discovered)} job URLs from Google search", SITE)

            # Step 2: Apply to each discovered URL
            for url in job_urls:
                try:
                    result = _apply_to_career_page(page, url)
                    if result:
                        applied += 1
                        _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 8)
                except Exception as e:
                    logger.warn(f"Error processing {url[:80]}…: {e}", SITE)
                    continue

        except Exception as e:
            logger.error(f"Company Careers bot crash: {e}", SITE)
        finally:
            browser.close()
            logger.info(f"✅ Company Careers bot finished. Applied to {applied} positions.", SITE)

def _discover_jobs_from_google(page) -> list:
    """Search Google for job listings on known ATS platforms"""
    urls = []
    for query in SEARCH_QUERIES[:3]:  # Limit to 3 queries per session
        try:
            google_url = f"https://www.google.com/search?q={quote(query)}&num=10"
            page.goto(google_url, wait_until="domcontentloaded", timeout=20000)
            _human_delay(2, 4)

            # Extract result links
            links = page.eval_on_selector_all(
                "a[href]",
                """els => els.map(el => el.href).filter(href =>
                    href.includes('lever.co') || href.includes('greenhouse.io') ||
                    href.includes('workday.com') || href.includes('ashbyhq.com') ||
                    href.includes('careers.')
                ).filter(href => !href.includes('google'))"""
            )
            # Filter to apply pages and de-duplicate
            apply_links = [l for l in links if "/apply" in l or "job" in l.lower()]
            urls.extend(apply_links[:5])  # Max 5 per query
            logger.info(f"Google query found {len(apply_links)} job links: {query[:60]}", SITE)
            _human_delay(3, 6)  # Be respectful to Google

        except Exception as e:
            logger.warn(f"Google discovery failed for query: {e}", SITE)

    return list(set(urls))  # De-duplicate

def _apply_to_career_page(page, url: str) -> bool:
    """Navigate to a career page URL and attempt to apply using AI form filler"""
    logger.info(f"Processing: {url[:80]}…", SITE)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _human_delay(2, 4)

        # Extract company & job title from page
        page_title = page.title()
        # Try common patterns: "Job Title - Company", "Company | Job Title"
        if " - " in page_title:
            parts = page_title.split(" - ")
            job_t = parts[0].strip()
            company = parts[1].strip() if len(parts) > 1 else "Unknown Company"
        elif " | " in page_title:
            parts = page_title.split(" | ")
            job_t = parts[0].strip()
            company = parts[-1].strip()
        else:
            job_t = "Software Engineer"
            company = _extract_company_from_url(url)

        # Skip if already applied
        if is_already_applied(SITE, company, job_t):
            logger.info(f"Skipping {company} — {job_t} (Already applied)", SITE)
            return False

        # Get job description from page body
        desc = ""
        try:
            desc_el = page.query_selector(".job-description, .description, #job-description, main")
            desc = desc_el.inner_text()[:3000] if desc_el else page.inner_text("body")[:3000]
        except Exception:
            pass

        # Tailor resume
        tailor_result = tailor_resume(job_t, company, desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        # Upload resume if file input exists
        upload = page.query_selector('input[type="file"]')
        if upload:
            try:
                upload.set_input_files(resume_path)
                _human_delay(1, 3)
            except Exception:
                pass

        # Use AI to fill all form fields intelligently
        success = fill_form_with_ai(page, site=SITE)

        if not success:
            logger.warn(f"AI form fill failed for {company} — {job_t}", SITE)
            return False

        # Look for submit button
        submit_btn = page.query_selector(
            'button[type="submit"], input[type="submit"], '
            'button:has-text("Submit"), button:has-text("Apply"), '
            'button:has-text("Send Application")'
        )
        if submit_btn:
            submit_btn.click()
            _human_delay(3, 5)

            record_application(
                site=SITE, company=company, role=job_t, location="Remote/Various",
                job_url=url, match_score=match_score, resume_used=resume_path,
            )
            git_sync()
            logger.success(f"✅ Applied → {company} | {job_t} via {_detect_portal(url)}", SITE)
            return True

    except PWTimeout:
        logger.warn(f"Timeout loading {url[:60]}…", SITE)
    except Exception as e:
        logger.warn(f"Failed to apply at {url[:60]}…: {e}", SITE)

    return False

def _detect_portal(url: str) -> str:
    """Detect which ATS portal a URL belongs to"""
    if "lever.co" in url:       return "Lever"
    if "greenhouse.io" in url:  return "Greenhouse"
    if "workday.com" in url:    return "Workday"
    if "ashbyhq.com" in url:    return "Ashby"
    if "smartrecruiters" in url: return "SmartRecruiters"
    return "Direct"

def _extract_company_from_url(url: str) -> str:
    """Best-effort company name from URL"""
    try:
        # e.g. https://jobs.lever.co/razorpay/... → "razorpay"
        m = re.search(r'lever\.co/([^/]+)', url)
        if m: return m.group(1).title()
        m = re.search(r'greenhouse\.io/([^/]+)', url)
        if m: return m.group(1).title()
        # Fallback: domain name
        m = re.search(r'https?://(?:www\.|careers\.)?([^./]+)', url)
        if m: return m.group(1).title()
    except Exception:
        pass
    return "Unknown Company"
