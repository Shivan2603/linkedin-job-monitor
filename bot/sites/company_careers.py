"""
sites/company_careers.py — Universal Company Career Website Automation
Discovers jobs on Lever, Greenhouse, Workday, and direct career portals.
Uses ai_agent_filler to dynamically navigate and submit applications.
Applies broadly to any matching position — no salary/visa filter.
"""
import time, random, re, os
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.ai_agent_filler import fill_form_with_ai
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import safe_browser_context, check_daily_limit, increment_daily_count

SITE = "company_careers"
MIN_MATCH = int(os.getenv("MIN_MATCH_SCORE", "60"))

# ─── DYNAMIC SEARCH QUERIES — massive global coverage ───────────────────────
def _build_search_queries() -> list:
    """Build dynamic Google search queries for all job titles across all major ATS platforms globally."""
    from bot.config import JOB_TITLES, LOCATIONS

    queries = []
    
    # Generate queries dynamically from user's configured titles and locations
    for loc in LOCATIONS:
        for title in JOB_TITLES:
            role = f'"{title}"'
            # Greenhouse & Lever search
            queries.append(f'site:lever.co OR site:greenhouse.io {role} "{loc}" "apply"')
            # Ashby & Workable search
            queries.append(f'site:jobs.ashbyhq.com OR site:apply.workable.com {role} "{loc}"')
            # SmartRecruiters search
            queries.append(f'site:jobs.smartrecruiters.com {role} "{loc}"')
            # Rippling & Breezy search
            queries.append(f'site:jobs.rippling.com OR site:app.breezy.hr {role} "{loc}"')
            # Direct company career site search (excluding aggregators)
            queries.append(f'{role} "careers" "{loc}" -site:linkedin.com -site:indeed.com -site:naukri.com -site:glassdoor.com -site:monster.com -site:foundit.in -site:shine.com -site:jobstreet.com')

    return list(set(queries))

SEARCH_QUERIES = _build_search_queries()

# ─── ULTIMATE TARGET COMPANIES — 60+ global/product companies ────────────────
TARGET_COMPANIES = [
    # Indian Product Tech Leaders
    {"company": "Zoho", "portal": "direct", "search_url": "https://careers.zoho.com/portal/zohorecruit/en/jobs"},
    {"company": "Freshworks", "portal": "direct", "search_url": "https://jobs.freshworks.com/"},
    {"company": "Razorpay", "portal": "lever", "search_url": "https://jobs.lever.co/razorpay?search=engineer"},
    {"company": "CRED", "portal": "lever", "search_url": "https://jobs.lever.co/cred?search=engineer"},
    {"company": "Swiggy", "portal": "workday", "search_url": "https://swiggy.wd3.myworkdayjobs.com/Careers"},
    {"company": "Zomato", "portal": "direct", "search_url": "https://www.zomato.com/careers"},
    {"company": "Ola", "portal": "direct", "search_url": "https://www.olacabs.com/careers"},
    {"company": "Paytm", "portal": "direct", "search_url": "https://careers.paytm.com/"},
    {"company": "PhonePe", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/phonepe"},
    {"company": "Meesho", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/meesho"},
    {"company": "ShareChat", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/sharechat"},
    {"company": "Zepto", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/zepto"},
    {"company": "Dream11", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/dream11"},
    {"company": "InMobi", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/inmobi"},
    {"company": "Groww", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/groww"},
    {"company": "Zerodha", "portal": "direct", "search_url": "https://careers.zerodha.com/"},

    # US / Global Silicon Valley Product Leaders
    {"company": "Stripe", "portal": "lever", "search_url": "https://jobs.lever.co/stripe?search=engineer"},
    {"company": "OpenAI", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/openai"},
    {"company": "Figma", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/figma"},
    {"company": "GitHub", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/github"},
    {"company": "GitLab", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/gitlab"},
    {"company": "Cloudflare", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/cloudflare"},
    {"company": "MongoDB", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/mongodb"},
    {"company": "Datadog", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/datadog"},
    {"company": "Elastic", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/elastic"},
    {"company": "HubSpot", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/hubspot"},
    {"company": "Twilio", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/twilio"},
    {"company": "Okta", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/okta"},
    {"company": "Snowflake", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/snowflake"},
    {"company": "Zoom", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/zoom"},
    {"company": "Atlassian", "portal": "direct", "search_url": "https://careers.atlassian.com/jobs"},
    {"company": "Shopify", "portal": "direct", "search_url": "https://careers.shopify.com/custom-search"},
    {"company": "Pinterest", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/pinterest"},
    {"company": "Uber", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/uber"},
    {"company": "Lyft", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/lyft"},
    {"company": "Airbnb", "portal": "direct", "search_url": "https://careers.airbnb.com/positions"},
    {"company": "Slack", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/slack"},
    {"company": "Asana", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/asana"},
    {"company": "Box", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/box"},
    {"company": "Robinhood", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/robinhood"},
    {"company": "Coinbase", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/coinbase"},
    {"company": "Notion", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/notion"},
    {"company": "Vercel", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/vercel"},
    {"company": "Netlify", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/netlify"},
    {"company": "Retool", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/retool"},
    {"company": "HashiCorp", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/hashicorp"},
    {"company": "Sentry", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/sentry"},
    {"company": "Postman", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/postman"},
    {"company": "Grafana Labs", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/grafanalabs"},
    {"company": "Docker", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/docker"},
    {"company": "Reddit", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/reddit"},
    {"company": "Discord", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/discord"},
    {"company": "Snap", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/snap"},
    {"company": "ZoomInfo", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/zoominfo"},
    {"company": "Canva", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/canva"},

    # European Tech Leaders
    {"company": "Bolt", "portal": "direct", "search_url": "https://careers.bolt.eu/jobs"},
    {"company": "Spotify", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/spotify"},
    {"company": "Revolut", "portal": "direct", "search_url": "https://careers.revolut.com/positions"},
    {"company": "Wise", "portal": "direct", "search_url": "https://wise.jobs/roles"},
    {"company": "Klarna", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/klarna"},
    {"company": "N26", "portal": "greenhouse", "search_url": "https://boards.greenhouse.io/n26"},
    {"company": "Booking.com", "portal": "direct", "search_url": "https://careers.booking.com/jobs"},
    {"company": "Delivery Hero", "portal": "direct", "search_url": "https://careers.deliveryhero.com/global/en"},
]

def _human_delay(a=2.0, b=4.0):
    time.sleep(random.uniform(a, b))

def run_company_careers_bot():
    """Main entry — discovers and applies to jobs on company career portals"""
    logger.info("🏢 Starting Universal Company Career Pages bot", SITE)

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "company_careers")
        page = context.pages[0] if context.pages else context.new_page()

        applied = 0
        job_urls = []

        try:
            # Step 1: Discover job URLs via Google
            discovered = _discover_jobs_from_google(page)
            job_urls.extend(discovered)
            logger.info(f"Discovered {len(discovered)} job URLs from Google search", SITE)

            # Step 2: Discover jobs directly from target company boards
            direct_discovered = _discover_jobs_from_target_companies(page)
            job_urls.extend(direct_discovered)
            logger.info(f"Discovered {len(direct_discovered)} job URLs directly from target companies", SITE)

            # De-duplicate
            job_urls = list(set(job_urls))
            logger.info(f"Total deduplicated job URLs to process: {len(job_urls)}", SITE)

            # Step 3: Apply to each discovered URL
            for url in job_urls:
                if not check_daily_limit(SITE):
                    logger.info("Company Careers daily limit reached", SITE)
                    break
                try:
                    result = _apply_to_career_page(page, url)
                    if result:
                        applied += 1
                        increment_daily_count(SITE)
                        _human_delay(APPLY_DELAY_SECONDS, APPLY_DELAY_SECONDS + 8)
                except Exception as e:
                    logger.warn(f"Error processing {url[:80]}…: {e}", SITE)
                    continue

        except Exception as e:
            logger.error(f"Company Careers bot crash: {e}", SITE)
        finally:
            try:
                browser.close()
            except Exception:
                pass
            logger.info(f"✅ Company Careers bot finished. Applied to {applied} positions.", SITE)

def _discover_jobs_from_google(page) -> list:
    """Search Google for job listings on known ATS platforms"""
    urls = []
    # Query 8 random search queries per session for broad randomized coverage without Google rate limits
    queries_to_run = random.sample(SEARCH_QUERIES, min(8, len(SEARCH_QUERIES)))
    
    for query in queries_to_run:
        try:
            google_url = f"https://www.google.com/search?q={quote(query)}&num=15"
            page.goto(google_url, wait_until="domcontentloaded", timeout=20000)
            _human_delay(2, 4)

            # Extract result links dynamically (filtering out aggregators and keeping ATS/Careers/Apply links)
            links = page.eval_on_selector_all(
                "a[href]",
                """els => els.map(el => {
                    const href = el.href;
                    try {
                        const url = new URL(href);
                        const host = url.hostname.toLowerCase();
                        const path = url.pathname.toLowerCase();
                        
                        // Exclude search engines & major aggregators
                        const blacklist = [
                            'google.', 'youtube.', 'github.', 'facebook.', 'twitter.', 'x.com', 'instagram.', 'pinterest.',
                            'linkedin.com', 'indeed.com', 'glassdoor.', 'naukri.com', 'monster.com', 'foundit.', 'shine.com',
                            'jooble.', 'jobstreet.', 'seek.com', 'simplyhired', 'ziprecruiter', 'careerbuilder',
                            'talent.com', 'neuvoo', 'upwork', 'fiverr', 'freelancer', 'ambitionbox', 'levels.fyi'
                        ];
                        if (blacklist.some(domain => host.includes(domain))) return null;
                        
                        // Check if it matches major ATS or has job/career terms in URL or link text
                        const isAts = host.includes('lever.co') || host.includes('greenhouse.io') || 
                                      host.includes('workday.com') || host.includes('ashbyhq.com') || 
                                      host.includes('smartrecruiters.com') || host.includes('breezy.hr') ||
                                      host.includes('rippling.com') || host.includes('workable.com') ||
                                      host.includes('recruitee.com');
                                      
                        const hasJobTerm = path.includes('job') || path.includes('career') || 
                                           path.includes('apply') || path.includes('position') || 
                                           path.includes('opening') || host.includes('careers.');
                                           
                        if (isAts || hasJobTerm) {
                            return href;
                        }
                    } catch (err) {}
                    return null;
                }).filter(h => h !== null)"""
            )
            # Filter to apply pages and de-duplicate
            apply_links = list(set([l for l in links if "/apply" in l or "job" in l.lower() or "career" in l.lower()]))
            urls.extend(apply_links[:5])  # Max 5 per query
            logger.info(f"Google query found {len(apply_links)} job links: {query[:60]}", SITE)
            _human_delay(3, 5)

        except Exception as e:
            logger.warn(f"Google discovery failed for query: {e}", SITE)

    return list(set(urls))

def _discover_jobs_from_target_companies(page) -> list:
    """Discover jobs directly by crawling target company job portals"""
    urls = []
    logger.info("Discovering jobs directly from target companies...", SITE)
    
    # Crawl 10 random target companies per execution cycle to prevent bans/throttling
    companies_to_crawl = random.sample(TARGET_COMPANIES, min(10, len(TARGET_COMPANIES)))
    
    for tc in companies_to_crawl:
        try:
            logger.info(f"Checking target company career portal: {tc['company']}...", SITE)
            page.goto(tc["search_url"], wait_until="domcontentloaded", timeout=25000)
            _human_delay(3, 5)

            # Collect all links
            links = page.query_selector_all("a[href]")
            tc_urls = []
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if not href:
                        continue
                    text = link.inner_text().lower().strip()
                    
                    # Target .NET, C#, general engineering roles
                    is_match = any(x in text for x in [".net", "c#", "dotnet", "software", "engineer", "developer", "backend"])
                    is_blacklist = any(x in text for x in ["java", "python", "golang", "ruby", "qa", "testing", "product manager", "sales"])
                    
                    if is_match and not is_blacklist:
                        resolved_url = urljoin(tc["search_url"], href)
                        if "lever.co" in resolved_url or "greenhouse.io" in resolved_url or "jobs" in resolved_url or "career" in resolved_url:
                            tc_urls.append(resolved_url)
                except Exception:
                    continue
                    
            if tc_urls:
                logger.info(f"Found {len(tc_urls)} matching positions for {tc['company']}", SITE)
                urls.extend(tc_urls[:4])  # Limit to top 4 matches per company
                
        except Exception as e:
            logger.warn(f"Failed to check target company {tc['company']}: {e}", SITE)
            continue
            
    return list(set(urls))

def _apply_to_career_page(page, url: str) -> bool:
    """Navigate to a career page URL and attempt to apply using AI form filler"""
    logger.info(f"Processing: {url[:80]}…", SITE)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _human_delay(2, 4)

        # Extract company & job title from page
        page_title = page.title()
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

        # Get job description
        desc = ""
        try:
            desc_el = page.query_selector(".job-description, .description, #job-description, main, [class*='description']")
            desc = desc_el.inner_text()[:3000] if desc_el else page.inner_text("body")[:3000]
        except Exception:
            pass

        # Tailor resume
        tailor_result = tailor_resume(job_t, company, desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        if match_score < MIN_MATCH:
            logger.info(f"Skipping {company} — {job_t} (Match score {match_score}% < {MIN_MATCH}%)", SITE)
            return False

        # Use AI to fill all form fields intelligently including file/resume uploads
        success = fill_form_with_ai(page, site=SITE, resume_path=resume_path)

        if not success:
            logger.warn(f"AI form fill failed for {company} — {job_t}", SITE)
            return False

        # Look for submit button
        submit_btn = None
        for sel in [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Submit")', button_text_match("Submit Application"),
            'button:has-text("Apply")', 'button:has-text("Send Application")'
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    submit_btn = el
                    break
            except Exception:
                continue

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

def button_text_match(text: str) -> str:
    return f'button:has-text("{text}")'

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
        m = re.search(r'lever\.co/([^/]+)', url)
        if m: return m.group(1).title()
        m = re.search(r'greenhouse\.io/([^/]+)', url)
        if m: return m.group(1).title()
        m = re.search(r'https?://(?:www\.|careers\.)?([^./]+)', url)
        if m: return m.group(1).title()
    except Exception:
        pass
    return "Unknown Company"
