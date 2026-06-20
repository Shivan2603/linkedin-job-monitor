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

from bot.config import TAILORED_TODAY
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
    ("indeed",          "Indeed Multi-Country", run_indeed_bot),
    ("shine",           "Shine",           run_shine_bot),
    ("monster",         "Foundit",         run_monster_bot),
    ("jobstreet",       "JobStreet",       run_jobstreet_bot),
    ("jooble",          "Jooble",          run_jooble_bot),
]

def run_all_sites():
    logger.info("=" * 60)
    logger.info(f"Job Bot Session Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Tailored resumes: {TAILORED_TODAY}")
    logger.info("=" * 60)

    stats = get_daily_stats()
    logger.info(f"Today's applications so far: {stats}")

    # Shuffle the bots list to randomize execution order on each run cycle
    shuffled_bots = list(SITE_BOTS)
    random.shuffle(shuffled_bots)

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
    logger.info("Job Bot Starting — Safe Mode Active")
    logger.info("Daily limits: LinkedIn=25, Naukri=40, Indeed=30, Shine=50, Monster=50, JobStreet=30, Jooble=30")
    logger.info("Anti-ban: random delays, cookie persistence, stealth browser")

    run_all_sites()

    # Randomize cycle time (60–90 min) to avoid pattern detection
    while True:
        wait_mins = random.randint(60, 90)
        logger.info(f"Next cycle in {wait_mins} minutes...")
        time.sleep(wait_mins * 60)
        run_all_sites()

if __name__ == "__main__":
    main()
