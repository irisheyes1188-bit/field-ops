"""
respond.py — FieldOps Response Engine
Agent: Chris | Phase 4: Response + Dispatch

Scans processing/ for pending missions, generates MISSION_RESPONSE packets,
requires explicit user approval before sending, then archives the mission.

CONSTRAINTS:
- No email is sent without explicit user approval at the terminal
- No files are deleted — only moved
- Does not act outside the FieldOps directory
- All actions are logged
"""

import imaplib
import smtplib
import shutil
import ssl
import re
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

FIELDOPS_ROOT    = Path("C:/Users/glegr/FieldOps")
CONFIG_DIR       = FIELDOPS_ROOT / "config"
PROCESSING_DIR   = FIELDOPS_ROOT / "processing"
OUTBOX_DIR       = FIELDOPS_ROOT / "outbox"
ARCHIVE_DONE     = FIELDOPS_ROOT / "archive" / "completed"
ARCHIVE_FAILED   = FIELDOPS_ROOT / "archive" / "failed"
ACTIVITY_LOG     = FIELDOPS_ROOT / "logs" / "activity" / "activity-log.txt"
ERROR_LOG        = FIELDOPS_ROOT / "logs" / "errors" / "error-log.txt"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.env"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT   = 587

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
# CREDENTIALS
# ---------------------------------------------------------------------------

def load_credentials() -> tuple:
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"credentials.env not found at {CREDENTIALS_FILE}")
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
        raise ValueError("credentials.env must contain EMAIL= and APP_PASSWORD=")
    return email_addr, app_password

# ---------------------------------------------------------------------------
# REQUEST PARSER
# ---------------------------------------------------------------------------

def parse_packet(filepath: Path) -> dict:
    """Parse a flat key: value packet file into a dict."""
    fields = {}
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip().upper()] = value.strip()
    return fields

def extract_sender_email(from_field: str) -> str:
    """Pull bare email address from 'Name <email>' or plain 'email'."""
    match = re.search(r"<(.+?)>", from_field)
    if match:
        return match.group(1).strip()
    return from_field.strip()

# ---------------------------------------------------------------------------
# RESPONSE GENERATOR
# ---------------------------------------------------------------------------

def generate_response(mission_id: str, request: dict) -> str:
    """Build a MISSION_RESPONSE packet from the parsed request fields."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    objective  = request.get("OBJECTIVE", "[not specified]")
    lane       = request.get("LANE", "[not specified]")
    constraints = request.get("CONSTRAINTS", "[none listed]")
    desired    = request.get("DESIRED_OUTPUT", "[not specified]")

    response = (
        f"PACKET_TYPE: MISSION_RESPONSE\n"
        f"MISSION_ID: {mission_id}\n"
        f"DATE: {timestamp}\n"
        f"STATUS: COMPLETE\n"
        f"SUMMARY: Response to mission {mission_id} — {objective}\n"
        f"OUTPUT:\n"
        f"  Lane: {lane}\n"
        f"  Objective addressed: {objective}\n"
        f"  Constraints observed: {constraints}\n"
        f"  Desired output target: {desired}\n"
        f"  [Agent response body — edit above this line before approving]\n"
        f"ATTACHMENTS: None\n"
    )
    return response

# ---------------------------------------------------------------------------
# APPROVAL GATE
# ---------------------------------------------------------------------------

def request_approval(mission_id: str, to_addr: str,
                     subject: str, body: str) -> bool:
    """
    Displays the full email draft to the user and requires explicit approval.
    Returns True if approved, False if rejected.
    """
    divider = "=" * 60
    print(f"\n{divider}")
    print(f"  DRAFT READY FOR REVIEW — {mission_id}")
    print(divider)
    print(f"  TO:      {to_addr}")
    print(f"  SUBJECT: {subject}")
    print(f"  BODY:")
    print(divider)
    print(body)
    print(divider)
    print("\nType APPROVE to send, or anything else to abort:")
    answer = input("  > ").strip().upper()
    if answer == "APPROVE":
        print()
        return True
    print(f"\n[ABORTED] Mission {mission_id} response not sent.")
    return False

# ---------------------------------------------------------------------------
# EMAIL SENDER
# ---------------------------------------------------------------------------

def send_email(from_addr: str, app_password: str,
               to_addr: str, subject: str, body: str):
    """Send via Gmail SMTP TLS. Raises on failure."""
    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(from_addr, app_password)
        server.sendmail(from_addr, to_addr, msg.as_string())

# ---------------------------------------------------------------------------
# ARCHIVE
# ---------------------------------------------------------------------------

def archive_mission(mission_folder: Path, success: bool):
    """Move mission folder to archive/completed or archive/failed."""
    destination = ARCHIVE_DONE if success else ARCHIVE_FAILED
    target = destination / mission_folder.name
    # Avoid collision if a folder with same name already exists
    if target.exists():
        target = destination / f"{mission_folder.name}-{datetime.now().strftime('%H%M%S')}"
    shutil.move(str(mission_folder), str(target))
    status = "completed" if success else "failed"
    log_activity(f"Mission {mission_folder.name} moved to archive/{status}/")

# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_response_engine():
    log_activity("=== FieldOps response engine started ===")

    # Load credentials
    try:
        from_addr, app_password = load_credentials()
    except (FileNotFoundError, ValueError) as e:
        log_error(str(e))
        return

    # Scan processing/ for M-XXXX folders
    if not PROCESSING_DIR.exists():
        log_error(f"Processing directory not found: {PROCESSING_DIR}")
        return

    mission_folders = sorted([
        d for d in PROCESSING_DIR.iterdir()
        if d.is_dir() and re.match(r"M-\d{4}$", d.name)
    ])

    if not mission_folders:
        log_activity("No mission folders found in processing/. Nothing to do.")
        return

    log_activity(f"Found {len(mission_folders)} mission folder(s) in processing/.")

    pending = 0
    for folder in mission_folders:
        request_file  = folder / "request.txt"
        response_file = folder / "response.txt"

        sent_flag = folder / "sent.flag"

        if not request_file.exists():
            log_error(f"{folder.name}: request.txt not found — skipping.")
            continue
        if sent_flag.exists():
            log_activity(f"{folder.name}: already sent (sent.flag present) — skipping.")
            continue

        pending += 1
        mission_id = folder.name
        log_activity(f"Processing {mission_id} ...")

        # Parse request
        try:
            request = parse_packet(request_file)
        except Exception as e:
            log_error(f"{mission_id}: Failed to parse request.txt — {e}")
            continue

        from_field = request.get("FROM", "")
        to_addr    = extract_sender_email(from_field)

        if not to_addr:
            log_error(f"{mission_id}: No FROM address found in request.txt — skipping.")
            continue

        # Generate response
        response_body = generate_response(mission_id, request)

        # Save response.txt inside mission folder
        with open(response_file, "w", encoding="utf-8") as f:
            f.write(response_body)
        log_activity(f"{mission_id}: response.txt written to processing/{mission_id}/")

        # Copy to outbox
        outbox_copy = OUTBOX_DIR / f"{mission_id}-response.txt"
        shutil.copy2(str(response_file), str(outbox_copy))
        log_activity(f"{mission_id}: response copied to outbox/{mission_id}-response.txt")

        # Build email
        subject = f"FIELDOPS: MISSION_RESPONSE {mission_id}"

        # --- APPROVAL GATE ---
        approved = request_approval(mission_id, to_addr, subject, response_body)

        if not approved:
            log_activity(f"{mission_id}: Send aborted by user — mission left in processing/.")
            continue

        # Send email
        try:
            send_email(from_addr, app_password, to_addr, subject, response_body)
            log_activity(f"{mission_id}: Response email sent to {to_addr}")
            # Write sent flag before archiving
            (folder / "sent.flag").write_text(
                f"Sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nTo: {to_addr}\n"
            )
            archive_mission(folder, success=True)
        except Exception as e:
            log_error(f"{mission_id}: Email send failed — {e}")
            archive_mission(folder, success=False)

    if pending == 0:
        log_activity("All missions already have responses. Nothing to process.")

    log_activity("=== Response engine run complete ===")


if __name__ == "__main__":
    run_response_engine()
