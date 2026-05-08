"""
crawler.py  —  Web Privacy Project (ENGR-UH 4323) Spring 2026
Fixed v2: uses custom in-browser commands to extract links from the live DOM.

WHAT CHANGED FROM v1:
  The old approach snapshotted HTML files on disk to find links.
  This broke because DumpPageSourceCommand writes files asynchronously
  inside OpenWPM's browser process, so our Python code read too early.

  The new approach:
    1. A custom ExtractLinksCommand runs INSIDE the browser, reads the
       live DOM via JavaScript, and writes links to a small JSON file.
    """

import os
from pathlib import Path
from typing import Literal
import json
import argparse
import logging
import tranco

from openwpm.command_sequence import CommandSequence
from openwpm.commands.browser_commands import GetCommand, DumpPageSourceCommand
from openwpm.config import BrowserParams, ManagerParams
from openwpm.storage.sql_provider import SQLiteStorageProvider
from openwpm.task_manager import TaskManager

from custom_commands import CookieConsentCommand, ExtractLinksCommand, safe_site_name, SleepCommand

logger = logging.getLogger("openwpm")

# ─────────────────────────────────────────────────────────────────────────────
# ARGUMENTS
# ─────────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Web Privacy Crawler (OpenWPM)")
parser.add_argument("--tranco", action="store_true", default=False,
                    help="Load sites from Tranco top list")
parser.add_argument("--headless", action="store_true", default=False,
                    help="Run browser in headless mode (no GUI)")
parser.add_argument("--n", type=int, default=100,
                    help="Number of sites to crawl (default: 100)")
parser.add_argument("--file", type=str,
                    help="Path to a text/CSV file with one URL per line")
args = parser.parse_args()

# ─────────────────────────────────────────────────────────────────────────────
# BUILD SITE LIST
# ─────────────────────────────────────────────────────────────────────────────
sites = []

if args.tranco:
    print(f"[*] Loading Tranco top-{args.n} list...")
    t = tranco.Tranco(cache=True, cache_dir=".tranco")
    latest = t.list()
    sites = ["https://" + x for x in latest.top(args.n)]
    print(f"[*] Loaded {len(sites)} sites from Tranco.")

elif args.file:
    with open(args.file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("http"):
                line = "https://" + line
            sites.append(line)
    print(f"[*] Loaded {len(sites)} sites from {args.file}")

else:
    print("[*] No source specified — loading Tranco top 100 by default.")
    t = tranco.Tranco(cache=True, cache_dir=".tranco")
    latest = t.list()
    sites = ["https://" + x for x in latest.top(100)]
    print(f"[*] Loaded {len(sites)} sites.")

# ─────────────────────────────────────────────────────────────────────────────
# OPENWPM CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
display_mode: Literal["native", "headless", "xvfb"] = "native"

# cRAWLING FRO STEP 9 AS WELL
sites.append('https://salim.webprivacylab.com/')
if args.headless:
    display_mode = "headless"

NUM_BROWSERS = 2

manager_params = ManagerParams(num_browsers=NUM_BROWSERS)
browser_params = [BrowserParams(display_mode=display_mode) for _ in range(NUM_BROWSERS)]

for bp in browser_params:
    bp.http_instrument      = True   # record all HTTP requests & responses
    bp.cookie_instrument    = True   # record cookies (HTTP headers + JS)
    bp.js_instrument        = True   # record JS API calls (needed for fingerprinting)
    bp.callstack_instrument = False  # skip call stacks (heavy, not required)

manager_params.data_directory   = Path("./datadir/")
manager_params.log_path         = Path("./datadir/crawl.log")
manager_params.source_dump_path = Path("./datadir/sources/")

os.makedirs(manager_params.data_directory,            exist_ok=True)
os.makedirs(manager_params.source_dump_path,          exist_ok=True)
os.makedirs(manager_params.data_directory / "links",  exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# HELPER: Read links saved by ExtractLinksCommand
# ─────────────────────────────────────────────────────────────────────────────
def read_extracted_links(site_url: str) -> list:

    '''Read the JSON file written by ExtractLinksCommand for this site.

    The file is at: ./datadir/links/<sanitised_url>.json
    The sanitisation here MUST match what ExtractLinksCommand does.
    Returns [] if the file doesn't exist (e.g. the page failed to load).'''
   

    safe_name = safe_site_name(site_url)

    
    out_dir = manager_params.data_directory / "links"
    path = out_dir / f"{safe_name}.json"
    print("LOOKING FOR:", path)
    print("EXISTS:", path.exists())
    try:
        with open(path, "r") as f:
            data = json.load(f)
        links = data.get("links", [])
        print(f"  [✓] Read {len(links)} internal link(s) from {path.name}")
        return links
    except FileNotFoundError:
        print(f"  [~] No links file for {site_url} — page may have failed or had no links.")
        return []
    except Exception as e:
        print(f"  [!] Error reading links file: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# CRAWL LOOP
# ─────────────────────────────────────────────────────────────────────────────
crawl_stats = {
    "attempted": 0,
    "homepage_ok": 0,
    "homepage_fail": 0,
    "internal_visited": 0,
}

print(f"\n{'='*65}")
print(f"  Starting crawl — {len(sites)} site(s)  |  mode: {display_mode}")
print(f"{'='*65}\n")

with TaskManager(
    manager_params,
    browser_params,
    SQLiteStorageProvider(Path("./datadir/crawl.sqlite")),
    None,
) as manager:

    for index, site in enumerate(sites):
        print(f"\n[{index+1}/{len(sites)}] ── {site}")
        crawl_stats["attempted"] += 1

        # ── Homepage callback ─────────────────────────────────────────────────
        def homepage_callback(success: bool, val: str = site) -> None:
            status = "OK ✓" if success else "FAIL ✗"
            print(f"  → Homepage {status}: {val}")
            if success:
                crawl_stats["homepage_ok"] += 1
            else:
                crawl_stats["homepage_fail"] += 1

        # ──────────────────────────────────────────────────────────────────────
        # SEQUENCE 1: Homepage
        #
        # reset=True  →  fresh browser profile (isolates each site as required)
        #
        # Command order matters:
        #   GetCommand           — load the page, wait 25 s for JS to settle
        #   CookieConsentCommand — click "Accept" on any cookie banner
        #   ExtractLinksCommand  — read internal links from the live DOM via JS
        #   DumpPageSourceCommand— save HTML snapshot to disk
        # ──────────────────────────────────────────────────────────────────────
        seq_home = CommandSequence(
            site,
            site_rank=index,
            callback=homepage_callback,
            reset=True,       # ← new profile per site (project requirement)
        )

                # Navigate and wait 25 s (project requirement)
        seq_home.append_command(GetCommand(url=site, sleep=25), timeout=60)

        # 1. FIRST remove cookie overlays
        seq_home.append_command(CookieConsentCommand(), timeout=10)

        # 2. THEN wait for DOM to stabilize after interaction
        seq_home.append_command(SleepCommand(5), timeout=10)

        # 3. THEN extract links from clean DOM
        seq_home.append_command(
            ExtractLinksCommand(base_url=site, max_links=5),
            timeout=15
        )

        # 4. THEN dump page
        seq_home.append_command(DumpPageSourceCommand("home"), timeout=30)
        # Execute and BLOCK until the full sequence is done.
        # After this line returns, ExtractLinksCommand has already
        # written its JSON file — guaranteed, no race condition.
        manager.execute_command_sequence(seq_home)

        # ── Read links written by ExtractLinksCommand ─────────────────────────
        import time
        time.sleep(10)  # just to be safe, give it a moment to write
        internal_links = read_extracted_links(site)

        if not internal_links:
            print(f"  trying again internal pages for {site}.")
            internal_links = read_extracted_links(site)

        print(f"  Internal pages queued ({len(internal_links)}):")
        for lnk in internal_links:
            print(f"    • {lnk}")

        # ──────────────────────────────────────────────────────────────────────
        # SEQUENCE 2: Internal pages
        #
        # reset=False → SAME browser profile as homepage.
        # Cookies set on the homepage persist here — this simulates a real
        # user navigating within the same site (project requirement).
        # ──────────────────────────────────────────────────────────────────────
        def internal_callback(success: bool, val: str = site) -> None:
            status = "OK ✓" if success else "FAIL ✗"
            print(f"  → Internal pages {status}: {val}")

        seq_internal = CommandSequence(
            site,
            site_rank=index,
            callback=internal_callback,
            reset=False,      # ← same session, cookies persist
        )

        for i, link in enumerate(internal_links):
            seq_internal.append_command(GetCommand(url=link, sleep=25), timeout=60)
            seq_internal.append_command(
                DumpPageSourceCommand(f"internal_{i}"), timeout=30
            )

        manager.execute_command_sequence(seq_internal)
        crawl_stats["internal_visited"] += len(internal_links)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  Crawl Complete!")
print(f"{'='*65}")
print(f"  Sites attempted       : {crawl_stats['attempted']}")
print(f"  Homepages OK          : {crawl_stats['homepage_ok']}")
print(f"  Homepages failed      : {crawl_stats['homepage_fail']}")
if crawl_stats["attempted"] > 0:
    rate = crawl_stats["homepage_ok"] / crawl_stats["attempted"] * 100
    print(f"  Success rate          : {rate:.1f}%")
print(f"  Internal pages visited: {crawl_stats['internal_visited']}")
print(f"  Database              : ./datadir/crawl.sqlite")
print(f"{'='*65}\n")
