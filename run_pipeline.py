import subprocess
import sys
from datetime import datetime

LOG_FILE = "pipeline_run.log"

steps = [
    ("Step 5 - Tracking Cookies", "python3 step5_tracking_cookies.py"),
    ("Step 6 - Tracking Requests", "python3 step6_tracking_requests.py"),
    ("Step 7 - Ecosystem Analysis", "python3 step7_ecosystem.py"),
    ("Recover Step 6", "python3 recover_step6.py"),
    ("Recover Step 7", "python3 recover_step7.py"),
    ("Step 8 - Fingerprinting", "python3 step8_fingerprinting.py"),
    ("Step 9 - Test Case Analysis", "python3 step9_test_case.py"),
    ("Step 9 - HAR vs Crawl Diff", "python3 step9_har_vs_crawl_diff.py"),
]

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()} - {msg}\n")

def run_step(name, command):
    log("\n" + "=" * 70)
    log(f"RUNNING: {name}")
    log(f"COMMAND: {command}")
    log("=" * 70)

    result = subprocess.run(command, shell=True)

    if result.returncode != 0:
        log(f"[❌ FAILED] {name}")
        sys.exit(1)
    else:
        log(f"[✓ SUCCESS] {name}")

def main():
    log("\n\n================ PIPELINE STARTED ================\n")

    for name, cmd in steps:
        run_step(name, cmd)

    log("\n================ PIPELINE COMPLETED ================\n")
    log("All steps executed successfully.")

if __name__ == "__main__":
    main()
