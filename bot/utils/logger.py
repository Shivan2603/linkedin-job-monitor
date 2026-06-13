"""
utils/logger.py — Structured logger that writes to data/logs.json
                  and data/applications.json for the monitoring dashboard.
                  git_sync() pushes updates to GitHub so the live dashboard
                  at https://shivan2603.github.io/linkedin-job-monitor reflects
                  real-time metrics immediately after every application.
"""
import json, os, uuid, subprocess
from datetime import datetime
from bot.config import DATA_FOLDER, PROJECT_FOLDER

LOGS_FILE = os.path.join(DATA_FOLDER, "logs.json")
APPS_FILE = os.path.join(DATA_FOLDER, "applications.json")

def _load(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

# ─── LOG ──────────────────────────────────────────────────
def log(level: str, message: str, site: str = "system"):
    """Append a log entry. level = INFO | SUCCESS | WARN | ERROR | AI"""
    entry = {
        "id":      str(uuid.uuid4())[:8],
        "ts":      datetime.now().isoformat(),
        "level":   level.upper(),
        "site":    site,
        "message": message,
    }
    logs = _load(LOGS_FILE)
    logs.append(entry)
    # Keep last 2000 entries
    if len(logs) > 2000:
        logs = logs[-2000:]
    _save(LOGS_FILE, logs)
    # Also print to console
    print(f"[{entry['ts'][:19]}] [{level.upper():7s}] [{site}] {message}")
    return entry

def info(msg, site="system"):    return log("INFO",    msg, site)
def success(msg, site="system"): return log("SUCCESS", msg, site)
def warn(msg, site="system"):    return log("WARN",    msg, site)
def error(msg, site="system"):   return log("ERROR",   msg, site)
def ai(msg, site="ai"):          return log("AI",      msg, site)

# ─── APPLICATION RECORD ───────────────────────────────────
def record_application(
    site: str,
    company: str,
    role: str,
    location: str,
    job_url: str,
    match_score: int,
    resume_used: str,
    status: str = "applied"
):
    """Save a successful application to applications.json"""
    entry = {
        "id":           str(uuid.uuid4())[:10],
        "site":         site,
        "company":      company,
        "role":         role,
        "location":     location,
        "job_url":      job_url,
        "match_score":  match_score,
        "resume_used":  os.path.basename(resume_used),
        "status":       status,
        "applied_at":   datetime.now().isoformat(),
    }
    apps = _load(APPS_FILE)
    apps.insert(0, entry)
    _save(APPS_FILE, apps)
    success(f"✅ Applied → {company} | {role} | {location} | {match_score}% match", site)
    return entry

def update_status(app_id: str, new_status: str):
    """Update application status (e.g. 'viewed', 'shortlisted', 'callback')"""
    apps = _load(APPS_FILE)
    for app in apps:
        if app["id"] == app_id:
            app["status"] = new_status
            app["updated_at"] = datetime.now().isoformat()
            break
    _save(APPS_FILE, apps)

def is_already_applied(site: str, company: str, role: str) -> bool:
    """Check if we already applied to this company & role on this site"""
    apps = _load(APPS_FILE)
    for app in apps:
        if (app.get("site") == site
                and app.get("company", "").lower() == company.lower()
                and app.get("role", "").lower() == role.lower()):
            return True
    return False

def git_sync():
    """
    Sync data files to GitHub so the live dashboard updates in real-time.
    Runs after every successful application submission.
    Uses git add → commit → push (non-blocking, suppresses output).
    """
    try:
        data_dir = os.path.join(PROJECT_FOLDER, "data")

        # Stage both data files
        subprocess.run(
            ["git", "add", "data/applications.json", "data/logs.json"],
            cwd=PROJECT_FOLDER, capture_output=True, check=False, timeout=15
        )

        # Check if there are actually changes to commit
        status = subprocess.run(
            ["git", "status", "--porcelain", "data/"],
            cwd=PROJECT_FOLDER, capture_output=True, text=True, timeout=10
        )

        if not status.stdout.strip():
            return  # Nothing to commit

        # Commit with timestamp
        commit_msg = f"bot: update metrics {datetime.now().strftime('%Y-%m-%d %H:%M')} [skip ci]"
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=PROJECT_FOLDER, capture_output=True, timeout=15
        )

        # Push to main branch
        push_result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=PROJECT_FOLDER, capture_output=True, text=True, timeout=30
        )

        if push_result.returncode == 0:
            print(f"[git_sync] ✅ Pushed metrics to GitHub")
        else:
            print(f"[git_sync] ⚠️  Push failed: {push_result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        print("[git_sync] ⏱️  Git push timed out — will retry next application")
    except FileNotFoundError:
        print("[git_sync] ⚠️  git not found in PATH — install git and re-run setup_247.ps1")
    except Exception as e:
        print(f"[git_sync] ❌ Unexpected error: {e}")
