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
# LOAD HTTP REQUESTS
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
    WHERE sv.site_url LIKE '%salim.webprivacylab%';
""", conn)

# ─────────────────────────────────────────────
# LOAD JS CALLS
# ─────────────────────────────────────────────
js_df = pd.read_sql(f"""
    SELECT j.script_url, j.symbol, j.operation, j.value
    FROM javascript j
    JOIN site_visits sv ON j.visit_id = sv.visit_id
    WHERE sv.site_url LIKE '%salim.webprivacylab%';
""", conn)

conn.close()

print(f"[*] HTTP requests: {len(http_df)}")
print(f"[*] JS calls: {len(js_df)}")

# ─────────────────────────────────────────────
# DOMAIN PARSING
# ─────────────────────────────────────────────
def get_domain(url):
    try:
        return urlparse(url).netloc
    except:
        return ""

http_df["request_domain"] = http_df["url"].apply(get_domain)

# ─────────────────────────────────────────────
# FILTER LIST CLASSIFICATION
# ─────────────────────────────────────────────
def load_rules():
    lines = []
    for path in ["./datadir/EasyList.txt", "./datadir/EasyPrivacy.txt"]:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines += f.readlines()
        except:
            pass
    return AdblockRules(lines) if lines else None

rules = load_rules()

http_df["flagged_by_filter"] = http_df["url"].apply(
    rules.should_block if rules else (lambda x: False)
)

# ─────────────────────────────────────────────
# CLASSIFY TYPE (IMPORTANT FIX)
# ─────────────────────────────────────────────
def classify(row):
    if row["flagged_by_filter"]:
        return "TRACKING_FILTER"

    url = row["url"].lower()

    if any(x in url for x in ["track", "pixel", "collect", "beacon", "analytics"]):
        return "TRACKING_HEURISTIC"

    if row["resource_type"] in ["beacon", "image"] and row["is_third_party_channel"]:
        return "SUSPICIOUS_TRACKING"

    return "CLEAN_CRAWLING"

http_df["classification"] = http_df.apply(classify, axis=1)

# ─────────────────────────────────────────────
# SUSPICIOUS DETECTION DETAILS
# ─────────────────────────────────────────────
def reason(row):
    url = row["url"].lower()
    reasons = []

    if "track" in url:
        reasons.append("contains /track")
    if "beacon" in url:
        reasons.append("beacon request")
    if row["resource_type"] == "image" and row["is_third_party_channel"]:
        reasons.append("possible pixel tracker")

    return "; ".join(reasons)

http_df["manual_reason"] = http_df.apply(reason, axis=1)

# ─────────────────────────────────────────────
# FINGERPRINTING SUMMARY
# ─────────────────────────────────────────────
CANVAS_WRITE = {
    "CanvasRenderingContext2D.fillText",
    "CanvasRenderingContext2D.strokeText"
}
CANVAS_READ = {
    "HTMLCanvasElement.toDataURL",
    "CanvasRenderingContext2D.getImageData"
}

AUDIO_CTX = "AudioContext"
AUDIO_READ = "AudioBuffer.getChannelData"

has_canvas = (
    js_df["symbol"].isin(CANVAS_WRITE).any() and
    js_df["symbol"].isin(CANVAS_READ).any()
)

has_audio = (
    js_df["symbol"].str.contains(AUDIO_CTX, na=False).any() and
    js_df["symbol"].str.contains(AUDIO_READ, na=False).any()
)

# ─────────────────────────────────────────────
# SAVE CSV OUTPUTS (MAIN FIX)
# ─────────────────────────────────────────────

http_df.to_csv("./datadir/step9_all_requests.csv", index=False)

http_df[http_df["classification"] == "TRACKING_FILTER"] \
    .to_csv("./datadir/step9_tracking_filter.csv", index=False)

http_df[http_df["classification"] == "TRACKING_HEURISTIC"] \
    .to_csv("./datadir/step9_tracking_heuristic.csv", index=False)

http_df[http_df["classification"] == "SUSPICIOUS_TRACKING"] \
    .to_csv("./datadir/step9_suspicious_manual.csv", index=False)

summary = pd.DataFrame([{
    "test_url": TEST_URL,
    "total_requests": len(http_df),
    "tracking_filter": (http_df["classification"] == "TRACKING_FILTER").sum(),
    "tracking_heuristic": (http_df["classification"] == "TRACKING_HEURISTIC").sum(),
    "suspicious_manual": (http_df["classification"] == "SUSPICIOUS_TRACKING").sum(),
    "clean_crawling": (http_df["classification"] == "CLEAN_CRAWLING").sum(),
    "canvas_fp": has_canvas,
    "audio_fp": has_audio
}])

summary.to_csv("./datadir/step9_summary.csv", index=False)

# ─────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────
print("\n================ OUTPUT SAVED =================")
print("[✓] step9_all_requests.csv")
print("[✓] step9_tracking_filter.csv")
print("[✓] step9_tracking_heuristic.csv")
print("[✓] step9_suspicious_manual.csv")
print("[✓] step9_summary.csv")
print("===============================================")