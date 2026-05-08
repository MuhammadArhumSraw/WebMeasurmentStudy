"""
STEP 6 — Tracking Requests Analysis
Web Privacy Project - ENGR-UH 4323 Spring 2026
"""

import sqlite3
import requests
import pandas as pd
from urllib.parse import urlparse
from adblockparser import AdblockRules
import time
import os

DB_PATH = "./datadir/crawl.sqlite"

# ─────────────────────────────────────────────
# FILTER LISTS (UNCHANGED)
# ─────────────────────────────────────────────
FILTER_LISTS = {
    "EasyList": "https://easylist.to/easylist/easylist.txt",
    "EasyPrivacy": "https://easylist.to/easylist/easyprivacy.txt",
}

REGIONAL_LISTS = {
    "Liste_AR": "https://easylist-downloads.adblockplus.org/Liste_AR.txt",
    "EasyList_China": "https://easylist-downloads.adblockplus.org/easylistchina.txt",
}

# ─────────────────────────────────────────────
# DOWNLOAD FILTER LISTS
# ─────────────────────────────────────────────
def download_filter_list(name: str, url: str) -> list[str]:
    cache_path = f"./datadir/{name}.txt"

    try:
        if os.path.exists(cache_path):
            print(f"  [cache] Using cached {name}")
            with open(cache_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.readlines()

        print(f"  [download] Fetching {name}...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(resp.text)

        lines = resp.text.splitlines()
        print(f"  [✓] {name}: {len(lines):,} rules")
        return lines

    except Exception as e:
        print(f"  [!] Failed {name}: {e}")
        return []


# ─────────────────────────────────────────────
# BUILD RULES
# ─────────────────────────────────────────────
def build_rules(list_names, all_lists):
    combined_rules = []

    for name in list_names:
        if name in all_lists:
            combined_rules.extend(download_filter_list(name, all_lists[name]))

    print(f"  [*] Total rules loaded: {len(combined_rules):,}")

    return AdblockRules(combined_rules, use_re2=False)


# ─────────────────────────────────────────────
# FAST TRACKING CHECK (WITH DEBUG + SPEED)
# ─────────────────────────────────────────────
def check_tracking_fast(df, rules):

    start_time = time.time()

    temp = pd.DataFrame({
        "url": df["url"].astype(str),
        "tp": df["is_third_party_channel"].astype(bool),
        "rtype": df["resource_type"].astype(str),
    })

    unique = temp.drop_duplicates()
    total = len(unique)

    print(f"    [INFO] Total rows    : {len(temp):,}")
    print(f"    [INFO] Unique checks : {total:,}")
    print(f"    [INFO] Starting scan...\n")

    cache = {}

    for i, row in enumerate(unique.itertuples(index=False), start=1):

        if i == 1 or i % 2000 == 0:

            elapsed = time.time() - start_time
            speed = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / speed if speed > 0 else 0

            print(
                f"    ✔ {i:,}/{total:,} "
                f"({i/total*100:.1f}%) | "
                f"{speed:.1f} req/s | "
                f"ETA: {eta/60:.1f} min"
            )

        options = {
            "third-party": row.tp,
            row.rtype: True
        }

        try:
            cache[(row.url, row.tp, row.rtype)] = rules.should_block(
                row.url,
                options
            )
        except:
            cache[(row.url, row.tp, row.rtype)] = False

    print("\n    [DONE] Reconstructing results...")

    result = [
        cache[(u, tp, rt)]
        for u, tp, rt in zip(
            temp["url"],
            temp["tp"],
            temp["rtype"]
        )
    ]

    elapsed = time.time() - start_time

    print("\n    ===============================")
    print(f"    COMPLETED IN : {elapsed/60:.2f} minutes")
    print(f"    SPEED        : {total/elapsed:.1f} checks/sec")
    print("    ===============================\n")

    return result


# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
print("=" * 65)
print("  Step 6: Tracking Requests Analysis")
print("=" * 65)

conn = sqlite3.connect(DB_PATH)

requests_df = pd.read_sql("""
    SELECT
        r.visit_id,
        r.url,
        r.top_level_url,
        r.is_third_party_channel,
        r.resource_type,
        sv.site_url
    FROM http_requests r
    JOIN site_visits sv ON r.visit_id = sv.visit_id;
""", conn)

conn.close()

print(f"[*] Total HTTP requests: {len(requests_df):,}")
print(f"[*] Unique sites: {requests_df['site_url'].nunique()}")

total_sites = requests_df["site_url"].nunique()


# ─────────────────────────────────────────────
# DOMAIN EXTRACTION
# ─────────────────────────────────────────────
def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except:
        return ""


print("\n[*] Extracting domains...")

requests_df["request_domain"] = requests_df["url"].apply(get_domain)
requests_df["top_domain"] = requests_df["top_level_url"].apply(get_domain)


# ─────────────────────────────────────────────
# PHASE A
# ─────────────────────────────────────────────
all_lists = {**FILTER_LISTS, **REGIONAL_LISTS}

print("\n[Phase A] EasyList + EasyPrivacy")

rules_global = build_rules(
    ["EasyList", "EasyPrivacy"],
    all_lists
)

print("[*] Checking requests...")

requests_df["tracked_global"] = check_tracking_fast(
    requests_df,
    rules_global
)


# ─────────────────────────────────────────────
# PHASE B
# ─────────────────────────────────────────────
print("\n[Phase B] Global + Regional Lists")

rules_with_regional = build_rules(
    ["EasyList", "EasyPrivacy", "Liste_AR", "EasyList_China"],
    all_lists
)

print("[*] Checking requests...")

requests_df["tracked_regional"] = check_tracking_fast(
    requests_df,
    rules_with_regional
)


# ─────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────
def compute_metrics(df: pd.DataFrame, col: str, label: str):

    print(f"\n{'─'*60}")
    print(f"  Results: {label}")
    print(f"{'─'*60}")

    tracked = df[df[col]]

    sites_any_tracking = tracked["site_url"].nunique()

    print(f"  a. Sites with any tracking: "
          f"{sites_any_tracking}/{total_sites} "
          f"({sites_any_tracking/total_sites*100:.1f}%)")

    first_party = tracked[tracked["is_third_party_channel"] == 0]
    sites_fp = first_party["site_url"].nunique()

    print(f"  b. Sites with 1st-party tracking: "
          f"{sites_fp}/{total_sites} "
          f"({sites_fp/total_sites*100:.1f}%)")

    third_party = tracked[tracked["is_third_party_channel"] == 1]
    sites_tp = third_party["site_url"].nunique()

    print(f"  c. Sites with 3rd-party tracking: "
          f"{sites_tp}/{total_sites} "
          f"({sites_tp/total_sites*100:.1f}%)")

    per_site = (
        tracked.groupby("site_url")["request_domain"]
        .nunique()
        .reset_index()
        .rename(columns={"request_domain": "unique_tracking_domains"})
    )

    print(f"\n  d. Tracking domains per site:")
    print(f"     Mean   : {per_site['unique_tracking_domains'].mean():.1f}")
    print(f"     Median : {per_site['unique_tracking_domains'].median():.1f}")
    print(f"     Max    : {per_site['unique_tracking_domains'].max()}")
    print(f"     Min    : {per_site['unique_tracking_domains'].min()}")

    top_domains = (
        tracked.groupby("request_domain")["site_url"]
        .nunique()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
        .rename(columns={"site_url": "sites_seen_on"})
    )

    print(f"\n  e. Top 15 tracking domains:")
    print(top_domains.to_string(index=False))


compute_metrics(requests_df, "tracked_global", "Global Lists Only")
compute_metrics(requests_df, "tracked_regional", "Global + Regional Lists")


# ─────────────────────────────────────────────
# COMPARISON
# ─────────────────────────────────────────────
print("\n" + "=" * 65)
print("  COMPARISON: Global vs Global + Regional")
print("=" * 65)

only_regional = requests_df[
    requests_df["tracked_regional"] & ~requests_df["tracked_global"]
]

print(f"  Requests only by regional: {len(only_regional):,}")
print(f"  Unique URLs only regional: {only_regional['url'].nunique():,}")

if not only_regional.empty:
    print("  Top extra domains:")
    print(only_regional["request_domain"].value_counts().head(10).to_string())
else:
    print("  (No additional requests detected)")

print("\n[✓] Step 6 complete")