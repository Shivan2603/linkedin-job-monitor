import os
import sys
from urllib.parse import quote

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.sites.company_careers import _ai_generate_search_queries, _ai_generate_target_companies
from bot.ai_agent_filler import _load_workday_accounts
from bot.utils import logger
from playwright.sync_api import sync_playwright
from bot.utils.safety import safe_browser_context

def main():
    print("=" * 60)
    print("Testing Universal Career Bot Discovery & Setup")
    print("=" * 60)
    
    # 1. AI Search Queries
    print("\n--- Generating AI Search Queries ---")
    queries = _ai_generate_search_queries()
    print(f"Generated {len(queries)} queries:")
    for idx, q in enumerate(queries[:10]):
        print(f"  {idx + 1}: {q}")
        
    # 2. AI Target Companies
    print("\n--- Generating AI Target Companies ---")
    tcs = _ai_generate_target_companies()
    print(f"Generated {len(tcs)} target companies:")
    for idx, tc in enumerate(tcs):
        print(f"  {idx + 1}: {tc.get('company')} -> {tc.get('search_query')}")
        
    # 3. Workday account cache load
    print("\n--- Loading Workday Account Cache ---")
    accounts = _load_workday_accounts()
    print(f"Loaded {len(accounts)} cached Workday accounts:")
    for domain, email in accounts.items():
        print(f"  {domain} -> {email}")
        
    # 4. Search engine discovery test (run 1 query only to test Playwright and extraction)
    print("\n--- Running Link Extraction on Search Engine (1 Query) ---")
    if queries:
        test_query = queries[0]
        print(f"Test Query: {test_query}")
        
        with sync_playwright() as p:
            browser, context = safe_browser_context(p, "test")
            page = context.new_page()
            
            try:
                # We'll run the search and extract links for just this one query
                google_url = f"https://www.google.com/search?q={quote(test_query)}&num=10"
                print(f"Navigating to Google Search: {google_url}")
                page.goto(google_url, wait_until="domcontentloaded", timeout=20000)
                
                # Extract using evaluation script
                links = page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('a[href]');
                        return Array.from(els).map(el => {
                            const href = el.href;
                            try {
                                const url = new URL(href);
                                const host = url.hostname.toLowerCase();
                                const path = url.pathname.toLowerCase();
                                
                                const blacklist = [
                                    'google.', 'youtube.', 'github.', 'facebook.', 'twitter.', 'x.com', 'instagram.', 'pinterest.',
                                    'linkedin.com', 'indeed.com', 'glassdoor.', 'naukri.com', 'monster.com', 'foundit.', 'shine.com',
                                    'jooble.', 'jobstreet.', 'seek.com', 'simplyhired', 'ziprecruiter', 'careerbuilder',
                                    'talent.com', 'neuvoo', 'upwork', 'fiverr', 'freelancer', 'ambitionbox', 'levels.fyi',
                                    'duckduckgo.com', 'bing.com', 'yahoo.com', 'wikipedia.org', 'support.google'
                                ];
                                if (blacklist.some(domain => host.includes(domain))) return null;
                                
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
                apply_links = list(set([l for l in links if "/apply" in l or "job" in l.lower() or "career" in l.lower()]))
                print(f"Extracted {len(apply_links)} matching job links:")
                for idx, l in enumerate(apply_links[:10]):
                    print(f"  {idx + 1}: {l}")
            except Exception as e:
                print(f"Error during search engine test: {e}")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
                
    print("\nTest completed successfully!")

if __name__ == "__main__":
    main()
