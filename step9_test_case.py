"""
STEP 9 — Test Case & Manual Inspection
Web Privacy Project - ENGR-UH 4323 Spring 2026

PURPOSE:
  Run your full analysis pipeline on the test page:
  https://salim.webprivacylab.com/

  This is the same analysis as Steps 5–8 but focused on a single page,
  so you can manually inspect every flagged and unflagged request.

HOW TO USE:
  1. First run the crawler on just the test page:
       python crawler.py --file test_url.txt
     where test_url.txt contains: https://salim.webprivacylab.com/
  
  2. Then run this script:
       python step9_test_case.py

  Note: If you already crawled this URL during the main crawl, you can
  filter by site_url = 'https://salim.webprivacylab.com/' instead of
  re-crawling.

RUN: python step9_test_case.py
"""

import sqlite3
import pandas as pd
from urllib.parse import urlparse
from adblockparser import AdblockRules

DB_PATH = "./datadir/crawl.sqlite"
TEST_URL = "https://salim.webprivacylab.com/"

print("=" * 65)
print("  Step 9: Test Case & Manual Inspection")
print(f"  Target: {TEST_URL}")
print("=" * 65)

conn = sqlite3.connect(DB_PATH)

# ─────────────────────────────────────────────
# Pull all HTTP requests for the test page
# ─────────────────────────────────────────────
http_df = pd.read_sql(f"""
    SELECT
        r.url,
        r.top_level_url,
        r.is_third_party_channel,
        r.resource_type,
        r.method,
        r.post_body,
        r.referrer
    FROM http_requests r
    JOIN site_visits sv ON r.visit_id = sv.visit_id
    WHERE sv.site_url LIKE '%salim.webprivacylab%'
       OR sv.site_url LIKE '%{TEST_URL.rstrip("/")}%';
""", conn)

print(f"[*] HTTP requests found for test page: {len(http_df)}")

if http_df.empty:
    print("[!] No requests found for the test URL.")
    print("    Make sure you've crawled https://salim.webprivacylab.com/")
    print("    Create test_url.txt with that URL and run:")
    print("      python crawler.py --file test_url.txt")
    conn.close()
    exit()

# ─────────────────────────────────────────────
# Pull JS calls for the test page
# ─────────────────────────────────────────────
js_df = pd.read_sql(f"""
    SELECT j.script_url, j.symbol, j.operation, j.value
    FROM javascript j
    JOIN site_visits sv ON j.visit_id = sv.visit_id
    WHERE sv.site_url LIKE '%salim.webprivacylab%';
""", conn)

conn.close()
print(f"[*] JavaScript API calls: {len(js_df)}")

# ─────────────────────────────────────────────
# Apply tracking detection
# ─────────────────────────────────────────────
def load_rules() -> AdblockRules | None:
    lines = []
    for path in ["./datadir/EasyList.txt", "./datadir/EasyPrivacy.txt"]:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines.extend(f.readlines())
        except FileNotFoundError:
            pass
    return AdblockRules(lines) if lines else None

rules = load_rules()

if rules:
    http_df["flagged_by_filter"] = http_df["url"].apply(rules.should_block)
else:
    print("[!] No filter lists cached. Run step6 first.")
    http_df["flagged_by_filter"] = False

def get_domain(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

http_df["request_domain"] = http_df["url"].apply(get_domain)

# ─────────────────────────────────────────────
# SECTION A: All requests overview
# ─────────────────────────────────────────────
print("\n" + "─" * 65)
print("  [A] ALL HTTP Requests")
print("─" * 65)
print(http_df[["url", "resource_type", "is_third_party_channel",
               "flagged_by_filter"]].to_string(index=False))

# ─────────────────────────────────────────────
# SECTION B: Requests flagged as tracking
# ─────────────────────────────────────────────
flagged = http_df[http_df["flagged_by_filter"]]
print(f"\n{'─'*65}")
print(f"  [B] Flagged as Tracking ({len(flagged)} requests)")
print(f"{'─'*65}")

if flagged.empty:
    print("  No requests flagged.")
else:
    for _, row in flagged.iterrows():
        party = "3rd-party" if row["is_third_party_channel"] else "1st-party"
        print(f"  [{party}] {row['resource_type']:15} {row['url'][:80]}")
        print(f"           Domain: {row['request_domain']}")
        print()

# ─────────────────────────────────────────────
# SECTION C: Suspicious but NOT flagged
# (This is the key manual inspection task)
#
# Strategy: look for known tracking patterns that filter lists miss:
#   - Requests with tracking-like parameters (?utm_, ?pixel, ?cid=)
#   - Beacons (resource_type = 'beacon' or 'ping')
#   - Requests to analytics-looking paths (/collect, /pixel, /beacon)
#   - Image pixels (1x1 or tiny images)
#   - Requests from third-party domains not yet in filter lists
# ─────────────────────────────────────────────
not_flagged = http_df[~http_df["flagged_by_filter"]]
print(f"{'─'*65}")
print(f"  [C] NOT Flagged — Manual Inspection ({len(not_flagged)} requests)")
print(f"{'─'*65}")

# Apply heuristics to find suspicious-but-missed requests
def is_suspicious(row) -> tuple[bool, str]:
    url = row["url"].lower()
    domain = row["request_domain"].lower()
    reason = []

    # Heuristic 1: tracking parameter patterns in URL
    tracking_params = ["utm_", "pixel", "cid=", "fbclid", "gclid", "mc_eid",
                       "_ga=", "affiliate", "/collect", "/beacon", "/pixel",
                       "/track", "/analytics", "/log?", "/event?"]
    for p in tracking_params:
        if p in url:
            reason.append(f"tracking param '{p}' in URL")

    # Heuristic 2: beacon or ping resource type
    if row["resource_type"] in ("beacon", "ping", "xhr", "fetch"):
        reason.append(f"resource_type={row['resource_type']} (often used for tracking)")

    # Heuristic 3: third-party tiny image (pixel tracking)
    if row["is_third_party_channel"] and row["resource_type"] == "image":
        reason.append("3rd-party image (possible 1x1 pixel tracker)")

    # Heuristic 4: known analytics/ad TLDs not yet in filter lists
    suspicious_domains = [
        "segment.io", "segment.com", "mixpanel.com", "amplitude.com",
        "hotjar.com", "clarity.ms", "fullstory.com", "heap.io",
        "intercom.io", "intercom.com", "crisp.chat", "tealiumiq.com",
        "taboola.com", "outbrain.com", "criteo.com",
    ]
    for sd in suspicious_domains:
        if sd in domain:
            reason.append(f"known tracking service: {sd}")

    if reason:
        return True, "; ".join(reason)
    return False, ""


print("\n  Suspicious (unflagged) requests and WHY they're suspicious:\n")
found_suspicious = False
for _, row in not_flagged.iterrows():
    suspicious, reason = is_suspicious(row)
    if suspicious:
        found_suspicious = True
        party = "3rd-party" if row["is_third_party_channel"] else "1st-party"
        print(f"  ⚠ [{party}] {row['url'][:80]}")
        print(f"    WHY SUSPICIOUS : {reason}")
        print(f"    NOT FLAGGED BECAUSE: Filter lists haven't added this domain/path yet.")
        print(f"    This illustrates filter-list limitations: lists are reactive, not proactive.")
        print()

if not found_suspicious:
    print("  No additional suspicious requests found by heuristics.")
    print("  (You should still manually inspect all third-party requests above)")

# ─────────────────────────────────────────────
# SECTION D: Canvas & Audio fingerprinting
# ─────────────────────────────────────────────
CANVAS_WRITE = {"CanvasRenderingContext2D.fillText", "CanvasRenderingContext2D.strokeText"}
CANVAS_READ  = {"HTMLCanvasElement.toDataURL", "CanvasRenderingContext2D.getImageData"}
AUDIO_CTX    = {"AudioContext", "OfflineAudioContext"}
AUDIO_READ   = {"AnalyserNode.getFloatFrequencyData", "AudioBuffer.getChannelData",
                "OfflineAudioContext.startRendering"}

has_canvas_write  = js_df["symbol"].isin(CANVAS_WRITE).any()
has_canvas_read   = js_df["symbol"].isin(CANVAS_READ).any()
has_audio_ctx     = js_df["symbol"].str.contains("AudioContext", na=False).any()
has_audio_read    = js_df["symbol"].isin(AUDIO_READ).any()

print(f"\n{'─'*65}")
print(f"  [D] Fingerprinting Detection")
print(f"{'─'*65}")
print(f"  Canvas write APIs used : {has_canvas_write}")
print(f"  Canvas read APIs used  : {has_canvas_read}")
print(f"  Canvas fingerprinting  : {has_canvas_write and has_canvas_read}")
print(f"  Audio context used     : {has_audio_ctx}")
print(f"  Audio read APIs used   : {has_audio_read}")
print(f"  Audio fingerprinting   : {has_audio_ctx and has_audio_read}")

if has_canvas_write and has_canvas_read:
    canvas_scripts = js_df[js_df["symbol"].isin(CANVAS_WRITE | CANVAS_READ)]["script_url"].unique()
    print(f"\n  Canvas fingerprinting scripts:")
    for s in canvas_scripts:
        print(f"    {s}")

# ─────────────────────────────────────────────
# Summary for your report
# ─────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  REPORT SUMMARY for {TEST_URL}")
print(f"{'='*65}")
print(f"  Total HTTP requests        : {len(http_df)}")
print(f"  Flagged as tracking        : {len(flagged)} ({len(flagged)/len(http_df)*100:.1f}%)")
print(f"  Suspicious but unflagged   : {sum(1 for _, r in not_flagged.iterrows() if is_suspicious(r)[0])}")
print(f"  Canvas fingerprinting      : {'Yes' if has_canvas_write and has_canvas_read else 'No'}")
print(f"  Audio fingerprinting       : {'Yes' if has_audio_ctx and has_audio_read else 'No'}")

print("\n[✓] Step 9 complete.")
