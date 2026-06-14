"""
bot/utils/db.py — SQLite database for persistent application tracking
Replaces JSON files as primary store. JSON files are exported from DB for dashboard.
"""
import sqlite3, os, json
from datetime import datetime
from bot.config import DATA_FOLDER

DB_PATH   = os.path.join(DATA_FOLDER, "jobbot.db")
APPS_JSON = os.path.join(DATA_FOLDER, "applications.json")
LOGS_JSON = os.path.join(DATA_FOLDER, "logs.json")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id          TEXT PRIMARY KEY,
                site        TEXT,
                company     TEXT,
                role        TEXT,
                location    TEXT,
                job_url     TEXT,
                match_score INTEGER,
                resume_used TEXT,
                status      TEXT DEFAULT 'applied',
                applied_at  TEXT,
                updated_at  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id      TEXT PRIMARY KEY,
                ts      TEXT,
                level   TEXT,
                site    TEXT,
                message TEXT
            )
        """)
        conn.commit()

def insert_application(app: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO applications
            (id, site, company, role, location, job_url, match_score, resume_used, status, applied_at)
            VALUES (:id,:site,:company,:role,:location,:job_url,:match_score,:resume_used,:status,:applied_at)
        """, app)
        conn.commit()
    export_to_json()

def insert_log(entry: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO logs (id, ts, level, site, message)
            VALUES (:id,:ts,:level,:site,:message)
        """, entry)
        conn.commit()
    # Export logs JSON (only last 500)
    _export_logs_json()

def is_already_applied(site: str, company: str, role: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT 1 FROM applications
            WHERE LOWER(site)=LOWER(?) AND LOWER(company)=LOWER(?) AND LOWER(role)=LOWER(?)
        """, (site, company, role)).fetchone()
        return row is not None

def update_status(app_id: str, new_status: str):
    with get_conn() as conn:
        conn.execute("""
            UPDATE applications SET status=?, updated_at=? WHERE id=?
        """, (new_status, datetime.now().isoformat(), app_id))
        conn.commit()
    export_to_json()

def get_all_applications() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY applied_at DESC").fetchall()
        return [dict(r) for r in rows]

def export_to_json():
    """Export DB → applications.json for the GitHub Pages dashboard."""
    apps = get_all_applications()
    with open(APPS_JSON, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2, ensure_ascii=False, default=str)

def _export_logs_json():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM logs ORDER BY ts DESC LIMIT 500").fetchall()
        logs = [dict(r) for r in rows]
    with open(LOGS_JSON, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False, default=str)

# Auto-init on import
init_db()
