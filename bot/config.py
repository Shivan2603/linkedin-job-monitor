"""
config.py — Central configuration and credential loader
All settings pulled from .env file
"""
import os
from datetime import date
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─── PATHS ────────────────────────────────────────────────
RESUME_FOLDER       = os.getenv("RESUME_FOLDER", r"E:\SivaShankar\Resume")
TAILORED_BASE       = os.getenv("TAILORED_FOLDER_BASE", r"E:\SivaShankar\aTresume")
PROJECT_FOLDER      = os.getenv("PROJECT_FOLDER", r"E:\SivaShankar\jobbot")
DATA_FOLDER         = os.getenv("DATA_FOLDER", r"E:\SivaShankar\jobbot\data")

# Today's tailored resume folder — created fresh each day
TODAY_STR           = date.today().strftime("%d-%m-%Y")
TAILORED_TODAY      = os.path.join(TAILORED_BASE, TODAY_STR)

# ─── BASE RESUME ──────────────────────────────────────────
# Always use the most recent resume as the base
BASE_RESUME_DOCX    = os.path.join(RESUME_FOLDER, "Siva_Shankar_Resume_6062026.docx")

# ─── AI PROVIDERS (All FREE) ───────────────────────────
# Groq  (primary): https://console.groq.com
GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL_PRIMARY   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")   # Resume tailoring
GROQ_MODEL_FAST      = os.getenv("GROQ_MODEL_FAST", "llama-3.1-8b-instant") # Form filling (fast)

# HuggingFace (ATS checker): https://huggingface.co/settings/tokens
HUGGINGFACE_TOKEN    = os.getenv("HUGGINGFACE_TOKEN", "")

# Google Gemini (fallback): https://aistudio.google.com/app/apikey
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL         = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

# Legacy aliases
ANTHROPIC_API_KEY    = GROQ_API_KEY
CLAUDE_MODEL         = GROQ_MODEL_PRIMARY

# ─── JOB SEARCH ───────────────────────────────────────────
JOB_TITLES = [t.strip() for t in os.getenv(
    "JOB_TITLES",
    "Software Engineer,Full Stack Developer,.NET Developer,Java Developer,Python Developer,React Developer"
).split(",")]

LOCATIONS = [l.strip() for l in os.getenv(
    "LOCATIONS",
    "Remote,Bangalore,Chennai,Hyderabad,UK,Australia,Malaysia,Singapore"
).split(",")]

EXPERIENCE_YEARS = int(os.getenv("EXPERIENCE_YEARS", "2"))

# ─── BOT SCHEDULE ─────────────────────────────────────────
BOT_START_HOUR      = int(os.getenv("BOT_START_HOUR", "0"))    # 12 AM
BOT_END_HOUR        = int(os.getenv("BOT_END_HOUR", "23"))     # 11 PM
MAX_JOBS_PER_SITE   = int(os.getenv("MAX_JOBS_PER_SITE", "500"))
APPLY_DELAY_SECONDS = int(os.getenv("APPLY_DELAY_SECONDS", "8"))
ONLY_LINKEDIN       = os.getenv("ONLY_LINKEDIN", "True").strip().lower() == "true"

# ─── CREDENTIALS ──────────────────────────────────────────
def _get_cred(key, is_pass=False):
    env_key = f"{key.upper()}_PASSWORD" if is_pass else f"{key.upper()}_EMAIL"
    val = os.getenv(env_key, "").strip()
    if not val:
        fallback_env = "LINKEDIN_PASSWORD" if is_pass else "LINKEDIN_EMAIL"
        val = os.getenv(fallback_env, "").strip()
    return val

CREDENTIALS = {
    "linkedin": {
        "email":    _get_cred("linkedin"),
        "password": _get_cred("linkedin", True),
    },
    "naukri": {
        "email":    _get_cred("naukri"),
        "password": _get_cred("naukri", True),
    },
    "indeed": {
        "email":    _get_cred("indeed"),
        "password": _get_cred("indeed", True),
    },
    "shine": {
        "email":    _get_cred("shine"),
        "password": _get_cred("shine", True),
    },
    "monster": {
        "email":    _get_cred("monster"),
        "password": _get_cred("monster", True),
    },
    "jobstreet": {
        "email":    _get_cred("jobstreet"),
        "password": _get_cred("jobstreet", True),
    },
    "jooble": {
        "email":    _get_cred("jooble"),
        "password": _get_cred("jooble", True),
    },
}

# ─── ENSURE FOLDERS EXIST ─────────────────────────────────
os.makedirs(TAILORED_TODAY, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)
