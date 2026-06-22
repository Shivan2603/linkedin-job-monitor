"""
bot/utils/email_sender.py — Cold email sender using Gmail SMTP
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from bot.utils import logger

def send_cold_email(to_email: str, subject: str, body: str, attachment_path: str = None) -> bool:
    """
    Sends an email via Gmail SMTP using LINKEDIN_EMAIL and GMAIL_APP_PASSWORD.
    If GMAIL_APP_PASSWORD is not set or is default placeholder, falls back to LINKEDIN_PASSWORD.
    
    Args:
        to_email: Recipient email address.
        subject: Email subject.
        body: Plain text or HTML body of the email.
        attachment_path: Optional path to a PDF attachment (e.g. tailored resume).
        
    Returns:
        True if email sent successfully, False otherwise.
    """
    from_email = os.getenv("LINKEDIN_EMAIL", "sivashankar.avi6@gmail.com").strip()
    gmail_app_pass = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    linkedin_pass = os.getenv("LINKEDIN_PASSWORD", "").strip()
    
    # Clean and choose password
    password = gmail_app_pass.replace(" ", "")
    
    # Fallback to LINKEDIN_PASSWORD if app pass is placeholder or empty
    if not password or "PASTE" in password.upper():
        logger.warn("GMAIL_APP_PASSWORD is not configured. Trying LINKEDIN_PASSWORD as fallback...", "email")
        password = linkedin_pass
        
    if not password:
        logger.error("No email password configured. Please set GMAIL_APP_PASSWORD or LINKEDIN_PASSWORD in your .env file.", "email")
        return False
        
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Attach body
        if "<html>" in body.lower():
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
            
        # Attach file
        if attachment_path:
            if not os.path.exists(attachment_path):
                logger.error(f"Attachment file not found: {attachment_path}", "email")
                return False
                
            filename = os.path.basename(attachment_path)
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {filename}",
            )
            msg.attach(part)
            
        # SMTP SSL Connection
        logger.info(f"Connecting to smtp.gmail.com:465 to send email to {to_email}...", "email")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
            
        logger.info(f"Cold email successfully sent to {to_email} with subject: '{subject}'", "email")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}", "email")
        return False
