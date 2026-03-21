"""
monitor.py — FieldOps Gmail Intake Monitor
Agent: Chris | Phase 3: Intake Only

Connects to fieldops1dispatch@gmail.com via IMAP, checks for unread emails,
validates each against FieldOps rules, and routes them to inbox/ or error log.

CONSTRAINTS:
- Does not delete any emails
- Does not send or reply to any emails
- Does not act outside the FieldOps directory
- Intake only — no processing triggered

SETUP REQUIRED:
1. Enable IMAP in Gmail settings: Settings > See All Settings > Forwarding and POP/IMAP
2. Generate a Gmail App Password:
   Google Account > Security > 2-Step Verification > App Passwords
   (Requires 2FA to be enabled on the account)
3. Fill in config/credentials.env with the generated app password
"""

import imaplib
import email
import os
import re
import ssl
from datetime import datetime
from pathlib import Path
from email.header import decode_header

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

FIELDOPS_ROOT   = Path("C:/Users/glegr/FieldOps")
CONFIG_DIR      = FIELDOPS_ROOT / "config"
INBOX_DIR       = FIELDOPS_ROOT / "inbox"
ACTIVITY_LOG    = FIELDOPS_ROOT / "logs" / "activity" / "activity-log.txt"
ERROR_LOG       = FIELDOPS_ROOT / "logs" / "errors" / "error-log.txt"
APPROVED_FILE   = CONFIG_DIR / "approved_senders.txt"
PACKET_TYPE_FILE = CONFIG_DIR / "packet_types.txt"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.env"

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT   = 993
SUBJECT_PREFIX = "FIELDOPS:"

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def _write_log(path: Path, level: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)

def log_activity(message: str):
    _write_log(ACTIVITY_LOG, "INFO", message)
    print(f"[ACTIVITY] {message}")

def log_error(message: str):
    _write_log(ERROR_LOG, "ERROR", message)
    print(f"[ERROR]    {message}")

# ---------------------------------------------------------------------------
# CONFIG LOADERS
# ---------------------------------------------------------------------------

def load_approved_senders() -> set:
    senders = set()
    if not APPROVED_FILE.exists():
        log_error(f"approved_senders.txt not found at {APPROVED_FILE}")
        return senders
    with open(APPROVED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                senders.add(line.lower())
    return senders

def load_packet_types() -> set:
    types = set()
    if not PACKET_TYPE_FILE.exists():
        log_error(f"packet_types.txt not found at {PACKET_TYPE_FILE}")
        return types
    with open(PACKET_TYPE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                types.add(line.upper())
    return types

def load_credentials() -> tuple:
    """Returns (email_address, app_password) from credentials.env."""
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.env not found at {CREDENTIALS_FILE}\n"
            "Create it with two lines:\n"
            "  EMAIL=fieldops1dispatch@gmail.com\n"
            "  APP_PASSWORD=your_app_password_here"
        )
    creds = {}
    with open(CREDENTIALS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                creds[key.strip().upper()] = value.strip()
    email_addr = creds.get("EMAIL")
    app_password = creds.get("APP_PASSWORD")
    if not email_addr or not app_password:
        raise ValueError(
            "credentials.env must contain both EMAIL= and APP_PASSWORD= entries."
        )
    return email_addr, app_password

# ---------------------------------------------------------------------------
# MISSION ID
# ---------------------------------------------------------------------------

def next_mission_id() -> str:
    """Scans inbox/ for existing M-XXXX files and returns the next ID."""
    existing = list(INBOX_DIR.glob("M-[0-9][0-9][0-9][0-9]-*.txt"))
    if not existing:
        return "M-0001"
    numbers = []
    for f in existing:
        match = re.match(r"M-(\d{4})-", f.name)
        if match:
            numbers.append(int(match.group(1)))
    return f"M-{max(numbers) + 1:04d}"

# ---------------------------------------------------------------------------
# EMAIL UTILITIES
# ---------------------------------------------------------------------------

def decode_mime_words(s: str) -> str:
    """Decode encoded email headers (e.g. =?utf-8?...)."""
    parts = decode_header(s)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)

def extract_body(msg) -> str:
    """Extract plain-text body from an email.message.Message object."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if ctype == "text/plain" and "attachment" not in disposition:
                charset = part.get_content_charset() or "utf-8"
                body = part.get_payload(decode=True).decode(charset, errors="replace")
                break
    else:
        charset = msg.get_content_charset() or "utf-8"
        body = msg.get_payload(decode=True).decode(charset, errors="replace")
    return body.strip()

# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_email(sender: str, subject: str, body: str,
                   approved_senders: set, packet_types: set) -> tuple:
    """
    Returns (is_valid: bool, reason: str, detected_packet_type: str | None).
    """
    sender_clean = sender.lower().strip()
    # Strip display name if present: "Name <email@domain>" -> "email@domain"
    match = re.search(r"<(.+?)>", sender_clean)
    if match:
        sender_clean = match.group(1).strip()

    if sender_clean not in approved_senders:
        return False, f"Sender not approved: {sender_clean}", None

    if SUBJECT_PREFIX not in subject.upper():
        return False, f"Subject missing '{SUBJECT_PREFIX}' prefix: {subject}", None

    detected_type = None
    for ptype in packet_types:
        if ptype in body.upper():
            detected_type = ptype
            break

    if detected_type is None:
        return False, f"No valid PACKET_TYPE found in body", None

    return True, "OK", detected_type

# ---------------------------------------------------------------------------
# INTAKE
# ---------------------------------------------------------------------------

def save_to_inbox(mission_id: str, sender: str, subject: str,
                  body: str, packet_type: str) -> Path:
    """Writes the raw email body to inbox/ and returns the file path."""
    filename = f"{mission_id}-received.txt"
    filepath = INBOX_DIR / filename
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = (
        f"RECEIVED: {timestamp}\n"
        f"MISSION_ID: {mission_id}\n"
        f"FROM: {sender}\n"
        f"SUBJECT: {subject}\n"
        f"PACKET_TYPE: {packet_type}\n"
        f"---\n"
        f"{body}\n"
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath

# ---------------------------------------------------------------------------
# MAIN MONITOR LOOP
# ---------------------------------------------------------------------------

def run_monitor():
    log_activity("=== FieldOps monitor started ===")

    # Load config
    approved_senders = load_approved_senders()
    packet_types = load_packet_types()
    log_activity(f"Loaded {len(approved_senders)} approved sender(s), "
                 f"{len(packet_types)} packet type(s).")

    # Load credentials
    try:
        email_addr, app_password = load_credentials()
    except (FileNotFoundError, ValueError) as e:
        log_error(str(e))
        return

    # Connect via IMAP
    log_activity(f"Connecting to {IMAP_SERVER} as {email_addr} ...")
    try:
        context = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, ssl_context=context)
        mail.login(email_addr, app_password)
    except imaplib.IMAP4.error as e:
        log_error(f"IMAP login failed: {e}")
        return
    except Exception as e:
        log_error(f"Connection error: {e}")
        return

    log_activity("IMAP connection established.")

    # Select inbox in write mode so we can mark messages as read after intake
    mail.select("INBOX", readonly=False)

    # Search for unread messages
    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        log_error("Failed to search inbox for unread messages.")
        mail.logout()
        return

    msg_ids = data[0].split()
    log_activity(f"Found {len(msg_ids)} unread message(s).")

    if not msg_ids:
        log_activity("No new messages. Monitor run complete.")
        mail.logout()
        return

    processed = 0
    rejected  = 0

    for msg_id in msg_ids:
        # Fetch message
        status, msg_data = mail.fetch(msg_id, "(RFC822)")
        if status != "OK":
            log_error(f"Failed to fetch message ID {msg_id}.")
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        sender  = decode_mime_words(msg.get("From", ""))
        subject = decode_mime_words(msg.get("Subject", ""))
        body    = extract_body(msg)

        # Validate
        valid, reason, packet_type = validate_email(
            sender, subject, body, approved_senders, packet_types
        )

        if valid:
            mission_id = next_mission_id()
            filepath = save_to_inbox(mission_id, sender, subject, body, packet_type)
            log_activity(
                f"INTAKE OK | {mission_id} | type={packet_type} | "
                f"from={sender} | file={filepath.name}"
            )
            # Mark as read on Gmail so it is not re-ingested next cycle
            mail.store(msg_id, "+FLAGS", "\\Seen")
            processed += 1
        else:
            log_error(
                f"INTAKE REJECTED | from={sender} | subject={subject} | reason={reason}"
            )
            # Mark rejected messages as read too — they will never pass validation
            mail.store(msg_id, "+FLAGS", "\\Seen")
            rejected += 1

    log_activity(
        f"=== Monitor run complete: {processed} accepted, {rejected} rejected ==="
    )
    mail.logout()


if __name__ == "__main__":
    run_monitor()
