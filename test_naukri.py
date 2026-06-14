from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto('https://www.naukri.com/senior-net-developer-jobs?k=Senior%20.NET%20Developer&l=Remote')
    page.wait_for_timeout(5000)
    cards = page.query_selector_all('.srp-jobtuple-wrapper')
    if cards:
        with context.expect_page() as new_page_info:
            cards[0].click()
        new_page = new_page_info.value
        new_page.wait_for_load_state()
        print('New page URL:', new_page.url)
        print('New page Title:', new_page.title())
        for s in ['button[class*="apply-button"]', '#apply-button']:
            print(s, bool(new_page.query_selector(s)))
    browser.close()
