from playwright.sync_api import sync_playwright
import time
from bot.config import CREDENTIALS
from bot.sites.naukri import _login

def run_test():
    creds = CREDENTIALS["naukri"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Login
        _login(page, creds)
        
        # Go to a search URL
        url = "https://www.naukri.com/senior-net-developer-jobs?k=Senior%20.NET%20Developer&l=Remote&experience=3,8"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        # Extract job urls
        urls = []
        links = page.query_selector_all("a.title")
        for link in links:
            href = link.get_attribute("href")
            if href and "job-listings" in href:
                if href.startswith("/"): href = "https://www.naukri.com" + href
                urls.append(href)
                
        print(f"Found {len(urls)} job URLs")
        
        easy_apply_url = None
        company_site_url = None
        
        for u in urls[:10]:
            print("Checking", u)
            page.goto(u, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except:
                pass
            
            btn_text = ""
            btn = None
            for sel in ['button[class*="apply-button"]', 'button:has-text("Apply")', 'a:has-text("Apply")']:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    btn_text = loc.inner_text().lower()
                    btn = loc
                    break
                    
            if btn:
                print("Found button:", btn_text)
                if "company site" in btn_text and not company_site_url:
                    company_site_url = u
                elif "already" not in btn_text and "save" not in btn_text and not easy_apply_url:
                    easy_apply_url = u
            else:
                print("No button found")
                
            if easy_apply_url and company_site_url:
                break
                
        print("Easy Apply URL:", easy_apply_url)
        print("Company Site URL:", company_site_url)
        browser.close()

if __name__ == "__main__":
    run_test()
