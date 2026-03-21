"""
route.py — FieldOps Inbox Router
Agent: Chris | Phase 3.5: Intake to Processing

Scans inbox/ for M-XXXX-received.txt files, creates a mission folder in
processing/, copies the packet in as request.txt, and moves the original
to archive/raw_packets/.

CONSTRAINTS:
- Does not delete any files — originals moved to archive/raw_packets/
- Does not act outside the FieldOps directory
- All actions are logged
"""

import shutil
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

FIELDOPS_ROOT  = Path("C:/Users/glegr/FieldOps")
INBOX_DIR      = FIELDOPS_ROOT / "inbox"
PROCESSING_DIR = FIELDOPS_ROOT / "processing"
RAW_ARCHIVE    = FIELDOPS_ROOT / "archive" / "raw_packets"
ACTIVITY_LOG   = FIELDOPS_ROOT / "logs" / "activity" / "activity-log.txt"
ERROR_LOG      = FIELDOPS_ROOT / "logs" / "errors" / "error-log.txt"

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def _write_log(path: Path, level: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")

def log_activity(message: str):
    _write_log(ACTIVITY_LOG, "INFO", message)
    print(f"[ACTIVITY] {message}")

def log_error(message: str):
    _write_log(ERROR_LOG, "ERROR", message)
    print(f"[ERROR]    {message}")

# ---------------------------------------------------------------------------
# ROUTER
# ---------------------------------------------------------------------------

def run_router():
    log_activity("=== FieldOps router started ===")

    # Find all M-XXXX-received.txt files in inbox/
    inbox_packets = sorted(INBOX_DIR.glob("M-[0-9][0-9][0-9][0-9]-received.txt"))

    if not inbox_packets:
        log_activity("No packets found in inbox/. Nothing to route.")
        return

    log_activity(f"Found {len(inbox_packets)} packet(s) in inbox/.")

    routed = 0
    for packet_file in inbox_packets:
        # Extract mission ID from filename
        match = re.match(r"(M-\d{4})-received\.txt", packet_file.name)
        if not match:
            log_error(f"Unexpected filename format: {packet_file.name} — skipping.")
            continue

        mission_id = match.group(1)
        mission_folder = PROCESSING_DIR / mission_id

        # Skip if already routed
        if mission_folder.exists():
            log_activity(f"{mission_id}: processing folder already exists — skipping.")
            continue

        # Create mission folder in processing/
        mission_folder.mkdir(parents=True, exist_ok=True)
        log_activity(f"{mission_id}: Created processing/{mission_id}/")

        # Copy packet into processing/M-XXXX/request.txt
        request_dest = mission_folder / "request.txt"
        shutil.copy2(str(packet_file), str(request_dest))
        log_activity(f"{mission_id}: Copied to processing/{mission_id}/request.txt")

        # Move original to archive/raw_packets/
        raw_dest = RAW_ARCHIVE / packet_file.name
        shutil.move(str(packet_file), str(raw_dest))
        log_activity(f"{mission_id}: Original moved to archive/raw_packets/{packet_file.name}")

        routed += 1

    log_activity(f"=== Router complete: {routed} packet(s) routed to processing/ ===")


if __name__ == "__main__":
    run_router()
