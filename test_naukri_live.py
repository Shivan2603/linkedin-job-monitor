import os, sys
from playwright.sync_api import sync_playwright
from bot.utils.safety import safe_browser_context, load_cookies, save_cookies
from bot.config import CREDENTIALS
from bot.sites.naukri import _login, _apply_to_url

def test_live():
    creds = CREDENTIALS["naukri"]
    with sync_playwright() as p:
        context, browser = safe_browser_context(p, "naukri")
        page = context.new_page()
        
        # Login
        if not load_cookies(context, "naukri"):
            _login(page, creds)
            save_cookies(context, "naukri")
        else:
            page.goto("https://www.naukri.com", wait_until="domcontentloaded")
            if not page.query_selector(".nI-gNb-header__logo"):
                _login(page, creds)
                save_cookies(context, "naukri")
        
        print("Logged in successfully. Finding 2 test jobs...")
        
        # Test Search
        page.goto("https://www.naukri.com/senior-net-developer-jobs?k=Senior%20.NET%20Developer&l=Remote&experience=3,8", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except:
            pass
            
        urls = []
        links = page.query_selector_all("a.title")
        for link in links:
            href = link.get_attribute("href")
            if href and "job-listings" in href:
                if href.startswith("/"): href = "https://www.naukri.com" + href
                urls.append(href)
                
        easy_apply_url = None
        company_site_url = None
        
        for u in urls[:10]:
            page.goto(u, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass
                
            btn_text = ""
            for sel in ['button[class*="apply-button"]', 'button:has-text("Apply")', 'a:has-text("Apply")']:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    btn_text = loc.inner_text().lower()
                    break
                    
            if "company" in btn_text and not company_site_url:
                company_site_url = u
            elif "already" not in btn_text and "save" not in btn_text and not easy_apply_url and "apply" in btn_text:
                easy_apply_url = u
                
            if easy_apply_url and company_site_url:
                break
                
        print(f"Testing Easy Apply: {easy_apply_url}")
        if easy_apply_url:
            _apply_to_url(page, easy_apply_url, "Senior .NET Developer", "Remote")
            
        print(f"Testing Company Site Apply: {company_site_url}")
        if company_site_url:
            _apply_to_url(page, company_site_url, "Senior .NET Developer", "Remote")
            
        browser.close()

if __name__ == "__main__":
    test_live()
