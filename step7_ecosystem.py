"""
STEP 7 — Tracker Ecosystem Analysis
Web Privacy Project - ENGR-UH 4323 Spring 2026

PURPOSE:
  Build a bipartite graph of websites ↔ trackers, then analyze:
  - Whether tracking is concentrated
  - Whether trackers appear together
  - Tracker ecosystem structure

EXTRA FEATURES ADDED:
  - Progress/debug logging
  - Faster tracking detection (dedup + cache)
  - CSV exports for ALL tracker-site mappings
  - First-party vs third-party tracker exports
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx

from urllib.parse import urlparse
from adblockparser import AdblockRules

import os
import time

DB_PATH = "./datadir/crawl.sqlite"

# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────
print("=" * 65)
print("  Step 7: Tracker Ecosystem Analysis")
print("=" * 65)

overall_start = time.time()

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
print("\n[*] Loading HTTP requests from SQLite...")

conn = sqlite3.connect(DB_PATH)

requests_df = pd.read_sql("""
    SELECT
        r.url,
        r.is_third_party_channel,
        sv.site_url
    FROM http_requests r
    JOIN site_visits sv
        ON r.visit_id = sv.visit_id;
""", conn)

conn.close()

print(f"  Total requests loaded: {len(requests_df):,}")
print(f"  Unique sites         : {requests_df['site_url'].nunique()}")

# ─────────────────────────────────────────────
# DOMAIN EXTRACTION
# ─────────────────────────────────────────────
def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

print("\n[*] Extracting request domains...")

requests_df["request_domain"] = (
    requests_df["url"]
    .astype(str)
    .apply(get_domain)
)

# ─────────────────────────────────────────────
# LOAD FILTER LISTS
# ─────────────────────────────────────────────
def load_cached_rules(paths: list[str]) -> AdblockRules:

    lines = []

    for path in paths:

        try:
            print(f"  Loading: {path}")

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                file_lines = f.readlines()

            print(f"    {len(file_lines):,} rules")

            lines.extend(file_lines)

        except FileNotFoundError:
            print(f"  [!] Missing filter list: {path}")

    print(f"\n[*] Total loaded rules: {len(lines):,}")

    return AdblockRules(lines, use_re2=False)


print("\n[*] Loading cached filter lists from Step 6...")

rules = load_cached_rules([
    "./datadir/EasyList.txt",
    "./datadir/EasyPrivacy.txt",
    "./datadir/Liste_AR.txt",
    "./datadir/EasyList_China.txt",
])

# ─────────────────────────────────────────────
# FAST TRACKING DETECTION
# ─────────────────────────────────────────────
def detect_tracking_fast(df, rules):

    start = time.time()

    temp = pd.DataFrame({
        "url": df["url"].astype(str),
    })

    unique_urls = temp["url"].drop_duplicates()

    total = len(unique_urls)

    print("\n[*] Detecting tracking requests...")
    print(f"  Total rows    : {len(df):,}")
    print(f"  Unique URLs   : {total:,}")

    cache = {}

    for i, url in enumerate(unique_urls, start=1):

        if i == 1 or i % 2000 == 0:

            elapsed = time.time() - start
            speed = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / speed if speed > 0 else 0

            print(
                f"  ✔ {i:,}/{total:,} "
                f"({i/total*100:.1f}%) | "
                f"{speed:.1f} urls/sec | "
                f"ETA: {eta/60:.1f} min"
            )

        try:
            cache[url] = rules.should_block(url)
        except:
            cache[url] = False

    print("\n[*] Reconstructing results...")

    result = temp["url"].map(cache)

    elapsed = time.time() - start

    print("\n  ===============================")
    print(f"  DONE IN : {elapsed/60:.2f} minutes")
    print(f"  SPEED   : {total/elapsed:.1f} urls/sec")
    print("  ===============================")

    return result


requests_df["is_tracking"] = detect_tracking_fast(
    requests_df,
    rules
)

# ─────────────────────────────────────────────
# SAVE ALL TRACKING REQUESTS
# ─────────────────────────────────────────────
print("\n[*] Saving raw tracking datasets...")

all_tracking = requests_df[
    (requests_df["is_tracking"]) &
    (requests_df["request_domain"] != "")
].copy()

third_party_tracking = all_tracking[
    all_tracking["is_third_party_channel"] == 1
].copy()

first_party_tracking = all_tracking[
    all_tracking["is_third_party_channel"] == 0
].copy()

# Save complete datasets
all_tracking.to_csv(
    "./datadir/step7_all_tracking_requests.csv",
    index=False
)

third_party_tracking.to_csv(
    "./datadir/step7_third_party_tracking.csv",
    index=False
)

first_party_tracking.to_csv(
    "./datadir/step7_first_party_tracking.csv",
    index=False
)

print(f"  Saved all tracking requests")
print(f"  Saved third-party tracking")
print(f"  Saved first-party tracking")

# ─────────────────────────────────────────────
# TRACKER ↔ SITE MAPPING EXPORT
# ─────────────────────────────────────────────
print("\n[*] Building tracker-site mapping...")

tracker_site_map = (
    all_tracking.groupby([
        "site_url",
        "request_domain",
        "is_third_party_channel"
    ])
    .size()
    .reset_index(name="request_count")
)

tracker_site_map["party_type"] = np.where(
    tracker_site_map["is_third_party_channel"] == 1,
    "third_party",
    "first_party"
)

tracker_site_map.to_csv(
    "./datadir/step7_tracker_site_mapping.csv",
    index=False
)

print(f"  Mapping rows: {len(tracker_site_map):,}")

# ─────────────────────────────────────────────
# KEEP ONLY THIRD-PARTY TRACKERS
# ─────────────────────────────────────────────
tracking = tracker_site_map[
    tracker_site_map["party_type"] == "third_party"
].copy()

print(f"\n[*] Third-party tracker relations: {len(tracking):,}")

# ─────────────────────────────────────────────
# BUILD BIPARTITE GRAPH
# ─────────────────────────────────────────────
print("\n[*] Building bipartite graph...")

B = nx.Graph()

sites = tracking["site_url"].unique()
trackers = tracking["request_domain"].unique()

B.add_nodes_from(sites, bipartite="site")
B.add_nodes_from(trackers, bipartite="tracker")

for i, row in enumerate(tracking.itertuples(index=False), start=1):

    if i % 5000 == 0:
        print(f"  Added {i:,}/{len(tracking):,} edges")

    B.add_edge(
        row.site_url,
        row.request_domain,
        weight=row.request_count
    )

print(f"\n  Sites in graph    : {len(sites)}")
print(f"  Trackers in graph : {len(trackers)}")
print(f"  Edges             : {B.number_of_edges()}")

# ─────────────────────────────────────────────
# ANALYSIS 1: TRACKER REACH
# ─────────────────────────────────────────────
print("\n[Analysis 1] Tracker Prevalence")

tracker_reach = (
    tracking.groupby("request_domain")["site_url"]
    .nunique()
    .sort_values(ascending=False)
    .reset_index()
    .rename(columns={"site_url": "num_sites"})
)

tracker_reach["pct_sites"] = (
    tracker_reach["num_sites"] / len(sites) * 100
).round(1)

print("\nTop 20 trackers:\n")
print(tracker_reach.head(20).to_string(index=False))

tracker_reach.to_csv(
    "./datadir/step7_tracker_reach.csv",
    index=False
)

# ─────────────────────────────────────────────
# ANALYSIS 2: CONCENTRATION
# ─────────────────────────────────────────────
print("\n[Analysis 2] Concentration")

total_tracker_appearances = tracker_reach["num_sites"].sum()

tracker_reach["cumulative_share"] = (
    tracker_reach["num_sites"].cumsum()
    / total_tracker_appearances
    * 100
)

top5_share = (
    tracker_reach.head(5)["num_sites"].sum()
    / total_tracker_appearances
    * 100
)

top10_share = (
    tracker_reach.head(10)["num_sites"].sum()
    / total_tracker_appearances
    * 100
)

print(f"  Top 5 trackers  : {top5_share:.1f}%")
print(f"  Top 10 trackers : {top10_share:.1f}%")

single_site = (tracker_reach["num_sites"] == 1).sum()

print(
    f"  Trackers on only 1 site: "
    f"{single_site} "
    f"({single_site/len(tracker_reach)*100:.1f}%)"
)

# ─────────────────────────────────────────────
# ANALYSIS 3: CO-OCCURRENCE
# ─────────────────────────────────────────────
print("\n[Analysis 3] Co-occurrence Matrix")

pivot = (
    tracking.pivot_table(
        index="site_url",
        columns="request_domain",
        values="request_count",
        fill_value=0
    )
    .clip(upper=1)
)

top30 = tracker_reach.head(30)["request_domain"].tolist()

pivot_top = pivot[
    [c for c in top30 if c in pivot.columns]
]

cooccurrence = pivot_top.T.dot(pivot_top)

print(f"  Matrix shape: {cooccurrence.shape}")

cooc_vals = []

cols = list(cooccurrence.columns)

for i in range(len(cols)):

    for j in range(i + 1, len(cols)):

        cooc_vals.append({
            "tracker_a": cols[i],
            "tracker_b": cols[j],
            "shared_sites": int(cooccurrence.iloc[i, j])
        })

cooc_df = (
    pd.DataFrame(cooc_vals)
    .sort_values("shared_sites", ascending=False)
)

print("\nTop 10 co-occurring tracker pairs:\n")
print(cooc_df.head(10).to_string(index=False))

cooc_df.to_csv(
    "./datadir/step7_cooccurrence.csv",
    index=False
)

# ─────────────────────────────────────────────
# VISUALIZATION 1
# ─────────────────────────────────────────────
print("\n[*] Generating tracker reach chart...")

fig, ax = plt.subplots(figsize=(10, 6))

top20 = tracker_reach.head(20)

ax.barh(
    top20["request_domain"][::-1],
    top20["num_sites"][::-1]
)

ax.set_xlabel("Number of sites tracker appears on")
ax.set_title("Top 20 Third-Party Trackers by Reach")

ax.axvline(
    x=len(sites) * 0.5,
    linestyle="--"
)

plt.tight_layout()

plt.savefig(
    "./datadir/step7_tracker_reach.png",
    dpi=150
)

plt.close()

print("  Saved: step7_tracker_reach.png")

# ─────────────────────────────────────────────
# VISUALIZATION 2
# ─────────────────────────────────────────────
print("\n[*] Generating bipartite graph...")

try:

    top10_trackers = (
        tracker_reach.head(10)["request_domain"]
        .tolist()
    )

    sub_edges = [
        (s, t)
        for s, t in B.edges()
        if t in top10_trackers
    ]

    G_sub = nx.Graph()
    G_sub.add_edges_from(sub_edges)

    site_nodes = [
        n for n in G_sub.nodes()
        if n not in top10_trackers
    ]

    tracker_nodes = [
        n for n in G_sub.nodes()
        if n in top10_trackers
    ]

    pos = nx.bipartite_layout(
        G_sub,
        tracker_nodes
    )

    fig, ax = plt.subplots(figsize=(12, 8))

    nx.draw_networkx_nodes(
        G_sub,
        pos,
        nodelist=tracker_nodes,
        node_size=300,
        ax=ax
    )

    nx.draw_networkx_nodes(
        G_sub,
        pos,
        nodelist=site_nodes,
        node_size=50,
        ax=ax
    )

    nx.draw_networkx_labels(
        G_sub,
        pos,
        labels={n: n for n in tracker_nodes},
        font_size=7,
        ax=ax
    )

    nx.draw_networkx_edges(
        G_sub,
        pos,
        alpha=0.2,
        ax=ax
    )

    ax.set_title(
        "Bipartite Graph: Sites ↔ Top 10 Trackers"
    )

    ax.axis("off")

    plt.tight_layout()

    plt.savefig(
        "./datadir/step7_bipartite.png",
        dpi=150
    )

    plt.close()

    print("  Saved: step7_bipartite.png")

except Exception as e:
    print(f"[!] Could not generate graph: {e}")

# ─────────────────────────────────────────────
# FINAL
# ─────────────────────────────────────────────
elapsed_total = time.time() - overall_start

print("\n" + "=" * 65)
print("  STEP 7 COMPLETE")
print("=" * 65)

print(f"Total runtime: {elapsed_total/60:.2f} minutes")

print("\nSaved CSV files:")
print("  - step7_all_tracking_requests.csv")
print("  - step7_first_party_tracking.csv")
print("  - step7_third_party_tracking.csv")
print("  - step7_tracker_site_mapping.csv")
print("  - step7_tracker_reach.csv")
print("  - step7_cooccurrence.csv")

print("\nSaved visualizations:")
print("  - step7_tracker_reach.png")
print("  - step7_bipartite.png")

print("\n[✓] Results saved to ./datadir/")