"""
main.py — Master orchestrator for the Job Application Bot
Safe mode: daily limits, site cooldowns, human-like pacing
"""
import time, random, sys, os
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import TAILORED_TODAY, BOT_START_HOUR, BOT_END_HOUR, ONLY_LINKEDIN
from bot.utils import logger
from bot.utils.safety import site_cooldown, get_daily_stats, check_daily_limit

# Site bots
from bot.sites.linkedin        import run_linkedin_bot
from bot.sites.naukri          import run_naukri_bot
from bot.sites.indeed          import run_indeed_bot
from bot.sites.shine           import run_shine_bot
from bot.sites.monster         import run_monster_bot
from bot.sites.company_careers import run_company_careers_bot
from bot.sites.jobstreet       import run_jobstreet_bot
from bot.sites.jooble          import run_jooble_bot

SITE_BOTS = [
    ("linkedin",        "LinkedIn",        run_linkedin_bot),
    ("company_careers", "Company Careers", run_company_careers_bot),
    ("naukri",          "Naukri",          run_naukri_bot),
    ("indeed",          "Indeed Multi-Country", lambda: run_indeed_bot(interactive=False)),
    ("shine",           "Shine",           run_shine_bot),
    ("monster",         "Foundit",         run_monster_bot),
    ("jobstreet",       "JobStreet",       run_jobstreet_bot),
    ("jooble",          "Jooble",          run_jooble_bot),
]

def is_in_running_window() -> bool:
    now = datetime.now()
    hour = now.hour
    return BOT_START_HOUR <= hour < BOT_END_HOUR

def wait_for_running_window():
    first_msg = True
    while not is_in_running_window():
        now = datetime.now()
        if first_msg:
            logger.info(f"Current time ({now.strftime('%H:%M:%S')}) is outside the running window ({BOT_START_HOUR}:00 - {BOT_END_HOUR}:00). Sleeping until active...")
            first_msg = False
        time.sleep(300) # Check every 5 minutes

def run_all_sites():
    wait_for_running_window()
    
    logger.info("=" * 60)
    logger.info(f"Job Bot Session Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Tailored resumes: {TAILORED_TODAY}")
    logger.info("=" * 60)

    stats = get_daily_stats()
    logger.info(f"Today's applications so far: {stats}")

    if ONLY_LINKEDIN:
        shuffled_bots = [b for b in SITE_BOTS if b[0] == "linkedin"]
        logger.info("Filtering run for LinkedIn ONLY per configuration.")
    else:
        # Careers page first, LinkedIn second, then other sites shuffled
        careers_bot = [b for b in SITE_BOTS if b[0] == "company_careers"]
        linkedin_bot = [b for b in SITE_BOTS if b[0] == "linkedin"]
        others = [b for b in SITE_BOTS if b[0] not in ["company_careers", "linkedin"]]
        
        random.shuffle(others)
        shuffled_bots = careers_bot + linkedin_bot + others
        
        order_names = [b[1] for b in shuffled_bots]
        logger.info(f"Execution order for this cycle: {', '.join(order_names)}")

    first_site = True
    for site_key, site_name, bot_fn in shuffled_bots:
        if not check_daily_limit(site_key):
            logger.info(f"Skipping {site_name} — daily limit reached", site_key)
            continue

        if not first_site:
            site_cooldown()   # 30–90 sec random pause between sites
        first_site = False

        logger.info(f"--- Starting {site_name} ---")
        try:
            bot_fn()
        except Exception as e:
            logger.error(f"{site_name} crashed: {e}")
        logger.info(f"--- {site_name} done ---")

    logger.info("All sites completed for this cycle.")
    stats = get_daily_stats()
    logger.info(f"Today's total applications: {stats}")
    logger.info("Waiting 60-90 minutes before next cycle...")

def main():
    cli_choice = None
    if len(sys.argv) > 1:
        cli_choice = sys.argv[1].strip()
        logger.info(f"Command-line argument provided: mode={cli_choice}", "main")
    elif not sys.stdin.isatty():
        cli_choice = "4"  # Default to All Sites continuous cycle loop in background
        logger.info("Non-interactive terminal detected. Defaulting to All Sites loop (mode 4).", "main")

    while True:
        if cli_choice:
            choice = cli_choice
            cli_choice = None
        else:
            print("\n" + "=" * 65)
            print("           JCODE — UNIVERSAL JOB APPLICATION BOT")
            print("=" * 65)
            print("  JOB SITE BOTS:")
            print("  1. LinkedIn Bot       (Easy Apply + Freelance + External Links)")
            print("  2. Careers/Bulk Bot   (Processes bulk_urls.txt interactively)")
            print("  3. Indeed Bot         (Multi-Country automation)")
            print("  4. All Sites Cycle    (Careers → LinkedIn → Others, shuffled)")
            print("")
            print("  AGENTS:")
            print("  5. Cold Outreach Agent (24/7 Job Finder + Cold Emailer)")
            print("  7. ★ Build Hiring Package (Resume + Cover Letter + Interview Prep)")
            print("     → Paste any JD → Get 3 tailored documents in seconds")
            print("  8. ★ Follow-Up Email Agent (Auto-send 7-day follow-ups)")
            print("")
            print("  6. Exit")
            print("=" * 65 + "\n")

            try:
                choice = input("Select an option (1-8): ").strip()
            except (KeyboardInterrupt, SystemExit):
                print("\nExiting.")
                break
            except EOFError:
                logger.info("EOF on stdin. Exiting menu loop.", "main")
                break

        if choice == "1":
            logger.info("Running LinkedIn Bot only...", "main")
            try:
                from bot.sites.linkedin import run_linkedin_bot
                run_linkedin_bot()
            except Exception as e:
                logger.error(f"LinkedIn Bot error: {e}", "main")
            if not sys.stdin.isatty():
                break
                
        elif choice == "2":
            logger.info("Running Careers Bot (Bulk Apply)...", "main")
            try:
                from bulk_apply import main as run_bulk_apply
                run_bulk_apply()
            except Exception as e:
                logger.error(f"Careers Bot error: {e}", "main")
            if not sys.stdin.isatty():
                break
            
        elif choice == "3":
            logger.info("Running Indeed Bot only...", "main")
            try:
                from bot.sites.indeed import run_indeed_bot
                run_indeed_bot()
            except Exception as e:
                logger.error(f"Indeed Bot error: {e}", "main")
            if not sys.stdin.isatty():
                break
                
        elif choice == "4":
            logger.info("Starting All Sites standard loop...", "main")
            logger.info("Anti-ban: random delays, cookie persistence, stealth browser", "main")
            logger.info(f"Time window restriction active: {BOT_START_HOUR}:00 to {BOT_END_HOUR}:00", "main")
            
            try:
                run_all_sites()
                
                # Cycle wait loop
                while True:
                    wait_mins = random.randint(60, 90)
                    logger.info(f"Next cycle in {wait_mins} minutes...", "main")
                    slept = 0
                    while slept < wait_mins * 60:
                        time.sleep(300)
                        slept += 300
                    run_all_sites()
            except (KeyboardInterrupt, SystemExit):
                logger.info("All Sites cycle interrupted by user.", "main")
                break
            except EOFError:
                logger.info("EOF in cycle loop. Exiting.", "main")
                break
                
        elif choice == "5":
            logger.info("Running Proactive Cold Outreach Agent...", "main")
            try:
                from bot.outreach_agent import run_outreach_agent
                run_outreach_agent()
            except Exception as e:
                logger.error(f"Outreach Agent error: {e}", "main")
            if not sys.stdin.isatty():
                break

        elif choice == "7":
            # ══ BUILD FULL HIRING PACKAGE ══════════════════════════════
            print("\n" + "=" * 65)
            print("  ★  JCODE HIRING PACKAGE BUILDER")
            print("  Generates: Resume + Cover Letter + Interview Prep Sheet")
            print("=" * 65)
            try:
                company   = input("\n  Company name: ").strip()
                job_title = input("  Job title:   ").strip()
                print("\n  Paste the full Job Description below.")
                print("  When done, type END on a new line and press Enter:\n")
                jd_lines = []
                while True:
                    line = input()
                    if line.strip().upper() == "END":
                        break
                    jd_lines.append(line)
                jd_text = "\n".join(jd_lines).strip()

                if not company or not job_title or not jd_text:
                    print("  [!] Company, job title, and JD text are all required.")
                else:
                    print(f"\n  Building hiring package for: {job_title} @ {company}")
                    print("  Running 14-agent pipeline... (this takes ~2-3 minutes)\n")
                    from bot.ai_resume import tailor_resume
                    result = tailor_resume(
                        job_title=job_title,
                        company=company,
                        job_description=jd_text
                    )
                    print("\n" + "=" * 65)
                    print("  ★  HIRING PACKAGE READY!")
                    print("=" * 65)
                    resume_path = result.get("resume_path", "")
                    cl_path     = result.get("cover_letter_path", "")
                    ip_path     = result.get("interview_prep_path", "")
                    score       = result.get("match_score", "N/A")
                    print(f"  ATS Score:       {score}%")
                    print(f"  Resume:          {resume_path}")
                    print(f"  Cover Letter:    {cl_path if cl_path else 'N/A'}")
                    print(f"  Interview Prep:  {ip_path if ip_path else 'N/A'}")
                    # Show why-hire if available
                    why_hire = result.get("tailored", {}).get("top_5_why_hire", [])
                    if why_hire:
                        print("\n  TOP 5 REASONS TO HIRE SIVA FOR THIS ROLE:")
                        for i, pt in enumerate(why_hire[:5], 1):
                            print(f"    {i}. {pt}")
                    print("=" * 65 + "\n")
            except (KeyboardInterrupt, SystemExit):
                print("\n  Hiring package builder cancelled.")
            except Exception as e:
                logger.error(f"Hiring Package Builder error: {e}", "main")
            if not sys.stdin.isatty():
                break

        elif choice == "6":
            print("Exiting.")
            break

        elif choice == "8":
            logger.info("Running Follow-Up Email Agent...", "main")
            try:
                from bot.followup_email_agent import run_followup_agent
                run_followup_agent()
            except Exception as e:
                logger.error(f"Follow-Up Agent error: {e}", "main")
            if not sys.stdin.isatty():
                break

        else:
            print("Invalid selection. Please choose 1-8.")


if __name__ == "__main__":
    main()
