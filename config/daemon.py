"""
daemon.py — FieldOps Background Daemon
Agent: Chris | Phase 5: Continuous Operations

Runs a continuous loop every 5 minutes:
  - monitor.py  : checks Gmail for new incoming packets
  - route.py    : promotes inbox packets to processing/

respond.py is intentionally NOT run automatically — sending email requires
explicit user approval. The daemon alerts you when missions are pending review.

Run:  python C:/Users/glegr/FieldOps/config/daemon.py
Stop: CTRL+C
"""

import subprocess
import sys
import time
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

FIELDOPS_ROOT  = Path("C:/Users/glegr/FieldOps")
CONFIG_DIR     = FIELDOPS_ROOT / "config"
PROCESSING_DIR = FIELDOPS_ROOT / "processing"
ACTIVITY_LOG   = FIELDOPS_ROOT / "logs" / "activity" / "activity-log.txt"
ERROR_LOG      = FIELDOPS_ROOT / "logs" / "errors" / "error-log.txt"

MONITOR_SCRIPT = CONFIG_DIR / "monitor.py"
ROUTE_SCRIPT   = CONFIG_DIR / "route.py"
RESPOND_SCRIPT = CONFIG_DIR / "respond.py"

CYCLE_INTERVAL_SECONDS = 300  # 5 minutes

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def _write_log(path: Path, level: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")

def log_activity(message: str):
    _write_log(ACTIVITY_LOG, "INFO", message)

def log_error(message: str):
    _write_log(ERROR_LOG, "ERROR", message)

def print_status(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# ---------------------------------------------------------------------------
# SCRIPT RUNNER
# ---------------------------------------------------------------------------

def run_script(script_path: Path) -> tuple:
    """
    Runs a Python script as a subprocess.
    Returns (success: bool, output: str).
    """
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2-minute timeout per script
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error_detail = result.stderr.strip() or output
            return False, error_detail
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"{script_path.name} timed out after 120 seconds"
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------------
# PENDING MISSION CHECK
# ---------------------------------------------------------------------------

def check_pending_missions() -> list:
    """
    Returns a list of mission IDs in processing/ that have request.txt
    but no sent.flag (i.e., awaiting response approval).
    """
    pending = []
    if not PROCESSING_DIR.exists():
        return pending
    for folder in sorted(PROCESSING_DIR.iterdir()):
        if folder.is_dir() and re.match(r"M-\d{4}$", folder.name):
            if (folder / "request.txt").exists() and not (folder / "sent.flag").exists():
                pending.append(folder.name)
    return pending

# ---------------------------------------------------------------------------
# SINGLE CYCLE
# ---------------------------------------------------------------------------

def run_cycle(cycle_num: int):
    log_activity(f"--- Cycle {cycle_num} start ---")
    print_status(f"Cycle {cycle_num} starting ...")

    # Step 1: monitor.py
    print_status("  Running monitor.py ...")
    success, output = run_script(MONITOR_SCRIPT)
    if success:
        log_activity(f"Cycle {cycle_num} | monitor.py OK")
        # Echo key lines to terminal
        for line in output.splitlines():
            if "Found" in line or "INTAKE OK" in line or "complete" in line.lower():
                print(f"           {line}")
    else:
        log_error(f"Cycle {cycle_num} | monitor.py FAILED: {output}")
        print_status(f"  [ERROR] monitor.py failed — logged to error-log.txt")

    # Step 2: route.py
    print_status("  Running route.py ...")
    success, output = run_script(ROUTE_SCRIPT)
    if success:
        log_activity(f"Cycle {cycle_num} | route.py OK")
        for line in output.splitlines():
            if "routed" in line.lower() or "No packets" in line:
                print(f"           {line}")
    else:
        log_error(f"Cycle {cycle_num} | route.py FAILED: {output}")
        print_status(f"  [ERROR] route.py failed — logged to error-log.txt")

    # Step 3: Check for missions pending response approval
    pending = check_pending_missions()
    if pending:
        missions_str = ", ".join(pending)
        log_activity(f"Cycle {cycle_num} | Pending approval: {missions_str}")
        print_status(f"  *** {len(pending)} mission(s) awaiting your approval: {missions_str}")
        print_status(f"  *** Run: python {RESPOND_SCRIPT}")
    else:
        log_activity(f"Cycle {cycle_num} | No missions pending approval")

    log_activity(f"--- Cycle {cycle_num} end ---")
    print_status(f"Chris is running. Cycle {cycle_num} complete.")

# ---------------------------------------------------------------------------
# DAEMON LOOP
# ---------------------------------------------------------------------------

def run_daemon():
    print("=" * 60)
    print("  FieldOps Daemon — Agent: Chris")
    print(f"  Cycle interval: {CYCLE_INTERVAL_SECONDS // 60} minutes")
    print(f"  Monitoring: {FIELDOPS_ROOT}")
    print("  Stop with: CTRL+C")
    print("=" * 60)
    print()

    log_activity("=== FieldOps daemon started ===")

    cycle_num = 1
    try:
        while True:
            run_cycle(cycle_num)
            cycle_num += 1

            # Countdown to next cycle
            print_status(f"Next cycle in {CYCLE_INTERVAL_SECONDS // 60} minutes. Waiting ...")
            print()
            time.sleep(CYCLE_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print_status("CTRL+C received. Shutting down ...")
        log_activity("=== FieldOps daemon stopped by user (CTRL+C) ===")
        print_status("Chris is offline. Goodbye.")
        sys.exit(0)


if __name__ == "__main__":
    run_daemon()
