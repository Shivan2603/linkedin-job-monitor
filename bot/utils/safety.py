"""
bot/utils/safety.py — Anti-ban & Human Behaviour Simulation
Protects the bot from getting flagged or banned on job sites.

Key measures:
  1. Random human-like delays (not fixed timers)
  2. Realistic mouse movements + scrolling before clicks
  3. Human typing speed (char by char)
  4. Daily application limits per site
  5. Cookie persistence (avoid re-login every run)
  6. Session cooldowns between sites
  7. Random user-agent rotation
  8. Viewport jitter
"""
import time, random, os, json
from datetime import date
from playwright.sync_api import Page
from bot.config import DATA_FOLDER
from bot.utils import logger

# ─── DAILY LIMITS (safe thresholds per site) ─────────────────────────────────
DAILY_LIMITS = {
    "linkedin":       25,   # LinkedIn flags >30 Easy Apply/day
    "naukri":         40,
    "indeed":         30,
    "shine":          50,
    "monster":        50,
    "company_careers": 60,
    "jobstreet":      30,
    "jooble":         30,
}

DAILY_COUNT_FILE = os.path.join(DATA_FOLDER, "daily_counts.json")

def _load_counts() -> dict:
    today = str(date.today())
    if os.path.exists(DAILY_COUNT_FILE):
        try:
            data = json.load(open(DAILY_COUNT_FILE))
            if data.get("date") == today:
                return data
        except Exception:
            pass
    return {"date": today}

def _save_counts(counts: dict):
    with open(DAILY_COUNT_FILE, "w") as f:
        json.dump(counts, f)

def check_daily_limit(site: str) -> bool:
    """Returns True if we are still under the daily limit for this site."""
    counts = _load_counts()
    used = counts.get(site, 0)
    limit = DAILY_LIMITS.get(site, 30)
    if used >= limit:
        logger.warn(f"Daily limit reached for {site} ({used}/{limit}). Skipping for today.", site)
        return False
    return True

def increment_daily_count(site: str):
    counts = _load_counts()
    counts[site] = counts.get(site, 0) + 1
    _save_counts(counts)

def get_daily_stats() -> dict:
    counts = _load_counts()
    return {s: counts.get(s, 0) for s in DAILY_LIMITS}

# ─── HUMAN DELAYS ────────────────────────────────────────────────────────────
def short_delay():
    """0.5 – 1.5 seconds — between small actions"""
    time.sleep(random.uniform(0.5, 1.5))

def medium_delay():
    """2 – 5 seconds — after page loads"""
    time.sleep(random.uniform(2.0, 5.0))

def long_delay():
    """8 – 20 seconds — between job applications"""
    time.sleep(random.uniform(8.0, 20.0))

def site_cooldown():
    """30 – 90 seconds — between different job sites"""
    secs = random.uniform(30, 90)
    logger.info(f"Site cooldown: {secs:.0f}s before next site...", "safety")
    time.sleep(secs)

def think_delay():
    """0.3 – 0.8 seconds — simulates human reading/thinking"""
    time.sleep(random.uniform(0.3, 0.8))

# ─── HUMAN TYPING ────────────────────────────────────────────────────────────
def human_type(page: Page, selector: str, text: str):
    """Type text character by character at human speed."""
    try:
        el = page.locator(selector).first
        el.click()
        time.sleep(random.uniform(0.3, 0.6))
        for char in text:
            el.press(char)
            time.sleep(random.uniform(0.05, 0.18))  # 50–180ms per character
    except Exception:
        # Fallback to normal fill
        try:
            page.fill(selector, text)
        except Exception:
            pass

# ─── HUMAN MOUSE BEHAVIOUR ───────────────────────────────────────────────────
def human_scroll(page: Page, direction: str = "down", amount: int = None):
    """Scroll like a human — variable speed and distance."""
    if amount is None:
        amount = random.randint(200, 600)
    if direction == "up":
        amount = -amount
    page.mouse.wheel(0, amount)
    time.sleep(random.uniform(0.3, 0.8))

def human_click(page: Page, selector: str):
    """
    Click with slight position randomness + pre-scroll into view.
    Mimics a human moving mouse to an element.
    """
    try:
        el = page.locator(selector).first
        el.scroll_into_view_if_needed()
        time.sleep(random.uniform(0.2, 0.5))
        box = el.bounding_box()
        if box:
            # Click slightly off-center (humans don't click pixel-perfect)
            x = box["x"] + box["width"]  * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            page.mouse.move(x, y, steps=random.randint(5, 15))
            time.sleep(random.uniform(0.1, 0.3))
            page.mouse.click(x, y)
        else:
            el.click()
    except Exception:
        try:
            page.click(selector)
        except Exception:
            pass

# ─── COOKIE PERSISTENCE ───────────────────────────────────────────────────────
COOKIE_DIR = os.path.join(DATA_FOLDER, "cookies")
os.makedirs(COOKIE_DIR, exist_ok=True)

def save_cookies(context, site: str):
    """Save browser cookies to disk so next run doesn't need to re-login."""
    try:
        cookies = context.cookies()
        path = os.path.join(COOKIE_DIR, f"{site}_cookies.json")
        with open(path, "w") as f:
            json.dump(cookies, f)
        logger.info(f"Cookies saved for {site}", site)
    except Exception as e:
        logger.warn(f"Could not save cookies for {site}: {e}", site)

def load_cookies(context, site: str) -> bool:
    """Load saved cookies. Returns True if cookies were loaded."""
    try:
        path = os.path.join(COOKIE_DIR, f"{site}_cookies.json")
        if not os.path.exists(path):
            return False
        with open(path) as f:
            cookies = json.load(f)
        # Only load non-expired cookies
        valid = [c for c in cookies if not c.get("expires") or c["expires"] > time.time()]
        if valid:
            context.add_cookies(valid)
            logger.info(f"Loaded {len(valid)} saved cookies for {site}", site)
            return True
    except Exception as e:
        logger.warn(f"Could not load cookies for {site}: {e}", site)
    return False

# ─── RANDOM USER AGENTS ──────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

def random_user_agent() -> str:
    return random.choice(USER_AGENTS)

# ─── RANDOM VIEWPORT ─────────────────────────────────────────────────────────
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]

def random_viewport() -> dict:
    vp = random.choice(VIEWPORTS)
    # Add slight jitter
    return {
        "width":  vp["width"]  + random.randint(-10, 10),
        "height": vp["height"] + random.randint(-5, 5),
    }

# ─── BROWSER CONTEXT HELPER ─────────────────────────────────────────────────
def safe_browser_context(playwright, site: str):
    """
    Launch a stealth persistent browser context.
    Using a persistent profile retains Gmail/LinkedIn logins permanently!
    headless=False + slow_mo=150 -> each action is visible field-by-field.
    """
    # Use a shared Chrome profile for all main sites (retaining active Google SSO / LinkedIn sessions globally)
    if site in ["indeed", "naukri", "monster", "jobstreet", "jooble", "linkedin", "shine"]:
        profile_name = "chrome_profile_shared"
    else:
        profile_name = f"chrome_profile_{site}"
        
    user_data_dir = os.path.join(DATA_FOLDER, profile_name)
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Clean up stale lock files from crashed previous sessions (prevents Error Code 32)
    for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_path = os.path.join(user_data_dir, lock_file)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass
    
    launch_kwargs = {
        "user_data_dir": user_data_dir,
        "headless": False,
        "slow_mo": 150,
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--start-maximized",
            "--window-position=0,0",
        ],
        "viewport": {"width": 1600, "height": 900},
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "extra_http_headers": {"Accept-Language": "en-IN,en;q=0.9"},
    }

    if site != "company_careers":
        launch_kwargs["channel"] = "chrome"  # Use official Google Chrome for main job boards

    context = playwright.chromium.launch_persistent_context(**launch_kwargs)
    
    # Remove navigator.webdriver flag
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        window.chrome = { runtime: {} };
    """)
    
    # Return context as both browser and context for backwards compatibility
    return context, context


# ─── VISIBLE FIELD-BY-FIELD LOGGER ──────────────────────────────────────────
def field_log(action: str, field_name: str, value: str = "", site: str = "bot"):
    """
    Print every form field action to the console with clear markers.
    This lets the user watch what the bot is filling in real time.
    """
    val_display = f"'{value[:60]}...'" if len(value) > 60 else f"'{value}'"
    icons = {
        "fill":     "✏️  FILL   ",
        "select":   "🔽 SELECT ",
        "click":    "🖱️  CLICK  ",
        "check":    "☑️  CHECK  ",
        "upload":   "📎 UPLOAD ",
        "skip":     "⏭️  SKIP   ",
        "found":    "🔍 FOUND  ",
        "submit":   "🚀 SUBMIT ",
        "success":  "✅ SUCCESS",
        "error":    "❌ ERROR  ",
        "step":     "📋 STEP   ",
        "nav":      "➡️  NEXT   ",
    }
    icon = icons.get(action, "•  ")
    if value:
        print(f"  [{site.upper()}] {icon} | {field_name:35s} = {val_display}")
    else:
        print(f"  [{site.upper()}] {icon} | {field_name}")


# ─── HUMAN FILL (visible, character-by-character) ────────────────────────────
def human_fill(el, value: str, field_name: str = "", site: str = "bot"):
    """
    Fill a field character-by-character at human typing speed.
    Clears existing value first, then types each character visibly.
    """
    try:
        el.triple_click()          # Select all existing text
        time.sleep(0.15)
        el.fill("")                # Clear
        time.sleep(0.1)
        # Type char by char for visibility
        for char in value:
            el.press(char)
            time.sleep(random.uniform(0.04, 0.12))
        field_log("fill", field_name or "input", value, site)
    except Exception:
        try:
            el.fill(value)
            field_log("fill", field_name or "input", value, site)
        except Exception:
            field_log("error", f"Could not fill: {field_name}", "", site)


# ─── GOOGLE SSO LOGIN FLOW ──────────────────────────────────────────────────
def handle_google_sso(auth_page, email: str, password: str) -> bool:
    """
    Handles Google SSO flow on the given Playwright page (could be a popup or redirect page).
    """
    logger.info(f"Handling Google SSO on page: {auth_page.url}", "safety")
    
    # Wait up to 12 seconds for either the email field, account picker, or email text to be visible
    start_time = time.time()
    selector_type = None  # 'email_input' or 'account_picker'
    target_locator = None
    
    while time.time() - start_time < 12:
        # Check for email inputs first
        for sel in ['input[name="identifier"]', 'input[type="email"]']:
            try:
                loc = auth_page.locator(sel).first
                if loc.is_visible():
                    selector_type = 'email_input'
                    target_locator = loc
                    break
            except Exception:
                pass
        if selector_type:
            break
            
        # Check for account pickers
        for sel in [f'[data-email="{email}"]', f'[data-identifier="{email}"]', 'div.auth-select-account', '#profileIdentifier']:
            try:
                loc = auth_page.locator(sel).first
                if loc.is_visible():
                    selector_type = 'account_picker'
                    target_locator = loc
                    break
            except Exception:
                pass
        if selector_type:
            break
            
        # Check for direct email text
        try:
            loc = auth_page.locator(f'text={email}').first
            if loc.is_visible():
                selector_type = 'account_picker'
                target_locator = loc
                break
        except Exception:
            pass
            
        time.sleep(0.5)

    if not selector_type:
        logger.warn("Timeout waiting for Google login selectors. Taking diagnostic screenshot.", "safety")
        try:
            auth_page.screenshot(path="data/google_sso_error.png")
            logger.info("Saved Google SSO error screenshot to data/google_sso_error.png", "safety")
        except Exception as se:
            logger.error(f"Failed to take Google SSO error screenshot: {se}", "safety")
        return False

    clicked = False
    if selector_type == 'account_picker' and target_locator:
        try:
            logger.info("Google SSO: Account picker detected. Clicking account...", "safety")
            target_locator.click()
            clicked = True
            time.sleep(3)
        except Exception as e:
            logger.error(f"Failed to click Google account picker: {e}", "safety")

    elif selector_type == 'email_input' and target_locator:
        try:
            logger.info("Google SSO: Email input field detected. Entering email...", "safety")
            human_fill(target_locator, email, "Google Email", "safety")
            time.sleep(1)
            next_btn = auth_page.locator('#identifierNext, button:has-text("Next"), button:has-text("Next step")').first
            if next_btn.is_visible():
                next_btn.click()
            else:
                target_locator.press("Enter")
            clicked = True
            time.sleep(3)
        except Exception as e:
            logger.error(f"Failed to fill email or click Next: {e}", "safety")

    # Now check if password input is visible (either after email click or picker click)
    # Wait for password input if it appears
    try:
        pass_input = auth_page.locator('input[type="password"]').first
        if pass_input.is_visible():
            logger.info("Google SSO: Entering password...", "safety")
            human_fill(pass_input, password, "Google Password", "safety")
            time.sleep(1)
            next_btn2 = auth_page.locator('#passwordNext, button:has-text("Next"), button:has-text("Next step")').first
            if next_btn2.is_visible():
                next_btn2.click()
            else:
                pass_input.press("Enter")
            time.sleep(3)
    except Exception:
        pass

    # Check if there is a confirmation/submit/allow button to consent
    try:
        consent_btn = auth_page.locator('button:has-text("Continue"), button:has-text("Confirm"), button:has-text("Allow")').first
        if consent_btn.is_visible():
            logger.info("Google SSO: Clicking consent/continue button...", "safety")
            consent_btn.click()
            time.sleep(3)
    except Exception:
        pass

    try:
        auth_page.screenshot(path="data/google_sso_final.png")
        logger.info("Saved final Google SSO screenshot to data/google_sso_final.png", "safety")
    except Exception as e:
        logger.warn(f"Failed to take final Google SSO screenshot: {e}", "safety")

    return True
