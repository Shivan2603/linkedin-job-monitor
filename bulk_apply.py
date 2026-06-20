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

def apply_to_url(page, url: str) -> bool:
    logger.info(f"\n==================================================", SITE)
    logger.info(f"Processing URL: {url}", SITE)
    logger.info(f"==================================================", SITE)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)

        # Get Page Title & Metadata
        page_title = page.title()
        job_title = ""
        company = ""

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

        # Fallback to page title parsing
        if not job_title or not company:
            if " - " in page_title:
                parts = page_title.split(" - ")
                job_title = job_title or parts[0].strip()
                company = company or (parts[1].strip() if len(parts) > 1 else "Unknown Company")
            elif " | " in page_title:
                parts = page_title.split(" | ")
                job_title = job_title or parts[0].strip()
                company = company or parts[-1].strip()
            else:
                job_title = job_title or "Software Engineer"
                company = company or "Company"
                
                # Extract company from URL as fallback
                m = re.search(r'lever\.co/([^/]+)', url)
                if m: company = m.group(1).title()
                else:
                    m = re.search(r'greenhouse\.io/([^/]+)', url)
                    if m: company = m.group(1).title()

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
