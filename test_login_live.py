import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, r"E:\SivaShankar\jobbot")

from playwright.sync_api import sync_playwright
from bot.utils.safety import safe_browser_context
from bot.config import CREDENTIALS
from bot.utils import logger

def test_indeed_login():
    logger.info("--- Testing Indeed Login ---", "test")
    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "indeed")
        page = context.new_page()
        try:
            from bot.sites.indeed import _ensure_logged_in
            success = _ensure_logged_in(page, "https://in.indeed.com")
            page.screenshot(path="indeed_test_result.png")
            logger.info(f"Indeed Login Test Success: {success}", "test")
            logger.info(f"Indeed Final URL: {page.url}", "test")
        except Exception as e:
            logger.error(f"Indeed Login Test Exception: {e}", "test")
        finally:
            browser.close()

def test_foundit_login():
    logger.info("--- Testing Foundit Login ---", "test")
    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "monster")
        page = context.new_page()
        try:
            from bot.sites.monster import _login_portal
            success = _login_portal(page, CREDENTIALS["monster"], "https://www.foundit.in")
            page.screenshot(path="foundit_test_result.png")
            logger.info(f"Foundit Login Test Success: {success}", "test")
            logger.info(f"Foundit Final URL: {page.url}", "test")
        except Exception as e:
            logger.error(f"Foundit Login Test Exception: {e}", "test")
        finally:
            browser.close()

def test_jobstreet_login():
    logger.info("--- Testing JobStreet Login ---", "test")
    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "jobstreet")
        page = context.new_page()
        try:
            from bot.sites.jobstreet import _login_portal
            success = _login_portal(page, CREDENTIALS["jobstreet"], "https://www.jobstreet.com.sg")
            page.screenshot(path="jobstreet_test_result.png")
            logger.info(f"JobStreet Login Test Success: {success}", "test")
            logger.info(f"JobStreet Final URL: {page.url}", "test")
        except Exception as e:
            logger.error(f"JobStreet Login Test Exception: {e}", "test")
        finally:
            browser.close()

def test_shine_login():
    logger.info("--- Testing Shine Login ---", "test")
    with sync_playwright() as p:
        browser, context = safe_browser_context(p, "shine")
        page = context.new_page()
        try:
            from bot.sites.shine import _login_portal
            success = _login_portal(page, CREDENTIALS["shine"])
            page.screenshot(path="shine_test_result.png")
            logger.info(f"Shine Login Test Success: {success}", "test")
            logger.info(f"Shine Final URL: {page.url}", "test")
        except Exception as e:
            logger.error(f"Shine Login Test Exception: {e}", "test")
        finally:
            browser.close()

if __name__ == "__main__":
    test_indeed_login()
    test_foundit_login()
    test_jobstreet_login()
    test_shine_login()
