"""
bot/outreach_agent.py — Proactive Job-Hunt Outreach Agent
Searches for jobs, tailors resumes, looks up emails, sends cold emails, and tracks follow-ups.
"""
import os
import re
import json
import time
import urllib.parse
from datetime import datetime, timedelta
import pandas as pd
import requests
from playwright.sync_api import sync_playwright

from bot.config import DATA_FOLDER, TAILORED_TODAY, GROQ_API_KEY
from bot.utils import logger
from bot.utils.email_sender import send_cold_email
from bot.ai_resume import tailor_resume
from bot.ai_router import ai_complete

# File paths
TRACKER_JSON = os.path.join(DATA_FOLDER, "outreach_tracker.json")
TRACKER_XLSX = os.path.join(DATA_FOLDER, "outreach_tracker.xlsx")

# Max emails per day limit
MAX_EMAILS_PER_DAY = int(os.getenv("MAX_OUTREACH_EMAILS_PER_DAY", "20"))

# Candidate Details
CANDIDATE_NAME = "Siva Shankar V"
CANDIDATE_EMAIL = "sivashankar.avi6@gmail.com"
CANDIDATE_PHONE = "+91 6383149155"
CANDIDATE_PORTFOLIO = "https://shivan2603.github.io/sivashankar-portfolio/"
CANDIDATE_GITHUB = "https://github.com/shivan2603"

def load_tracker() -> list:
    if os.path.exists(TRACKER_JSON):
        try:
            with open(TRACKER_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading outreach tracker: {e}", "outreach")
    return []

def save_tracker(tracker: list):
    try:
        # Save JSON
        with open(TRACKER_JSON, "w", encoding="utf-8") as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
            
        # Sync with Excel using pandas
        if tracker:
            df = pd.DataFrame(tracker)
            # Reorder columns for readability
            cols_order = [
                "date", "company", "job_title", "location", "url", 
                "contact_name", "contact_role", "email", "status", 
                "follow_up_1_date", "follow_up_1_status",
                "follow_up_2_date", "follow_up_2_status", 
                "subject", "body", "resume_path"
            ]
            # Keep only existing columns
            cols_to_use = [c for c in cols_order if c in df.columns]
            df = df[cols_to_use]
            df.to_excel(TRACKER_XLSX, index=False)
            logger.info("Outreach tracker successfully synced to JSON and Excel.", "outreach")
    except Exception as e:
        logger.error(f"Error saving outreach tracker: {e}", "outreach")

def get_emails_sent_today() -> int:
    tracker = load_tracker()
    today_str = datetime.today().strftime("%Y-%m-%d")
    sent_today = 0
    for entry in tracker:
        if entry.get("date", "").startswith(today_str):
            if entry.get("status") in ["Sent", "Followed Up 1", "Followed Up 2"]:
                sent_today += 1
    return sent_today

# ─── SEARCH & SCRAPING MODULES ────────────────────────────────────────────────
def search_duckduckgo(query: str, max_results: int = 15) -> list:
    """Queries DuckDuckGo HTML search and returns list of organic links."""
    logger.info(f"Querying DuckDuckGo for: '{query}'", "outreach")
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    params = {"q": query}
    links = []
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            raw_links = re.findall(r'href=["\']([^"\']+)["\']', r.text)
            for href in raw_links:
                if "uddg=" in href:
                    parts = href.split("uddg=")
                    if len(parts) > 1:
                        actual_encoded = parts[1].split("&")[0]
                        actual_url = urllib.parse.unquote(actual_encoded)
                        if actual_url not in links and "duckduckgo" not in actual_url:
                            links.append(actual_url)
                elif href.startswith("http") and "duckduckgo" not in href:
                    if href not in links:
                        links.append(href)
        else:
            logger.warn(f"DuckDuckGo HTML requests failed with status code {r.status_code}. Retrying via Playwright...", "outreach")
            raise Exception("Blocked or non-200 status code")
    except Exception:
        # Fallback to Playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                page.goto(f"https://duckduckgo.com/?q={urllib.parse.quote(query)}")
                page.wait_for_timeout(5000)
                links_elements = page.locator("a").all()
                for el in links_elements:
                    try:
                        href = el.get_attribute("href")
                        if href and href.startswith("http") and "duckduckgo" not in href:
                            if href not in links:
                                links.append(href)
                    except Exception:
                        continue
                browser.close()
        except Exception as e:
            logger.error(f"Playwright DuckDuckGo search fallback failed: {e}", "outreach")
            
    return links[:max_results]

def get_job_urls() -> list:
    """Scours LinkedIn, Indeed, and WeWorkRemotely via DDG for matching job URLs."""
    queries = [
        'site:linkedin.com/jobs/view ".net" ("United Kingdom" OR "UK" OR "Europe" OR "Germany" OR "Australia" OR "Singapore" OR "Canada" OR "USA") -jobs-in-india',
        'site:indeed.com/viewjob ".net" ("United Kingdom" OR "UK" OR "Australia" OR "Singapore" OR "Canada" OR "USA") -india',
        'site:weworkremotely.com/remote-jobs ".net"',
        'site:remoteok.com ".net" developer'
    ]
    all_links = []
    tracker = load_tracker()
    already_processed_urls = {entry.get("url") for entry in tracker if entry.get("url")}
    
    for q in queries:
        links = search_duckduckgo(q)
        for link in links:
            # Normalize link
            clean_link = link.split("?")[0]
            if clean_link in already_processed_urls or link in already_processed_urls:
                continue
                
            is_valid_job_link = False
            if "linkedin.com/jobs/view" in link:
                is_valid_job_link = True
            elif "indeed.com/viewjob" in link:
                is_valid_job_link = True
            elif "weworkremotely.com/remote-jobs" in link:
                is_valid_job_link = True
            elif "remoteok.com/remote-jobs" in link or "remoteok.com/l/" in link:
                is_valid_job_link = True
                
            if is_valid_job_link and clean_link not in all_links:
                all_links.append(clean_link)
                
    logger.info(f"Discovered {len(all_links)} new potential job URLs.", "outreach")
    return all_links

def scrape_job_details(url: str) -> dict | None:
    """Uses Playwright to scrape job description, job title, and company name."""
    logger.info(f"Scraping job details from URL: {url}", "outreach")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            
            title = page.title()
            body_text = page.locator("body").inner_text()
            
            # Simple selectors to find Title and Company
            job_title = ""
            company_name = ""
            
            # Attempt to extract job title/company based on site structure
            if "linkedin.com" in url:
                # LinkedIn selectors
                try:
                    job_title = page.locator("h1").first.inner_text().strip()
                except Exception:
                    pass
                try:
                    # Look for company name link
                    company_name = page.locator(".topcard__org-name-link, .job-details-jobs-unified-top-card__company-name").first.inner_text().strip()
                except Exception:
                    pass
            elif "indeed.com" in url:
                try:
                    job_title = page.locator("h1").first.inner_text().strip()
                except Exception:
                    pass
                try:
                    company_name = page.locator("[data-company-name='true'], .jobsearch-CompanyInfoContainer").first.inner_text().strip()
                except Exception:
                    pass
            elif "weworkremotely.com" in url:
                try:
                    job_title = page.locator("h1").first.inner_text().strip()
                except Exception:
                    pass
                try:
                    company_name = page.locator(".company-card h2 a, .listing-header-container h2").first.inner_text().strip()
                except Exception:
                    pass
                    
            # Fallbacks using Page Title or AI
            if not job_title or not company_name:
                # Ask AI to extract from Title and body snippet
                prompt = f"Page Title: {title}\nURL: {url}\n\nExtract: 1. Job Title, 2. Company Name. Return as JSON: {{\"job_title\": \"...\", \"company_name\": \"...\"}}"
                try:
                    res_raw = ai_complete("You extract structured data from text. Return only raw JSON.", prompt, task="general", max_tokens=150)
                    for fence in ["```json", "```"]:
                        if fence in res_raw:
                            res_raw = res_raw.split(fence)[1].split("```")[0].strip()
                            break
                    res_json = json.loads(res_raw)
                    if not job_title:
                        job_title = res_json.get("job_title", "")
                    if not company_name:
                        company_name = res_json.get("company_name", "")
                except Exception:
                    pass
                    
            # Fallback to page title splits
            if not job_title:
                job_title = title.split(" hiring ")[0].split(" - ")[0].split(" | ")[0].strip()
            if not company_name:
                company_name = title.split(" at ")[-1].split(" hiring ")[-1].split(" - ")[-1].split(" | ")[-1].strip()
                
            # Clean up Company Name
            company_name = re.sub(r'\(.*?\)', '', company_name).strip()
            company_name = company_name.split(" is hiring")[0].split(" hiring")[0].strip()
            
            browser.close()
            
            # Simple programmatic check to verify it is a .NET Core / C# role
            jd_lower = body_text.lower()
            title_lower = job_title.lower()
            if ".net" not in jd_lower and "c#" not in jd_lower and "csharp" not in jd_lower and ".net" not in title_lower and "c#" not in title_lower:
                logger.info(f"Skipping {job_title} at {company_name} — Tech stack (.NET / C#) not found in JD.", "outreach")
                return None
                
            # Exclude India Onsite
            if "india" in jd_lower or "chennai" in jd_lower or "bangalore" in jd_lower or "mumbai" in jd_lower or "pune" in jd_lower:
                # If it mentions remote or hybrid, keep it. Otherwise skip.
                if "remote" not in jd_lower and "hybrid" not in jd_lower:
                    logger.info(f"Skipping {job_title} at {company_name} — India onsite role excluded.", "outreach")
                    return None
            
            return {
                "job_title": job_title,
                "company_name": company_name,
                "job_description": body_text[:6000],  # Truncate to avoid context limit
                "url": url
            }
    except Exception as e:
        logger.error(f"Error scraping job details from {url}: {e}", "outreach")
    return None

# ─── CONTACT LOOKUP MODULE ───────────────────────────────────────────────────
def extract_company_domain(company_name: str, job_url: str) -> str:
    """Finds company domain via job URL or DuckDuckGo search."""
    # Try parsing domain from job_url first if it's not a general job board
    parsed = urllib.parse.urlparse(job_url)
    netloc = parsed.netloc.lower()
    if not any(board in netloc for board in ["linkedin.com", "indeed.com", "weworkremotely.com", "remoteok.com", "glassdoor.com"]):
        domain = netloc.replace("www.", "")
        return domain
        
    # Query DDG
    query = f'"{company_name}" official website'
    links = search_duckduckgo(query, max_results=3)
    for link in links:
        link_parsed = urllib.parse.urlparse(link)
        link_netloc = link_parsed.netloc.lower()
        if not any(board in link_netloc for board in ["linkedin.com", "indeed.com", "weworkremotely.com", "remoteok.com", "glassdoor.com", "facebook.com", "twitter.com", "wikipedia.org"]):
            return link_netloc.replace("www.", "")
            
    # Fallback to simple slug
    slug = re.sub(r'[^a-zA-Z0-9]', '', company_name).lower()
    return f"{slug}.com"

def lookup_hiring_contact(company_name: str, domain: str) -> dict:
    """
    Finds a recruiter/CTO/Engineering Manager name & email for outreach.
    Returns: {"name": "...", "role": "...", "email": "...", "source": "..."}
    """
    logger.info(f"Searching hiring contact details for {company_name} ({domain})...", "outreach")
    
    # Query DDG for email mentions or people
    query = f'site:{domain} "email" OR "contact" OR "@{domain}"'
    snippets = []
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, params={"q": query}, timeout=10)
        if r.status_code == 200:
            snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', r.text, re.DOTALL)
    except Exception:
        pass
        
    # Search for names/roles of contacts
    people_query = f'"{company_name}" (CTO OR "Engineering Manager" OR Recruiter OR "Talent Acquisition")'
    people_snippets = []
    try:
        r = requests.get("https://html.duckduckgo.com/html/", headers={"User-Agent": "Mozilla/5.0"}, params={"q": people_query}, timeout=10)
        if r.status_code == 200:
            people_snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', r.text, re.DOTALL)
    except Exception:
        pass
        
    combined_context = "\n".join(snippets + people_snippets)
    
    # Ask AI to analyze snippets and find name, role, email
    system_prompt = "You are a lead generation intelligence agent. Find name, role, and email of the hiring contact."
    user_prompt = f"""Company: {company_name}
Domain: {domain}
Search Context:
{combined_context}

Analyze the search context. Extract the email address if present. Also identify the contact name and role (e.g. Recruiter, Engineering Manager, CTO).
If no specific email is found, return the best guessed email using standard patterns (e.g. first.last@{domain}, recruiting@{domain}, careers@{domain}) and specify "guessed" as the email_status.
Return JSON:
{{"contact_name": "...", "contact_role": "...", "email": "...", "email_status": "found/guessed"}}
Return ONLY raw JSON."""

    try:
        raw_res = ai_complete(system_prompt, user_prompt, task="general", max_tokens=250)
        for fence in ["```json", "```"]:
            if fence in raw_res:
                raw_res = raw_res.split(fence)[1].split("```")[0].strip()
                break
        res = json.loads(raw_res)
        email = res.get("email", "").strip().lower()
        if not email or "@" not in email:
            email = f"careers@{domain}"
            res["email"] = email
            res["email_status"] = "guessed"
        return {
            "name": res.get("contact_name", "Hiring Team"),
            "role": res.get("contact_role", "Recruiting & Engineering"),
            "email": email,
            "status": res.get("email_status", "guessed")
        }
    except Exception as e:
        logger.error(f"Failed to parse hiring contact via AI: {e}", "outreach")
        return {
            "name": "Hiring Team",
            "role": "Recruiting & Engineering",
            "email": f"careers@{domain}",
            "status": "guessed"
        }

# ─── COLD EMAIL DRAFTING ─────────────────────────────────────────────────────
def draft_cold_email(contact_name: str, job_title: str, company: str, job_description: str) -> tuple[str, str]:
    """Generates email subject and body using LLM (<150 words)."""
    system_prompt = "You are an expert cold outreach specialist. Write highly conversion-focused, short emails."
    user_prompt = f"""Draft a short, punchy cold email to a hiring contact.
Candidate: Siva Shankar V
Role: Senior Software Engineer (.NET Core / C# / Azure)
Notice Period: serving notice, last working day August 14th, 2026.
Primary tech: C#, .NET Core 8, ASP.NET Web API, Azure Cloud, Microservices, Clean Architecture, CQRS, Docker, SQL Server.
Certifications: Microsoft Azure Developer Associate (AZ-204).
Experience: 4+ years.
Target Job Title: {job_title}
Target Company: {company}
Hiring Contact Name: {contact_name}
Job Description: {job_description[:3000]}

Rules:
1. Under 150 words.
2. Direct, personalized opening hook referring to the specific job details or tech stack.
3. Call to Action: ask if they have 5 minutes for a brief chat this week.
4. Note that my tailored PDF resume is attached.
5. No placeholder brackets (like [Hiring Manager], [Company]). Output fully filled in text.
6. Provide output in this format:
Subject: [Subject Line]
---
[Email Body]
"""

    try:
        raw_email = ai_complete(system_prompt, user_prompt, task="general", max_tokens=400)
        subject = "Senior .NET Engineer Role"
        body = raw_email
        
        if "Subject:" in raw_email:
            parts = raw_email.split("Subject:")
            body_parts = parts[1].split("---")
            subject = body_parts[0].strip()
            if len(body_parts) > 1:
                body = "---".join(body_parts[1:]).strip()
            else:
                body = parts[1].strip()
                
        # Ensure signatures are clean
        if CANDIDATE_EMAIL not in body:
            body += f"\n\nBest regards,\n{CANDIDATE_NAME}\n{CANDIDATE_EMAIL} | {CANDIDATE_PHONE}\nPortfolio: {CANDIDATE_PORTFOLIO}\nGitHub: {CANDIDATE_GITHUB}"
            
        return subject, body
    except Exception as e:
        logger.error(f"Failed to draft cold email via AI: {e}", "outreach")
        subject = f"Senior .NET Engineer Application - Siva Shankar V"
        body = f"Hi {contact_name},\n\nI noticed you are hiring a {job_title} at {company} and wanted to reach out. I am a Senior Software Engineer with 4+ years of experience specializing in C#, .NET Core, Azure, Microservices, and Clean Architecture.\n\nI am currently serving my notice period with a last working day of August 14th, 2026, and hold the Microsoft Azure Developer Associate (AZ-204) certification. I have attached my tailored resume for your review.\n\nDo you have 5 minutes for a brief call this week?\n\nBest regards,\n{CANDIDATE_NAME}\n{CANDIDATE_EMAIL} | {CANDIDATE_PHONE}\nPortfolio: {CANDIDATE_PORTFOLIO}\nGitHub: {CANDIDATE_GITHUB}"
        return subject, body

# ─── FOLLOW-UP PROCESSING ────────────────────────────────────────────────────
def process_follow_ups():
    """Scans tracker for Sent outreach campaigns to follow up on Day 5 and Day 10."""
    logger.info("Scanning for follow-ups (Day 5 and Day 10)...", "outreach")
    tracker = load_tracker()
    updated = False
    today = datetime.today().date()
    
    for entry in tracker:
        # Check Follow-up 1 (Day 5)
        if entry.get("status") == "Sent" and entry.get("follow_up_1_date"):
            f1_date = datetime.strptime(entry["follow_up_1_date"], "%Y-%m-%d").date()
            if today >= f1_date and entry.get("follow_up_1_status") == "Pending":
                logger.info(f"Sending Follow-up 1 to {entry['email']} for {entry['company']}...", "outreach")
                subject = f"Follow-up: {entry['subject']}"
                body = f"Hi {entry['contact_name']},\n\nI hope you're having a great week.\n\nI wanted to follow up on my previous note regarding the {entry['job_title']} role at {entry['company']}. I would love to connect and share how my 4+ years of .NET Core, Microservices, and Azure experience can add value to your team.\n\nLet me know if you have 5 minutes for a chat.\n\nBest regards,\n{CANDIDATE_NAME}"
                
                success = send_cold_email(entry["email"], subject, body, entry.get("resume_path"))
                if success:
                    entry["follow_up_1_status"] = "Sent"
                    entry["status"] = "Followed Up 1"
                    updated = True
                    time.sleep(5)  # Cooldown between emails
                    
        # Check Follow-up 2 (Day 10)
        elif entry.get("status") == "Followed Up 1" and entry.get("follow_up_2_date"):
            f2_date = datetime.strptime(entry["follow_up_2_date"], "%Y-%m-%d").date()
            if today >= f2_date and entry.get("follow_up_2_status") == "Pending":
                logger.info(f"Sending Follow-up 2 to {entry['email']} for {entry['company']}...", "outreach")
                subject = f"Final check-in: {entry['subject']}"
                body = f"Hi {entry['contact_name']},\n\nI'm checking in one last time to see if you have any feedback on my profile for the {entry['job_title']} role. If not, no worries at all — I appreciate your time.\n\nHave a great rest of the week!\n\nBest regards,\n{CANDIDATE_NAME}"
                
                success = send_cold_email(entry["email"], subject, body, entry.get("resume_path"))
                if success:
                    entry["follow_up_2_status"] = "Sent"
                    entry["status"] = "Followed Up 2"
                    updated = True
                    time.sleep(5)  # Cooldown between emails
                    
    if updated:
        save_tracker(tracker)
    else:
        logger.info("No pending follow-ups found.", "outreach")

# ─── MAIN OUTREACH AGENT RUNNER ──────────────────────────────────────────────
def run_outreach_agent():
    logger.info("=" * 60, "outreach")
    logger.info("PROACTIVE JOB-HUNT COLD OUTREACH AGENT STARTING", "outreach")
    logger.info("=" * 60, "outreach")
    
    # 1. Check daily limit
    sent_today = get_emails_sent_today()
    logger.info(f"Emails sent today: {sent_today} / {MAX_EMAILS_PER_DAY}", "outreach")
    if sent_today >= MAX_EMAILS_PER_DAY:
        logger.warn(f"Daily limit of {MAX_EMAILS_PER_DAY} outreach emails reached. Skipping outreach run.", "outreach")
        return
        
    # 2. Process pending follow-ups first
    process_follow_ups()
    
    # Check limit again after follow-ups
    sent_today = get_emails_sent_today()
    if sent_today >= MAX_EMAILS_PER_DAY:
        logger.warn(f"Daily limit reached after sending follow-ups. Stopping.", "outreach")
        return
        
    # 3. Discover jobs
    job_urls = get_job_urls()
    if not job_urls:
        logger.info("No new job links discovered in this run.", "outreach")
        return
        
    tracker = load_tracker()
    
    for url in job_urls:
        if sent_today >= MAX_EMAILS_PER_DAY:
            logger.info(f"Daily limit of {MAX_EMAILS_PER_DAY} reached during loop. Stopping.", "outreach")
            break
            
        logger.info(f"Processing URL: {url}", "outreach")
        job = scrape_job_details(url)
        if not job:
            continue
            
        # Get company domain and lookup contact
        domain = extract_company_domain(job["company_name"], url)
        contact = lookup_hiring_contact(job["company_name"], domain)
        
        logger.info(f"Contact Found: {contact['name']} ({contact['role']}) - Email: {contact['email']} ({contact['status']})", "outreach")
        
        # Tailor Resume
        logger.info(f"Tailoring resume for {job['job_title']} at {job['company_name']}...", "outreach")
        tailored = tailor_resume(job["job_title"], job["company_name"], job["job_description"])
        resume_pdf_path = tailored.get("resume_pdf_path", "")
        
        if not resume_pdf_path or not os.path.exists(resume_pdf_path):
            logger.error("Failed to generate tailored resume PDF. Skipping outreach for this job.", "outreach")
            continue
            
        # Draft email
        subject, body = draft_cold_email(contact["name"], job["job_title"], job["company_name"], job["job_description"])
        
        # Send Cold Email
        logger.info(f"Sending outreach email to {contact['email']}...", "outreach")
        success = send_cold_email(contact["email"], subject, body, resume_pdf_path)
        
        # Track entry
        status = "Sent" if success else "Failed"
        today_str = datetime.today().strftime("%Y-%m-%d")
        f1_date = (datetime.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        f2_date = (datetime.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        
        new_entry = {
            "date": today_str,
            "company": job["company_name"],
            "job_title": job["job_title"],
            "location": "Remote / Relocation",
            "url": url,
            "contact_name": contact["name"],
            "contact_role": contact["role"],
            "email": contact["email"],
            "status": status,
            "follow_up_1_date": f1_date,
            "follow_up_1_status": "Pending" if success else "Failed",
            "follow_up_2_date": f2_date,
            "follow_up_2_status": "Pending" if success else "Failed",
            "subject": subject,
            "body": body,
            "resume_path": resume_pdf_path
        }
        
        tracker.append(new_entry)
        save_tracker(tracker)
        
        if success:
            sent_today += 1
            logger.info(f"Outreach successful. Today's count: {sent_today}", "outreach")
            # Human-like delay between outreach cycles
            time.sleep(random.randint(20, 45))
            
    logger.info("Proactive Cold Outreach Agent cycle completed.", "outreach")
