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
    """
    user_data_dir = os.path.join(DATA_FOLDER, f"chrome_profile_{site}")
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Clean up stale lock files from crashed previous sessions (prevents Error Code 32)
    for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_path = os.path.join(user_data_dir, lock_file)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass
    
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--start-maximized",
        ],
        slow_mo=random.randint(30, 80),   # Slow down ALL actions slightly
        user_agent=random_user_agent(),
        viewport=random_viewport(),
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
    )
    
    # Remove navigator.webdriver flag
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        window.chrome = { runtime: {} };
    """)
    
    # Return context as both browser and context for backwards compatibility
    return context, context
