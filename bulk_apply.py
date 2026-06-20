import os
import sys
import time
import re
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.ai_resume import tailor_resume
from bot.ai_agent_filler import fill_form_with_ai
from bot.utils.learning import learn_from_filled_form
from bot.utils import logger
from bot.utils.logger import record_application, is_already_applied, git_sync
from bot.utils.safety import safe_browser_context

SITE = "company_careers"
BULK_FILE = r"E:\SivaShankar\jobbot\data\bulk_urls.txt"

def load_bulk_urls() -> list:
    """Reads URLs from the bulk file. Creates the file if it doesn't exist."""
    if not os.path.exists(BULK_FILE):
        os.makedirs(os.path.dirname(BULK_FILE), exist_ok=True)
        with open(BULK_FILE, "w", encoding="utf-8") as f:
            f.write("# Paste job URLs here (one per line). Lines starting with # are ignored.\n")
            f.write("# Example:\n# https://jobs.lever.co/company/job-id\n")
        logger.info(f"Created empty bulk URLs file at: {BULK_FILE}", SITE)
        return []
        
    urls = []
    with open(BULK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls

def remove_url_from_file(url: str):
    """Removes the processed URL from the text file so the user can see remaining tasks."""
    if not os.path.exists(BULK_FILE):
        return
    with open(BULK_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    with open(BULK_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip() != url:
                f.write(line)

def is_block_page(page) -> bool:
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

def _extract_company_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        
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
        return data.get("job_title", "").strip(), data.get("company", "").strip()
    except Exception:
        return "", ""

def apply_to_url(page, url: str) -> bool:
    logger.info(f"\n==================================================", SITE)
    logger.info(f"Processing URL: {url}", SITE)
    logger.info(f"==================================================", SITE)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)

        # Check for Cloudflare / Access Denied block
        if is_block_page(page):
            logger.warn(f"Skipping {url[:60]}... — Access Denied / Cloudflare block page detected", SITE)
            remove_url_from_file(url)
            return False

        # Get Page Title & Metadata
        page_title = page.title()
        
        # Try AI-powered title extraction first
        job_title, company = _ai_parse_job_and_company(page_title, url)

        # Fallback to page title parsing if AI failed
        if not job_title or not company:
            if "jobstreet" in url.lower():
                # Extract job title using JobStreet selectors
                for sel in ['[data-automation="job-detail-title"]', 'h1[data-automation="job-title"]', 'h1']:
                    el = page.query_selector(sel)
                    if el:
                        job_title = el.inner_text().strip()
                        if job_title:
                            break
                # Extract company name using JobStreet selectors
                for sel in ['[data-automation="advertiser-name"]', 'span[data-automation="company-name"]', '.company-name']:
                    el = page.query_selector(sel)
                    if el:
                        company = el.inner_text().strip()
                        if company:
                            break

            if not job_title or not company:
                if " - " in page_title:
                    parts = page_title.split(" - ")
                    job_title = job_title or parts[0].strip()
                    company = company or (parts[1].strip() if len(parts) > 1 else "")
                elif " | " in page_title:
                    parts = page_title.split(" | ")
                    job_title = job_title or parts[0].strip()
                    company = company or parts[-1].strip()
                else:
                    job_title = job_title or "Software Engineer"
                    company = company or _extract_company_from_url(url)
                    
                if not company:
                    company = _extract_company_from_url(url)

        # Clean job title (remove location keywords)
        job_title = re.sub(r'\s+', ' ', job_title).strip()
        job_title = re.sub(r'\b(Job\s+)?in\s+.*$', '', job_title, flags=re.IGNORECASE).strip()
        job_title = re.sub(r'\b(Johor|Selangor|Kuala Lumpur|Shah Alam|Subang|Bangalore|Chennai|Remote|Singapore|Malaysia|India).*$', '', job_title, flags=re.IGNORECASE).strip()
        job_title = re.sub(r'[\s\-,\/\|\(\)]+$', '', job_title).strip()

        # Clean company (remove tags, details)
        company = company.split("Careers")[0].split("Jobs")[0].strip()

        # Check job description
        job_desc = ""
        try:
            desc_el = page.query_selector(".job-description, .description, #job-description, main, body")
            job_desc = desc_el.inner_text()[:4000] if desc_el else ""
        except Exception:
            pass

        logger.info(f"Detected Company: {company} | Job Title: {job_title}", SITE)

        if is_already_applied(SITE, company, job_title):
            logger.info(f"Already applied to {company} — {job_title}. Skipping...", SITE)
            remove_url_from_file(url)
            return False

        # Tailor resume on the fly
        logger.info(f"Tailoring resume for {company} — {job_title}...", SITE)
        tailor_result = tailor_resume(job_title, company, job_desc, site=SITE)
        resume_path = tailor_result["resume_path"]

        # Fill the form using AI (which handles resume upload automatically)
        logger.info("Filling form fields and uploading resume via AI...", SITE)
        fill_form_with_ai(page, site=SITE, resume_path=resume_path)
        time.sleep(2)

        # Learn from filled form BEFORE manual intervention
        try:
            learn_from_filled_form(page, SITE)
        except Exception as e:
            logger.warn(f"Pre-learning failed: {e}", SITE)

        # Interactive manual review
        print("\n" + "*" * 70)
        print("ACTION REQUIRED:")
        print(f"Form has been pre-filled for: {company} — {job_title}")
        print("Please review the browser page, fill any missing fields, and solve CAPTCHAs.")
        print("When you are done:")
        print("  - Press ENTER to let the bot submit the form and learn your answers.")
        print("  - Type 's' and press Enter to SKIP this application.")
        print("  - Type 'd' and press Enter if you manually clicked submit yourself.")
        print("*" * 70 + "\n")

        user_choice = input("Your choice (Enter / s / d): ").strip().lower()

        if user_choice == 's':
            logger.info(f"Skipped application for: {company} — {job_title}", SITE)
            remove_url_from_file(url)
            return False

        # Learn from filled form AFTER manual review (capture user inputs)
        try:
            learn_from_filled_form(page, SITE)
        except Exception as e:
            logger.warn(f"Post-learning failed: {e}", SITE)

        if user_choice == 'd':
            logger.success(f"Manually submitted and recorded: {company} — {job_title}", SITE)
            record_application(
                site=SITE, company=company, role=job_title, location="Remote/Various",
                job_url=url, match_score=tailor_result["match_score"], resume_used=resume_path
            )
            git_sync()
            remove_url_from_file(url)
            return True

        # Click submit button on behalf of user
        submit_btn = page.query_selector(
            'button[type="submit"], input[type="submit"], '
            '#submit_app, button:has-text("Submit"), button:has-text("Apply"), '
            'button:has-text("Send Application")'
        )
        if submit_btn:
            try:
                logger.info("Clicking submit button...", SITE)
                submit_btn.click()
                time.sleep(5)
                logger.success(f"Submitted successfully: {company} — {job_title}", SITE)
                record_application(
                    site=SITE, company=company, role=job_title, location="Remote/Various",
                    job_url=url, match_score=tailor_result["match_score"], resume_used=resume_path
                )
                git_sync()
                remove_url_from_file(url)
                return True
            except Exception as e:
                logger.error(f"Failed to click submit button: {e}", SITE)
        else:
            logger.warn("Submit button not found. Assuming you clicked submit manually.", SITE)
            record_application(
                site=SITE, company=company, role=job_title, location="Remote/Various",
                job_url=url, match_score=tailor_result["match_score"], resume_used=resume_path
            )
            git_sync()
            remove_url_from_file(url)
            return True

    except Exception as e:
        logger.error(f"Failed to process {url[:60]}: {e}", SITE)

    return False

def main():
    print("=" * 60)
    print("  Universal Job Bot - BULK APPLY MODE")
    print("=" * 60)
    
    urls = load_bulk_urls()
    if not urls:
        print(f"\nNo URLs found in {BULK_FILE}!")
        print("Please paste the target job URLs into that file (one per line) and run again.\n")
        input("Press ENTER to exit...")
        return

    print(f"Loaded {len(urls)} job URLs to process.")
    print("Starting Playwright Chromium session...")
    
    with sync_playwright() as p:
        browser, context = safe_browser_context(p, SITE)
        page = context.pages[0] if context.pages else context.new_page()

        applied = 0
        for url in list(urls): # copy list to iterate safely
            if apply_to_url(page, url):
                applied += 1
            time.sleep(2)

        try:
            browser.close()
        except Exception:
            pass

        logger.success(f"\nFinished session! Applied to {applied}/{len(urls)} jobs.", SITE)
        print("\nAll URLs in this batch have been processed!")
        input("Press ENTER to exit...")

if __name__ == "__main__":
    main()
