"""
bot/utils/logger.py — Logger backed by SQLite DB + JSON export + git sync
"""
import os, uuid, subprocess
from datetime import datetime
from bot.config import PROJECT_FOLDER
from bot.utils import db

def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'replace').decode())

def log(level: str, message: str, site: str = "system"):
    entry = {
        "id":      str(uuid.uuid4())[:8],
        "ts":      datetime.now().isoformat(),
        "level":   level.upper(),
        "site":    site,
        "message": message,
    }
    db.insert_log(entry)
    _safe_print(f"[{entry['ts'][11:19]}] [{level.upper():7s}] [{site}] {message}")
    return entry

def info(msg, site="system"):    return log("INFO",    msg, site)
def success(msg, site="system"): return log("SUCCESS", msg, site)
def warn(msg, site="system"):    return log("WARN",    msg, site)
def error(msg, site="system"):   return log("ERROR",   msg, site)
def ai(msg, site="ai"):          return log("AI",      msg, site)

def record_application(site, company, role, location, job_url,
                       match_score, resume_used, status="applied"):
    entry = {
        "id":          str(uuid.uuid4())[:10],
        "site":        site,
        "company":     company,
        "role":        role,
        "location":    location,
        "job_url":     job_url,
        "match_score": match_score,
        "resume_used": os.path.basename(resume_used),
        "status":      status,
        "applied_at":  datetime.now().isoformat(),
    }
    db.insert_application(entry)
    success(f"Applied: {company} | {role} | {location} | {match_score}% match", site)
    git_sync()
    return entry

def update_status(app_id: str, new_status: str):
    db.update_status(app_id, new_status)

def is_already_applied(site: str, company: str, role: str) -> bool:
    return db.is_already_applied(site, company, role)

def git_sync():
    """Push data files to GitHub so dashboard updates in real-time."""
    try:
        subprocess.run(["git", "add", "data/applications.json", "data/logs.json"],
                       cwd=PROJECT_FOLDER, capture_output=True, timeout=15)

        status = subprocess.run(["git", "status", "--porcelain", "data/"],
                                cwd=PROJECT_FOLDER, capture_output=True, text=True, timeout=10)
        if not status.stdout.strip():
            return

        msg = f"bot: sync {datetime.now().strftime('%Y-%m-%d %H:%M')} [skip ci]"
        subprocess.run(["git", "commit", "-m", msg],
                       cwd=PROJECT_FOLDER, capture_output=True, timeout=15)
        result = subprocess.run(["git", "push", "origin", "main"],
                                cwd=PROJECT_FOLDER, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            _safe_print("[git_sync] Pushed to GitHub")
        else:
            _safe_print(f"[git_sync] Push failed: {result.stderr[:100]}")
    except Exception as e:
        _safe_print(f"[git_sync] Error: {e}")
