import json
import pandas as pd
from urllib.parse import urlparse

CRAWL_CSV = "./datadir/step9_all_requests.csv"
HAR_FILE  = "./datadir/salim.webprivacylab.com.har"
OUTPUT    = "./datadir/har_only_tracking_requests.csv"


# ─────────────────────────────────────────────
# Load crawl data
# ─────────────────────────────────────────────
crawl_df = pd.read_csv(CRAWL_CSV)
crawl_urls = set(crawl_df["url"].dropna().str.strip())

print(f"[+] Crawl requests loaded: {len(crawl_urls)}")


# ─────────────────────────────────────────────
# Load HAR file
# ─────────────────────────────────────────────
with open(HAR_FILE, "r", encoding="utf-8") as f:
    har_data = json.load(f)

entries = har_data["log"]["entries"]

har_requests = []

for e in entries:
    try:
        url = e["request"]["url"]
        method = e["request"]["method"]
        status = e["response"]["status"]
        mime = e["response"]["content"].get("mimeType", "")

        har_requests.append({
            "url": url,
            "method": method,
            "status": status,
            "mimeType": mime,
            "domain": urlparse(url).netloc
        })
    except:
        continue

har_df = pd.DataFrame(har_requests)

print(f"[+] HAR requests loaded: {len(har_df)}")


# ─────────────────────────────────────────────
# STEP 1: Find requests missing in crawl
# ─────────────────────────────────────────────
har_df["in_crawl"] = har_df["url"].apply(lambda x: x in crawl_urls)

missing_df = har_df[har_df["in_crawl"] == False].copy()


# ─────────────────────────────────────────────
# STEP 2: Heuristic tracking detection
# ─────────────────────────────────────────────
def is_tracking(url):
    url = url.lower()

    tracking_signals = [
        "track", "pixel", "beacon", "collect",
        "analytics", "metrics", "log", "event",
        "facebook", "doubleclick", "googletagmanager",
        "scorecard", "segment", "amplitude",
        "hotjar", "clarity", "ads", "adservice"
    ]

    return any(s in url for s in tracking_signals)


missing_df["likely_tracking"] = missing_df["url"].apply(is_tracking)


# keep only tracking-like missing requests
result_df = missing_df[missing_df["likely_tracking"]].copy()


# ─────────────────────────────────────────────
# CLEAN COLUMNS
# ─────────────────────────────────────────────
result_df = result_df[[
    "url", "method", "status", "mimeType", "domain"
]]

result_df["reason"] = "Present in HAR but missing in crawl + matches tracking heuristics"


# ─────────────────────────────────────────────
# SAVE OUTPUT
# ─────────────────────────────────────────────
result_df.to_csv(OUTPUT, index=False)

print("\n================ RESULT =================")
print(f"[✓] Total HAR requests          : {len(har_df)}")
print(f"[✓] Missing from crawl          : {len(missing_df)}")
print(f"[✓] Likely tracking (final)     : {len(result_df)}")
print(f"[✓] Saved to                    : {OUTPUT}")
print("========================================")