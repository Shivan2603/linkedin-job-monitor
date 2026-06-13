"""
main.py — Master orchestrator for the Job Application Bot
Runs all site bots sequentially within the 12 AM – 11 PM window
Loops continuously throughout the day applying to new jobs
"""
import time
import schedule
import sys, os
from datetime import datetime

# Allow importing from bot package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import BOT_START_HOUR, BOT_END_HOUR, TAILORED_TODAY
from bot.utils import logger

# Site bots
from bot.sites.linkedin import run_linkedin_bot
from bot.sites.naukri   import run_naukri_bot
from bot.sites.indeed   import run_indeed_bot
from bot.sites.shine    import run_shine_bot
from bot.sites.monster  import run_monster_bot
from bot.sites.company_careers import run_company_careers_bot

SITE_BOTS = [
    ("LinkedIn",      run_linkedin_bot),
    ("Naukri",        run_naukri_bot),
    ("Indeed India",  run_indeed_bot),
    ("Shine",         run_shine_bot),
    ("Monster India", run_monster_bot),
    ("Company Careers", run_company_careers_bot),
]

def run_all_sites():
    """Run all configured job site bots"""

    logger.info("=" * 60)
    logger.info(f"🤖 Job Bot Session Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"📁 Tailored resumes → {TAILORED_TODAY}")
    logger.info("=" * 60)

    for site_name, bot_fn in SITE_BOTS:
        logger.info(f"--- Starting {site_name} ---")
        try:
            bot_fn()
        except Exception as e:
            logger.error(f"{site_name} failed with error: {e}")
        logger.info(f"--- {site_name} done ---")
        time.sleep(10)  # Brief pause between sites

    logger.info("✅ All site bots completed for this cycle.")
    logger.info("💤 Waiting 60 minutes before next cycle...")

def main():
    logger.info("🚀 Job Bot Scheduler Starting...")
    logger.info("📅 Active window: 24/7 Continuous Mode")
    logger.info("♾️  Application limit: UNLIMITED")

    # Run immediately on start
    run_all_sites()

    # Then run every 60 minutes
    schedule.every(60).minutes.do(run_all_sites)

    logger.info("⏰ Scheduler running. Bot will cycle every 60 minutes.")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main()
