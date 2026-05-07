"""
STEP 5 — Tracking Cookies Analysis (FIXED VERSION)

Measures:
- Prevalence across sites
- First vs third-party context
- Whether set via HTTP or JavaScript
"""

import sqlite3
import pandas as pd
from urllib.parse import urlparse

DB_PATH = "./datadir/crawl.sqlite"
conn = sqlite3.connect(DB_PATH)

print("=" * 65)
print("  Step 5: Tracking Cookie Analysis (FINAL)")
print("=" * 65)

TRACKING_COOKIES = {
    "_ga": "Google Analytics",
    "_fbp": "Facebook Pixel",
    "__gads": "DoubleClick / Google Ads",
}

# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────
def get_domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except:
        return ""

def is_first_party(site_url, host):
    try:
        site = get_domain(site_url)
        cookie = host.lstrip(".")
        return site.endswith(cookie) or cookie.endswith(site)
    except:
        return False

def extract_cookie_names(headers):
    try:
        if not headers:
            return []
        data = eval(headers) if isinstance(headers, str) else headers
        cookies = []
        for h in data:
            if h[0].lower() == "set-cookie":
                cookie_name = h[1].split("=")[0]
                cookies.append(cookie_name)
        return cookies
    except:
        return []

# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────

# JavaScript cookies
js_df = pd.read_sql("""
    SELECT jc.visit_id, jc.host, jc.name, sv.site_url
    FROM javascript_cookies jc
    JOIN site_visits sv ON jc.visit_id = sv.visit_id
""", conn)

# HTTP cookies (from response headers)
http_df = pd.read_sql("""
    SELECT hr.visit_id, hr.url, hr.headers, sv.site_url
    FROM http_responses hr
    JOIN site_visits sv ON hr.visit_id = sv.visit_id
    WHERE hr.headers LIKE '%Set-Cookie%'
""", conn)

http_df["cookie_names"] = http_df["headers"].apply(extract_cookie_names)

total_sites = js_df["site_url"].nunique()
print(f"[*] Total sites: {total_sites}")

results = []

# ─────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────
for cookie in TRACKING_COOKIES:
    print(f"\n{'─'*60}")
    print(f"Cookie: {cookie}")
    print(f"{'─'*60}")

    # JS matches
    js_matches = js_df[js_df["name"] == cookie].copy()

    # HTTP matches
    http_matches = http_df[http_df["cookie_names"].apply(lambda x: cookie in x)].copy()

    # Sites
    js_sites = set(js_matches["site_url"])
    http_sites = set(http_matches["site_url"])
    all_sites = js_sites.union(http_sites)

    prevalence = (len(all_sites) / total_sites * 100) if total_sites > 0 else 0

    print(f"Found on {len(all_sites)} / {total_sites} sites ({prevalence:.1f}%)")

    # ── First vs Third Party ───────────────────
    fp_sites = set()
    tp_sites = set()

    for _, row in js_matches.iterrows():
        if is_first_party(row["site_url"], row["host"]):
            fp_sites.add(row["site_url"])
        else:
            tp_sites.add(row["site_url"])

    for _, row in http_matches.iterrows():
        if is_first_party(row["site_url"], row["url"]):
            fp_sites.add(row["site_url"])
        else:
            tp_sites.add(row["site_url"])

    print(f"First-party sites : {len(fp_sites)}")
    print(f"Third-party sites : {len(tp_sites)}")

    # ── Set via JS vs HTTP ─────────────────────
    print(f"Set via JavaScript : {len(js_sites)} sites")
    print(f"Set via HTTP       : {len(http_sites)} sites")

    results.append({
        "cookie": cookie,
        "sites_found": len(all_sites),
        "prevalence_pct": round(prevalence, 1),
        "first_party_sites": len(fp_sites),
        "third_party_sites": len(tp_sites),
        "set_via_js_sites": len(js_sites),
        "set_via_http_sites": len(http_sites),
    })

# ─────────────────────────────────────────────
# Output summary
# ─────────────────────────────────────────────
print("\n" + "=" * 65)
print("SUMMARY")
print("=" * 65)

summary_df = pd.DataFrame(results)
print(summary_df.to_string(index=False))

summary_df.to_csv("./datadir/step5_cookie_summary.csv", index=False)
print("\n[✓] Saved to ./datadir/step5_cookie_summary.csv")

conn.close()