"""
sites/company_careers.py — Universal Company Career Website Automation
Discovers jobs on Lever, Greenhouse, Workday, Ashby, Workable, SuccessFactors, Taleo, iCIMS, Breezy, Recruitee, and direct career portals.
Prioritizes VISA SPONSORSHIP roles globally (UK Tier 2, US H-1B, Canada, Australia, Germany, Singapore, UAE, etc.).
Uses ai_agent_filler to dynamically navigate and submit applications.
User can take control at ANY TIME by typing 'c' + Enter in the terminal.
"""
import time, random, re, os, json, sys, threading
from urllib.parse import quote, urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bot.config import JOB_TITLES, LOCATIONS, APPLY_DELAY_SECONDS
from bot.ai_resume import tailor_resume
from bot.ai_agent_filler import fill_form_with_ai
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import safe_browser_context, check_daily_limit, increment_daily_count, browser_manager
from bot.utils.learning import learn_from_filled_form

SITE = "company_careers"
MIN_MATCH = int(os.getenv("MIN_MATCH_SCORE", "60"))

# ─── GLOBAL VISA SPONSORSHIP LOCATIONS ────────────────────────────────────────
# Countries/regions known to sponsor skilled worker visas for .NET engineers
VISA_GLOBAL_LOCATIONS = [
    # United Kingdom (Skilled Worker / Tier 2)
    "United Kingdom", "London", "Manchester", "Birmingham", "Edinburgh",
    # United States (H-1B / O-1 / TN)
    "United States", "New York", "San Francisco", "Seattle", "Austin", "Chicago",
    # Canada (Express Entry / LMIA)
    "Canada", "Toronto", "Vancouver", "Calgary", "Ottawa",
    # Australia (TSS 482 / Skilled Independent)
    "Australia", "Sydney", "Melbourne", "Brisbane", "Perth",
    # Germany (EU Blue Card)
    "Germany", "Berlin", "Munich", "Hamburg", "Frankfurt",
    # Singapore (Employment Pass)
    "Singapore",
    # Netherlands (Highly Skilled Migrant)
    "Netherlands", "Amsterdam",
    # Ireland (Critical Skills)
    "Ireland", "Dublin",
    # Sweden / Denmark / Finland / Norway
    "Sweden", "Stockholm", "Denmark", "Copenhagen", "Finland", "Helsinki",
    # UAE / Middle East
    "UAE", "Dubai", "Abu Dhabi",
    # New Zealand (Skilled Migrant)
    "New Zealand", "Auckland",
    # Remote / Global
    "Remote", "Worldwide",
]

VISA_SPONSORSHIP_TERMS = [
    "visa sponsorship", "visa sponsor", "will sponsor", "sponsorship available",
    "we sponsor", "visa support", "relocation assistance", "relocation support",
    "h1b", "h-1b", "tier 2 sponsor", "skilled worker visa", "work permit",
    "work authorization", "employment pass", "global mobility",
]

# ─── TAKE CONTROL ANYTIME (background stdin watcher) ─────────────────────────
_control_event = threading.Event()  # Set when user types 'c'

def _start_control_watcher():
    """Starts a background daemon thread that watches stdin for 'c' to trigger take-control."""
    def _watcher():
        print("\n[BOT] Type 'c' + Enter at ANY TIME to take control of the browser.")
        while True:
            try:
                line = sys.stdin.readline()
                if line.strip().lower() == 'c':
                    _control_event.set()
                    print("[BOT] ⚡ Take-control flagged — bot will pause at next safe point.")
            except Exception:
                break
    t = threading.Thread(target=_watcher, daemon=True)
    t.start()

def _check_take_control(page):
    """If the user typed 'c', disconnect the browser and wait for them to hand back control."""
    if _control_event.is_set():
        _control_event.clear()
        print("\n" + "=" * 70)
        print("⚡  YOU HAVE CONTROL — Browser is now live for your input.")
        print("   Fill forms, solve CAPTCHAs, navigate to any page you want.")
        print("   When finished, press ENTER to hand control back to the bot.")
        print("=" * 70)
        browser_manager.disconnect()
        try:
            input("Press ENTER to return control to the bot: ")
        except Exception:
            pass
        browser_manager.reconnect()
        print("[BOT] Control returned — resuming automation.\n")


# ─── DYNAMIC SEARCH QUERIES — massive global visa sponsorship coverage ────────

def _build_search_queries() -> list:
    """Build Google search queries prioritizing GLOBAL VISA SPONSORSHIP roles matching the .NET/C# profile."""
    from bot.config import JOB_TITLES

    queries = []

    for title in JOB_TITLES:
        role = f'"{title}"'
        # ── Visa sponsorship on major ATS (global, no location lock) ──
        queries.append(f'site:lever.co OR site:greenhouse.io OR site:myworkdayjobs.com {role} "visa sponsorship"')
        queries.append(f'site:jobs.ashbyhq.com OR site:apply.workable.com {role} "visa sponsorship"')
        queries.append(f'site:jobs.smartrecruiters.com OR site:recruitee.com OR site:app.breezy.hr {role} "visa sponsorship"')
        queries.append(f'site:icims.com OR site:taleo.net {role} "visa sponsorship" OR "sponsor visa"')

        # ── UK Skilled Worker / Tier 2 ──
        for loc in ["London", "Manchester", "Birmingham", "United Kingdom"]:
            queries.append(f'site:lever.co OR site:greenhouse.io {role} "{loc}" "visa sponsorship" OR "tier 2"')
            queries.append(f'{role} "{loc}" "visa sponsorship" -site:linkedin.com -site:indeed.com -site:glassdoor.com')

        # ── USA (H-1B willing) ──
        for loc in ["New York", "San Francisco", "Seattle", "Austin"]:
            queries.append(f'site:lever.co OR site:greenhouse.io {role} "{loc}" "h1b" OR "visa sponsorship" OR "will sponsor"')

        # ── Canada / Australia / Germany / Singapore / Netherlands ──
        for loc in ["Canada", "Australia", "Germany", "Singapore", "Netherlands", "Ireland", "Dubai"]:
            queries.append(f'site:lever.co OR site:greenhouse.io OR site:myworkdayjobs.com {role} "{loc}" "visa" OR "relocation" OR "work permit"')

        # ── Remote / global visa sponsorship ──
        queries.append(f'{role} "visa sponsorship" "remote" -site:linkedin.com -site:indeed.com')
        queries.append(f'site:lever.co OR site:greenhouse.io {role} "relocation" OR "globally" "visa" OR "sponsorship"')

    return list(set(queries))


def _ai_generate_search_queries() -> list:
    """Use AI to generate highly targeted Google search queries for GLOBAL VISA SPONSORSHIP .NET jobs."""
    try:
        from bot.ai_router import ai_complete
        from bot.config import JOB_TITLES

        system = (
            "You are an AI recruitment crawler specializing in GLOBAL VISA SPONSORSHIP opportunities. "
            "Generate 20-25 highly effective advanced Google search queries to find direct job application links "
            "for .NET / C# / ASP.NET Core / Azure engineers who need visa sponsorship. "
            "Target ONLY jobs that explicitly offer visa sponsorship, work permits, or relocation assistance. "
            "Focus on major ATS platforms: lever.co, greenhouse.io, myworkdayjobs.com, ashbyhq.com, "
            "workable.com, smartrecruiters.com, taleo.net, icims.com, breezy.hr, recruitee.com.\n\n"
            "Target countries: UK (Tier 2/Skilled Worker), USA (H-1B), Canada (LMIA), Australia (TSS 482), "
            "Germany (EU Blue Card), Singapore (EP), Netherlands, Ireland, UAE, Sweden, Denmark, New Zealand.\n\n"
            "CRITICAL RULES:\n"
            "1. 'site:' operator ONLY for ATS domains — NEVER for location names.\n"
            "2. Include 'visa sponsorship' OR 'will sponsor' OR 'h1b' OR 'tier 2' OR 'work permit' OR 'relocation' in EVERY query.\n"
            "3. Output ONLY a clean list of queries, one per line. No numbering, no markdown."
        )
        user = (
            f"Candidate Profile: .NET Core, C#, ASP.NET Web API, Azure, Microservices, Angular, 4+ years experience\n"
            f"Job Titles: {JOB_TITLES}\n"
            f"Goal: Find globally posted visa-sponsorship .NET jobs and return ready-to-use Google search queries."
        )
        raw = ai_complete(system, user, task="form_fill", max_tokens=1000)
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        cleaned_lines = []
        for line in lines:
            line = re.sub(r'^\d+[\.\-\s]+', '', line)
            line = re.sub(r'^[\*\-\s]+', '', line)
            if line:
                cleaned_lines.append(line)
        return cleaned_lines
    except Exception as e:
        logger.warn(f"AI search query generation failed: {e}", SITE)
        return []


def _ai_generate_target_companies() -> list:
    """Use AI to dynamically generate target companies and their career page search query terms"""
    try:
        from bot.ai_router import ai_complete
        from bot.config import LOCATIONS
        
        system = (
            "You are an AI recruitment researcher. Generate 10 prominent product/technology companies "
            "that hire .NET / C# / Angular developers in these locations. "
            "For each company, provide its name and the google search query to find its career page. "
            "Return EXACTLY a JSON array of objects: [{\"company\": \"Name\", \"search_query\": \"query\"}]"
        )
        user = f"Locations: {LOCATIONS}"
        raw = ai_complete(system, user, task="form_fill", max_tokens=600)
        
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        else:
            m = re.search(r'(\[.*?\])', raw, re.DOTALL)
            raw = m.group(1).strip() if m else raw
            
        return json.loads(raw)
    except Exception as e:
        logger.warn(f"AI target company generation failed: {e}", SITE)
        return []


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

def _check_visa_sponsorship(text: str) -> bool:
    """Returns True if the job description or page text mentions visa sponsorship / relocation."""
    t = text.lower()
    return any(term in t for term in VISA_SPONSORSHIP_TERMS)


def _human_delay(a=2.0, b=4.0):
    time.sleep(random.uniform(a, b))


def run_company_careers_bot():
    """Main entry — discovers and applies to global visa-sponsorship jobs on company career portals"""
    logger.info("🏢 Starting Careers Bot — Global Visa Sponsorship Mode", SITE)
    logger.info("Targets: UK (Tier 2) | USA (H-1B) | Canada | Australia | Germany | Singapore | UAE | Remote", SITE)

    # Start background stdin watcher so user can type 'c' anytime
    if sys.stdin.isatty():
        _start_control_watcher()

    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "company_careers")
        page = context.pages[0] if context.pages else context.new_page()

        applied = 0

        # Now search and apply
        job_urls = []
        try:
            # Step 1: Discover job URLs via search engines (visa-focused queries)
            discovered = _discover_jobs_from_google(page)
            job_urls.extend(discovered)
            logger.info(f"Discovered {len(discovered)} job URLs from visa-sponsorship search queries", SITE)

            # Step 2: Discover jobs directly from static target company boards
            direct_discovered = _discover_jobs_from_target_companies(page)
            job_urls.extend(direct_discovered)
            logger.info(f"Discovered {len(direct_discovered)} job URLs directly from target companies", SITE)

            # Step 3: Discover jobs dynamically from AI-generated target companies
            ai_target_companies = _ai_generate_target_companies()
            if ai_target_companies:
                logger.info(f"AI: Generated {len(ai_target_companies)} dynamic target companies to explore.", SITE)
                for tc in ai_target_companies:
                    try:
                        q = tc.get("search_query")
                        if not q: continue
                        logger.info(f"AI Target Company Query: {q}", SITE)
                        google_url = f"https://www.google.com/search?q={quote(q)}&num=5"
                        page.goto(google_url, wait_until="domcontentloaded", timeout=20000)
                        _human_delay(2, 4)
                        links = page.evaluate("""
                            () => Array.from(document.querySelectorAll('a[href]'))
                                       .map(el => el.href)
                                       .filter(href => href.includes('lever.co') || href.includes('greenhouse.io') || href.includes('myworkdayjobs.com') || href.includes('jobs') || href.includes('career'));
                        """)
                        if links:
                            job_urls.extend(links[:2])
                    except Exception as e:
                        logger.warn(f"Failed to crawl AI target company {tc.get('company')}: {e}", SITE)

            # De-duplicate
            job_urls = list(set(job_urls))

            # ★ Sort: visa-sponsorship keyword URLs float to the TOP of the queue
            visa_urls  = [u for u in job_urls if any(t in u.lower() for t in ["visa", "sponsor", "relocation", "global"])]
            other_urls = [u for u in job_urls if u not in visa_urls]
            job_urls   = visa_urls + other_urls
            logger.info(f"Total URLs: {len(job_urls)} — {len(visa_urls)} flagged as likely visa-sponsorship 🌟", SITE)

            # Step 4: Apply to each discovered URL (visa-first order)
            for url in job_urls:
                # Check if user wants to take control before navigating to each new job
                _check_take_control(page)

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
    """Search Google and DuckDuckGo for job listings using dynamic queries and pagination"""
    urls = []
    
    # Generate queries dynamically using AI
    ai_queries = _ai_generate_search_queries()
    if ai_queries:
        logger.info(f"AI: Generated {len(ai_queries)} dynamic search queries.", SITE)
        queries_to_run = ai_queries[:15]  # Run up to 15 queries
    else:
        # Fallback to random queries
        queries_to_run = random.sample(SEARCH_QUERIES, min(8, len(SEARCH_QUERIES)))
        
    for i, query in enumerate(queries_to_run):
        # Alternate search engines: Google (even indexes) and DuckDuckGo (odd indexes)
        engine = "google" if i % 2 == 0 else "duckduckgo"
        
        # Paging: Crawl 2 pages per query (e.g. Page 1 and Page 2)
        for page_num in range(2):
            try:
                if engine == "google":
                    # Google pagination: start=0, start=10
                    start = page_num * 10
                    search_url = f"https://www.google.com/search?q={quote(query)}&start={start}"
                else:
                    search_url = f"https://duckduckgo.com/?q={quote(query)}"
                    
                logger.info(f"Searching {engine} (Page {page_num + 1}): {query[:60]}...", SITE)
                page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
                _human_delay(2, 4)
                
                if engine == "duckduckgo" and page_num > 0:
                    page.keyboard.press("End")
                    _human_delay(1.5, 2.5)
                    page.keyboard.press("End")
                    _human_delay(1.5, 2.5)
                
                # Extract links dynamically (filtering out aggregators and keeping ATS/Careers/Apply links)
                links = page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('a[href]');
                        return Array.from(els).map(el => {
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
                                    'talent.com', 'neuvoo', 'upwork', 'fiverr', 'freelancer', 'ambitionbox', 'levels.fyi',
                                    'duckduckgo.com', 'bing.com', 'yahoo.com', 'wikipedia.org', 'support.google'
                                ];
                                if (blacklist.some(domain => host.includes(domain))) return null;
                                
                                // Check if it matches major ATS or has job/career terms in URL or link text
                                const isAts = host.includes('lever.co') || host.includes('greenhouse.io') || 
                                              host.includes('myworkdayjobs.com') || host.includes('ashbyhq.com') || 
                                              host.includes('smartrecruiters.com') || host.includes('breezy.hr') ||
                                              host.includes('rippling.com') || host.includes('workable.com') ||
                                              host.includes('recruitee.com') || host.includes('sap.com') ||
                                              host.includes('taleo.net') || host.includes('icims.com');
                                              
                                const hasJobTerm = path.includes('/job') || path.includes('/career') || 
                                                   path.includes('/apply') || path.includes('/position') || 
                                                   path.includes('/opening') || host.includes('careers.');
                                                   
                                if (isAts || hasJobTerm) {
                                    return href;
                                }
                            } catch (err) {}
                            return null;
                        }).filter(h => h !== null);
                    }
                """)
                # Filter to apply pages and de-duplicate
                apply_links = list(set([l for l in links if "/apply" in l or "job" in l.lower() or "career" in l.lower()]))
                urls.extend(apply_links[:10])  # Max 10 per query page
                logger.info(f"Found {len(apply_links)} job links: {query[:50]}", SITE)
                _human_delay(2, 4)
                
                # DuckDuckGo handles paging via scroll/infinite loading, so stop loop
                if engine == "duckduckgo":
                    break
                    
            except Exception as e:
                logger.warn(f"Search discovery failed for query: {e}", SITE)
                
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


def is_block_page(page) -> bool:
    """Returns True if the page displays a Cloudflare block, Access Denied, or 403/404 error."""
    try:
        title = page.title().lower()
        if any(term in title for term in ["access denied", "cloudflare", "attention required", "security check", "forbidden", "403"]):
            return True
        body_text = page.inner_text("body").lower()
        if "cloudflare" in body_text and ("ray id" in body_text or "enable javascript" in body_text or "security check" in body_text):
            return True
        if "access denied" in body_text and "error code 1020" in body_text:
            return True
    except Exception:
        pass
    return False

def _ai_parse_job_and_company(page_title: str, url: str) -> tuple:
    """Uses AI to accurately split the page title or URL into (job_title, company_name) without locations or extensions."""
    try:
        from bot.ai_router import ai_complete
        import json
        
        system = (
            "You are a recruitment scraping assistant. Given a web page title and URL, "
            "extract the clean Job Title and Company Name.\n"
            "Rules:\n"
            "1. Remove experience ranges (e.g. '4-7 years', 'with 4-7 Years of Experience').\n"
            "2. Remove locations (e.g. 'in Philippines', 'Bangalore', 'Remote').\n"
            "3. Remove job board names or tags (e.g. 'foundit', 'JobStreet', 'LinkedIn', 'Careers').\n"
            "4. Return EXACTLY a JSON object: {\"job_title\": \"clean title\", \"company\": \"clean company\"}"
        )
        user = f"Page Title: {page_title}\nURL: {url}"
        raw = ai_complete(system, user, task="form_fill", max_tokens=200)
        
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        else:
            m = re.search(r'(\{.*?\})', raw, re.DOTALL)
            raw = m.group(1).strip() if m else raw
            
        data = json.loads(raw)
        job_t = data.get("job_title", "").strip()
        co = data.get("company", "").strip()
        
        # If company name is a known job board or placeholder, force it to empty so fallback handles it
        job_boards = {"linkedin", "indeed", "jobstreet", "monster", "foundit", "shine", "careers", "jobs", "unknown company", "unknown"}
        if co.lower().strip() in job_boards:
            co = ""
            
        return job_t, co
    except Exception:
        return "", ""

def _apply_to_career_page(page, url: str) -> bool:
    """Navigate to a career page URL and attempt to apply using AI form filler"""
    logger.info(f"Processing: {url[:80]}…", SITE)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _human_delay(2, 4)

        # Check for Cloudflare / Access Denied block
        if is_block_page(page):
            logger.warn(f"Skipping {url[:60]}... — Access Denied / Cloudflare block page detected", SITE)
            return False

        # Extract company & job title from page
        page_title = page.title()
        
        # Try AI-powered title extraction first
        job_t, company = _ai_parse_job_and_company(page_title, url)

        # Fallback if AI fails
        if not job_t or not company:
            if " - " in page_title:
                parts = re.split(r'(?<!\d)\s*-\s*(?!\d)', page_title)
                job_t = job_t or parts[0].strip()
                company = company or (parts[1].strip() if len(parts) > 1 else "Unknown Company")
            elif " | " in page_title:
                parts = page_title.split(" | ")
                job_t = job_t or parts[0].strip()
                company = company or parts[-1].strip()
            else:
                job_t = job_t or "Software Engineer"
                company = company or _extract_company_from_url(url)
                
            if not company:
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

        # Tech stack pre-check: JD must mention .net or c# to save API time
        desc_lower = desc.lower()
        if not (any(k in desc_lower for k in [".net", "c#", "dotnet"])):
            logger.info(f"Skipping {company} — {job_t} (Job description does not mention .NET or C# keywords)", SITE)
            return False

        # Visa sponsorship detection — log prominently
        has_visa = _check_visa_sponsorship(desc + " " + page_title + " " + url)
        if has_visa:
            logger.info(f"🌟 VISA SPONSORSHIP DETECTED — {company} | {job_t}", SITE)
        else:
            logger.info(f"   No visa mention — {company} | {job_t} (proceeding anyway for profile match)", SITE)

        # Tailor resume
        tailor_result = tailor_resume(job_t, company, desc, site=SITE)
        resume_path   = tailor_result["resume_path"]
        match_score   = tailor_result["match_score"]

        if not resume_path:
            logger.info(f"Skipping {company} — {job_t} (Tech stack or experience mismatch)", SITE)
            return False

        if match_score < MIN_MATCH:
            logger.info(f"Skipping {company} — {job_t} (Match score {match_score}% < {MIN_MATCH}%)", SITE)
            return False

        # Use AI to fill all form fields intelligently including file/resume uploads
        success = fill_form_with_ai(page, site=SITE, resume_path=resume_path)

        # Interactive manual review — remind user they can type 'c' anytime
        visa_tag = " 🌟 VISA SPONSORSHIP" if has_visa else ""
        print("\n" + "*" * 70)
        print(f"ACTION REQUIRED (TAKE CONTROL):{visa_tag}")
        print(f"Form has been pre-filled for: {company} — {job_t}")
        print("Please review the browser page, fill any missing fields, and solve CAPTCHAs.")
        print("When you are done:")
        print("  - Press ENTER to let the bot submit the form and learn your answers.")
        print("  - Type 's' and press Enter to SKIP this application.")
        print("  - Type 'd' and press Enter if you manually clicked submit yourself.")
        print("*" * 70 + "\n")

        # Disconnect to allow manual action/CAPTCHA solving
        browser_manager.disconnect()
        user_choice = input("Your choice (Enter / s / d): ").strip().lower()
        browser_manager.reconnect()
        page = browser_manager.get_active_page()

        if user_choice == 's':
            logger.info(f"Skipped application for: {company} — {job_t}", SITE)
            return False

        # Learn from filled form AFTER manual review (capture user inputs)
        try:
            learn_from_filled_form(page, SITE)
        except Exception as e:
            logger.warn(f"Post-learning failed: {e}", SITE)

        if user_choice == 'd':
            logger.success(f"Manually submitted and recorded: {company} — {job_t}", SITE)
            record_application(
                site=SITE, company=company, role=job_t, location="Remote/Various",
                job_url=url, match_score=match_score, resume_used=resume_path,
            )
            git_sync()
            return True

        # Click submit button on behalf of user
        submit_btn = None
        for sel in [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Submit Application")', button_text_match("Submit Application"),
            'button:has-text("Apply")', 'button:has-text("Send Application")',
            'button:has-text("Submit")', '#submit_app'
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    submit_btn = el
                    break
            except Exception:
                continue

        if submit_btn:
            try:
                logger.info("Clicking submit button...", SITE)
                submit_btn.click()
                _human_delay(3, 5)
                logger.success(f"Submitted successfully: {company} — {job_t}", SITE)
            except Exception as e:
                logger.error(f"Failed to click submit button: {e}", SITE)
        else:
            logger.warn("Submit button not found. Assuming you clicked submit manually.", SITE)

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
    """Extracts company name from URL, handling subdomains, country codes, ATS domains, and LinkedIn job view URLs."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        
        # Special case: LinkedIn job view URLs
        if "linkedin.com" in domain:
            if "/jobs/view/" in path:
                path_parts = [p for p in path.split("/") if p]
                if path_parts:
                    last_part = path_parts[-1]
                    if "-at-" in last_part:
                        co_part = last_part.split("-at-")[-1]
                        co_part = re.sub(r'-\d+$', '', co_part)
                        co_name = co_part.replace("-", " ").replace("_", " ").strip()
                        if co_name:
                            return co_name.title()
            return "LinkedIn"

        # 1. Handle ATS domains where company is in path or subdomain
        if "lever.co" in domain:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].title()
        if "greenhouse.io" in domain:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].title()
        if "myworkdayjobs.com" in domain:
            parts = domain.split(".")
            if parts and parts[0] != "www":
                return parts[0].title()
                
        # 2. Strip common prefixes
        domain = domain.replace("www.", "").replace("careers.", "").replace("jobs.", "")
        
        # 3. Handle country codes (e.g. company.com.my, company.co.uk)
        parts = domain.split(".")
        if len(parts) >= 3 and parts[-2] in ["com", "co", "org", "net", "edu", "gov"]:
            return parts[-3].capitalize()
            
        if len(parts) >= 2:
            return parts[-2].capitalize()
            
        return parts[0].capitalize()
    except Exception:
        pass
    return "Unknown Company"
