"""
STEP 6 — Metrics From step7_all_tracking_requests.csv

This script recomputes ALL required metrics using the
recovered Step 7 tracking file instead of relying on
OpenWPM's broken is_third_party_channel field.

INPUT:
    ./datadir/step7_all_tracking_requests.csv

REQUIRED COLUMNS:
    url
    site_url
    request_domain
    is_tracking

OUTPUT:
    Prints all Step 6 metrics
"""

import pandas as pd
from urllib.parse import urlparse

CSV_PATH = "./datadir/step7_all_tracking_requests.csv"


# ─────────────────────────────────────────────
# DOMAIN EXTRACTION
# ─────────────────────────────────────────────
def get_domain(url):
    try:
        return urlparse(str(url)).netloc.lower()
    except:
        return ""


# ─────────────────────────────────────────────
# LOAD CSV
# ─────────────────────────────────────────────
print("=" * 65)
print(" STEP 6 METRICS FROM RECOVERED STEP 7 FILE")
print("=" * 65)

df = pd.read_csv(CSV_PATH)

print(f"[*] Rows loaded: {len(df):,}")

# ensure bool
df["is_tracking"] = (
    df["is_tracking"]
    .astype(str)
    .str.lower()
    .map({
        "true": True,
        "false": False
    })
)

print("[✓] Parsed tracking column")


# ─────────────────────────────────────────────
# EXTRACT TOP DOMAIN
# ─────────────────────────────────────────────
print("[*] Computing party relationships...")

df["top_domain"] = df["site_url"].apply(get_domain)

# recompute request_domain if missing
if "request_domain" not in df.columns:
    df["request_domain"] = df["url"].apply(get_domain)

df["request_domain"] = (
    df["request_domain"]
    .fillna("")
    .astype(str)
    .str.lower()
)

# third-party comparison
df["is_third_party"] = (
    df["request_domain"] != df["top_domain"]
)

print("[✓] Third-party classification complete")


# ─────────────────────────────────────────────
# FILTER TRACKING ONLY
# ─────────────────────────────────────────────
tracked = df[df["is_tracking"] == True]

print(f"[*] Tracking requests: {len(tracked):,}")

total_sites = df["site_url"].nunique()

print(f"[*] Total sites: {total_sites}")


# ─────────────────────────────────────────────
# a. ANY TRACKING
# ─────────────────────────────────────────────
sites_any = tracked["site_url"].nunique()

print("\n" + "─" * 60)
print("a. Fraction of sites with any tracking")
print("─" * 60)

print(
    f"{sites_any}/{total_sites} "
    f"({sites_any/total_sites*100:.1f}%)"
)


# ─────────────────────────────────────────────
# b. FIRST PARTY TRACKING
# ─────────────────────────────────────────────
first_party = tracked[
    tracked["is_third_party"] == False
]

sites_fp = first_party["site_url"].nunique()

print("\n" + "─" * 60)
print("b. Fraction with first-party tracking")
print("─" * 60)

print(
    f"{sites_fp}/{total_sites} "
    f"({sites_fp/total_sites*100:.1f}%)"
)


# ─────────────────────────────────────────────
# c. THIRD PARTY TRACKING
# ─────────────────────────────────────────────
third_party = tracked[
    tracked["is_third_party"] == True
]

sites_tp = third_party["site_url"].nunique()

print("\n" + "─" * 60)
print("c. Fraction with third-party tracking")
print("─" * 60)

print(
    f"{sites_tp}/{total_sites} "
    f"({sites_tp/total_sites*100:.1f}%)"
)


# ─────────────────────────────────────────────
# d. TRACKING DOMAINS PER SITE
# ─────────────────────────────────────────────
per_site = (
    tracked.groupby("site_url")["request_domain"]
    .nunique()
    .reset_index()
    .rename(columns={
        "request_domain":
        "unique_tracking_domains"
    })
)

print("\n" + "─" * 60)
print("d. Tracking domains per site")
print("─" * 60)

print(
    f"Mean   : "
    f"{per_site['unique_tracking_domains'].mean():.1f}"
)

print(
    f"Median : "
    f"{per_site['unique_tracking_domains'].median():.1f}"
)

print(
    f"Max    : "
    f"{per_site['unique_tracking_domains'].max()}"
)

print(
    f"Min    : "
    f"{per_site['unique_tracking_domains'].min()}"
)


# ─────────────────────────────────────────────
# e. TOP TRACKING DOMAINS
# ─────────────────────────────────────────────
top_domains = (
    tracked.groupby("request_domain")["site_url"]
    .nunique()
    .sort_values(ascending=False)
    .head(15)
    .reset_index()
    .rename(columns={
        "site_url":
        "sites_seen_on"
    })
)

print("\n" + "─" * 60)
print("e. Most common tracking domains")
print("─" * 60)

print(top_domains.to_string(index=False))


# ─────────────────────────────────────────────
# SAVE OUTPUTS
# ─────────────────────────────────────────────
per_site.to_csv(
    "./datadir/step6_tracking_domains_per_site.csv",
    index=False
)

top_domains.to_csv(
    "./datadir/step6_top_tracking_domains.csv",
    index=False
)

print("\n[✓] CSV outputs saved")

print("\n[✓] Step 6 metrics recomputation complete")
