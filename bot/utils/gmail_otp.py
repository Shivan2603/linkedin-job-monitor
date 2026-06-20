"""
bot/utils/gmail_otp.py — Auto-read OTP codes from Gmail via IMAP
Watches your Gmail inbox for OTP/verification emails from job sites
and returns the code so the bot can fill it automatically.

Setup required (one-time):
  1. Go to: https://myaccount.google.com/apppasswords
  2. Sign in → Select app: "Mail" → Select device: "Windows Computer"
  3. Click "Generate" → Copy the 16-char password (e.g. "abcd efgh ijkl mnop")
  4. Paste it in .env as: GMAIL_APP_PASSWORD=abcdefghijklmnop
"""
import imaplib
import email
import re
import time
import os
from email.header import decode_header
from bot.utils import logger

GMAIL_USER     = os.getenv("LINKEDIN_EMAIL", "sivashankar.avi6@gmail.com")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")

# Senders we look for OTP emails from
OTP_SENDERS = [
    "linkedin",
    "naukri",
    "indeed",
    "shine",
    "monster",
    "foundit",
    "jobstreet",
    "seek",
    "security",
    "verify",
    "noreply",
    "notification",
    "account",
    "no-reply",
]

# Regex patterns to extract OTP codes
OTP_PATTERNS = [
    r'\b(\d{6})\b',           # 6-digit code (most common)
    r'\b(\d{4})\b',           # 4-digit code
    r'code[:\s]+(\d{4,8})',   # "code: 123456"
    r'OTP[:\s]+(\d{4,8})',    # "OTP: 123456"
    r'pin[:\s]+(\d{4,8})',    # "pin: 1234"
    r'verification[:\s]+(\d{4,8})',
]


def _connect_gmail():
    """Connect to Gmail via IMAP using App Password."""
    if not GMAIL_APP_PASS or len(GMAIL_APP_PASS) < 10:
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        # Remove spaces from app password (Google shows it with spaces)
        clean_pass = GMAIL_APP_PASS.replace(" ", "")
        mail.login(GMAIL_USER, clean_pass)
        return mail
    except Exception as e:
        logger.warn(f"Gmail IMAP connection failed: {e}", "otp")
        return None


def _extract_otp_from_text(text: str) -> str | None:
    """Try all OTP patterns to extract a code from email text."""
    for pattern in OTP_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Filter out obviously wrong numbers (years, etc.)
            for match in matches:
                num = int(match)
                if 1000 <= num <= 999999:  # Valid OTP range
                    return match
    return None


def _get_email_text(msg) -> str:
    """Extract plain text from email message."""
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    text += part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            text = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return text


def wait_for_otp(site: str = "any", timeout_seconds: int = 60) -> str | None:
    """
    Wait for an OTP email to arrive in Gmail and return the code.
    
    Args:
        site: Job site name (e.g. "linkedin") — used to filter emails
        timeout_seconds: How long to wait for the OTP email (default 60s)
    
    Returns:
        OTP code string if found, None if timed out or error
    """
    if not GMAIL_APP_PASS or len(GMAIL_APP_PASS) < 10:
        logger.warn("GMAIL_APP_PASSWORD not set — cannot auto-read OTP. Please enter it manually.", "otp")
        return None

    logger.info(f"Watching Gmail for OTP from {site} (timeout: {timeout_seconds}s)...", "otp")
    
    start_time = time.time()
    check_interval = 5  # Check every 5 seconds

    while time.time() - start_time < timeout_seconds:
        try:
            mail = _connect_gmail()
            if not mail:
                return None

            mail.select("INBOX")

            # Search for recent unseen emails
            _, msg_ids = mail.search(None, "UNSEEN")
            msg_id_list = msg_ids[0].split()

            for msg_id in reversed(msg_id_list[-10:]):  # Check last 10 unread
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Check sender
                sender = str(msg.get("From", "")).lower()
                subject = str(msg.get("Subject", "")).lower()

                # Filter: must be from a known OTP sender or related to our sites
                site_terms = [site.lower()]
                if site.lower() == "monster":
                    site_terms.extend(["foundit", "foundit.in", "foundit.sg", "monster"])
                elif site.lower() == "jobstreet":
                    site_terms.extend(["seek", "seek.com", "jobstreet"])

                is_relevant = (
                    any(s in sender for s in OTP_SENDERS) or
                    any(s in subject for s in ["otp", "code", "verify", "verification", "pin"] + site_terms)
                )

                if not is_relevant:
                    continue

                # Extract OTP from email body
                body = _get_email_text(msg)
                full_text = subject + " " + body
                otp = _extract_otp_from_text(full_text)

                if otp:
                    logger.info(f"OTP found: {otp} (from: {sender[:40]})", "otp")
                    mail.logout()
                    return otp

            mail.logout()

        except Exception as e:
            logger.warn(f"Gmail OTP check error: {e}", "otp")

        elapsed = time.time() - start_time
        remaining = timeout_seconds - elapsed
        if remaining > 0:
            logger.info(f"OTP not found yet, checking again in {check_interval}s... ({remaining:.0f}s remaining)", "otp")
            time.sleep(check_interval)

    logger.warn(f"OTP timeout after {timeout_seconds}s — please enter it manually in the browser", "otp")
    return None


def fill_otp_on_page(page, site: str = "any", timeout: int = 60) -> bool:
    """
    Watch Gmail for OTP, then fill it into the current page automatically.
    Returns True if OTP was found and filled, False otherwise.
    """
    otp = wait_for_otp(site=site, timeout_seconds=timeout)
    if not otp:
        return False

    # Try common OTP input selectors
    otp_selectors = [
        'input[name*="pin"]',
        'input[name*="otp"]',
        'input[name*="code"]',
        'input[name*="verification"]',
        'input[placeholder*="code"]',
        'input[placeholder*="OTP"]',
        'input[autocomplete="one-time-code"]',
        'input[type="number"][maxlength="6"]',
        'input[type="tel"][maxlength="6"]',
        'input[type="text"][maxlength="6"]',
    ]

    for selector in otp_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible():
                el.fill(otp)
                logger.info(f"OTP {otp} auto-filled successfully!", "otp")
                # Try to click submit/verify button
                for btn in ['button[type="submit"]', 'button:has-text("Verify")',
                           'button:has-text("Submit")', 'button:has-text("Continue")']:
                    try:
                        page.click(btn, timeout=3000)
                        break
                    except Exception:
                        continue
                return True
        except Exception:
            continue

    logger.warn("OTP found but could not auto-fill — please enter it manually", "otp")
    return False
