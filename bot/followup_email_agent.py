"""
followup_email_agent.py — Automated Follow-Up Email System
════════════════════════════════════════════════════════════
Sends a polite, professional follow-up email 7 days after applying.
Studies show: candidates who follow up are 3x more likely to get a response.

Flow:
  1. Reads the application log (data/applications.json)
  2. Finds applications made 7 days ago with no status update
  3. Generates a personalized follow-up email for each
  4. Sends via Gmail SMTP (same as outreach agent)
  5. Marks the application as "followed_up" in the log
"""

import os, json, smtplib, time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bot.ai_router import ai_complete
from bot.utils import logger

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
try:
    from bot.config import GMAIL_USER, GMAIL_APP_PASSWORD
except ImportError:
    GMAIL_USER = os.getenv("GMAIL_USER", "")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

APPLICATIONS_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "applications.json")
FOLLOWUP_AFTER_DAYS = 7

FOLLOWUP_SYSTEM = """You are the Follow-Up Email Agent. Write a brief, professional follow-up email
for a job application that was submitted 7 days ago with no response.

FOLLOW-UP EMAIL RULES:
1. Subject: "Following Up: {job_title} Application — Siva Shankar V"
2. Keep it SHORT — 4-5 sentences maximum. Recruiters are busy.
3. DO NOT sound desperate or apologetic
4. Reference ONE specific thing about the company (use company_domain to infer)
5. Reinforce the top differentiator (the hardest to replicate skill)
6. Clear CTA: invite them to share any update or schedule a quick call
7. Professional sign-off with phone number

TONE: Confident, brief, professional. Like a follow-up from a busy senior engineer,
not a desperate job seeker.

Return ONLY valid JSON:
{
  "subject": "Following Up: [job_title] Application — Siva Shankar V",
  "body": "Dear [Hiring Team / specific name if known],\\n\\n[4-5 sentences]\\n\\nBest regards,\\nSiva Shankar V\\n+91 6383149155\\nsivashankar.avi6@gmail.com"
}"""


def load_applications() -> list:
    """Load the applications log."""
    try:
        if os.path.exists(APPLICATIONS_LOG):
            with open(APPLICATIONS_LOG, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"[FollowUp] Failed to load applications log: {e}")
    return []


def save_applications(apps: list):
    """Save updated applications log."""
    try:
        os.makedirs(os.path.dirname(APPLICATIONS_LOG), exist_ok=True)
        with open(APPLICATIONS_LOG, "w", encoding="utf-8") as f:
            json.dump(apps, f, indent=2)
    except Exception as e:
        logger.error(f"[FollowUp] Failed to save applications log: {e}")


def log_application(job_title: str, company: str, job_url: str = "",
                    hr_email: str = "", jd_context: dict = None):
    """
    Call this after every application to log it for follow-up tracking.
    Call from tailor_resume() or the job site bots.
    """
    apps = load_applications()
    entry = {
        "job_title":   job_title,
        "company":     company,
        "job_url":     job_url,
        "hr_email":    hr_email,
        "applied_at":  datetime.now().isoformat(),
        "status":      "applied",
        "followed_up": False,
        "company_domain": (jd_context or {}).get("company_domain", "technology")
    }
    apps.append(entry)
    save_applications(apps)
    logger.info(f"[FollowUp] Logged application: {job_title} @ {company}")


def generate_followup_email(app: dict, parse_json_safely=None) -> dict:
    """Generate a personalized follow-up email for one application."""
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    try:
        prompt = (
            f"Job Title: {app['job_title']}\n"
            f"Company: {app['company']}\n"
            f"Company Domain: {app.get('company_domain', 'technology')}\n"
            f"Applied: {app['applied_at'][:10]}\n"
            f"Days since applied: {FOLLOWUP_AFTER_DAYS}\n\n"
            f"Write a brief 4-5 sentence follow-up email. Reference that we applied "
            f"{FOLLOWUP_AFTER_DAYS} days ago and are still very interested. "
            f"Mention one specific strength relevant to their domain."
        )
        raw = ai_complete(FOLLOWUP_SYSTEM, prompt, task="tailor", max_tokens=400)
        return parse_json_safely(raw)
    except Exception as e:
        # Fallback template
        return {
            "subject": f"Following Up: {app['job_title']} Application — Siva Shankar V",
            "body": (
                f"Dear Hiring Team,\n\n"
                f"I wanted to follow up on my application for the {app['job_title']} role at {app['company']}, "
                f"submitted {FOLLOWUP_AFTER_DAYS} days ago. I remain very excited about this opportunity "
                f"and believe my experience building cloud-native .NET microservices at enterprise scale — "
                f"most recently delivering 12+ production services at 99.98% uptime for Deloitte — "
                f"aligns closely with what your team is looking for.\n\n"
                f"Please let me know if you need any additional information or would like to schedule a call. "
                f"I'm available immediately and serving my notice period (LWD: 14th August 2026).\n\n"
                f"Best regards,\n"
                f"Siva Shankar V\n"
                f"+91 6383149155\n"
                f"sivashankar.avi6@gmail.com"
            )
        }


def send_followup_email(to_email: str, subject: str, body: str) -> bool:
    """Send a follow-up email via Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or "PASTE" in GMAIL_APP_PASSWORD:
        logger.warning("[FollowUp] Gmail credentials not configured. Skipping send.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, to_email, msg.as_string())

        logger.info(f"[FollowUp] Sent follow-up to {to_email}")
        return True
    except Exception as e:
        logger.error(f"[FollowUp] Email send failed: {e}")
        return False


def run_followup_agent():
    """
    Main entry point. Run this daily (or on startup) to auto-send
    follow-up emails for applications 7+ days old with no response.
    """
    apps = load_applications()
    cutoff_date = datetime.now() - timedelta(days=FOLLOWUP_AFTER_DAYS)
    updated = False

    print(f"\n[FollowUp] Checking {len(apps)} logged applications...")

    for i, app in enumerate(apps):
        # Skip if already followed up or has a status update
        if app.get("followed_up") or app.get("status") not in ["applied"]:
            continue

        # Check if old enough
        try:
            applied_dt = datetime.fromisoformat(app["applied_at"])
        except Exception:
            continue

        if applied_dt > cutoff_date:
            days_left = (applied_dt + timedelta(days=FOLLOWUP_AFTER_DAYS) - datetime.now()).days
            print(f"  ⏳ {app['job_title']} @ {app['company']} — follow-up in {days_left} day(s)")
            continue

        # Time to follow up!
        hr_email = app.get("hr_email", "").strip()
        company  = app["company"]
        jt       = app["job_title"]

        print(f"\n  📧 Follow-up due: {jt} @ {company} (applied {applied_dt.strftime('%d %b')})")

        email_data = generate_followup_email(app)
        subject = email_data.get("subject", f"Following Up: {jt} Application")
        body    = email_data.get("body", "")

        if hr_email:
            sent = send_followup_email(hr_email, subject, body)
            apps[i]["followed_up"] = True
            apps[i]["followup_sent_at"] = datetime.now().isoformat()
            apps[i]["followup_result"] = "sent" if sent else "failed"
            updated = True
            print(f"  ✅ Follow-up {'sent' if sent else 'FAILED (email error)'} to {hr_email}")
        else:
            # No email — print the draft for manual send
            print(f"\n  ⚠️  No HR email on file. Draft follow-up for {company}:")
            print(f"  Subject: {subject}")
            print(f"  ---\n{body}\n  ---")
            apps[i]["followed_up"] = True
            apps[i]["followup_result"] = "manual_required"
            updated = True

        time.sleep(2)  # Brief pause between emails

    if updated:
        save_applications(apps)

    print(f"\n[FollowUp] Done. {len(apps)} applications tracked.")
