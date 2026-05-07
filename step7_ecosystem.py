"""
STEP 7 — Tracker Ecosystem Analysis
Web Privacy Project - ENGR-UH 4323 Spring 2026

PURPOSE:
  Build a bipartite graph of websites ↔ trackers, then analyze:
  - Whether tracking is concentrated (a few big trackers dominate)
  - Whether trackers appear together (co-occurrence / clustering)
  - What this tells us about the web tracking ecosystem

INSTALL DEPENDENCIES:
  pip install networkx matplotlib scipy scikit-learn

RUN: python step7_ecosystem.py
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend (no display needed)
import matplotlib.pyplot as plt
import networkx as nx
from collections import Counter
from urllib.parse import urlparse
from adblockparser import AdblockRules

DB_PATH = "./datadir/crawl.sqlite"

# ─────────────────────────────────────────────
# Load the tracking domains identified in Step 6
# (We re-run the detection here for self-containment)
# ─────────────────────────────────────────────
print("=" * 65)
print("  Step 7: Tracker Ecosystem Analysis")
print("=" * 65)

conn = sqlite3.connect(DB_PATH)
requests_df = pd.read_sql("""
    SELECT r.url, r.is_third_party_channel, sv.site_url
    FROM http_requests r
    JOIN site_visits sv ON r.visit_id = sv.visit_id;
""", conn)
conn.close()

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

requests_df["request_domain"] = requests_df["url"].apply(get_domain)

# ── Load rules (cached from Step 6) ─────────────────────────────────────────
def load_cached_rules(paths: list[str]) -> AdblockRules:
    lines = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines.extend(f.readlines())
        except FileNotFoundError:
            print(f"  [!] Filter list not found at {path}. Run Step 6 first.")
    return AdblockRules(lines)

print("[*] Loading cached filter lists from Step 6...")
rules = load_cached_rules([
    "./datadir/EasyList.txt",
    "./datadir/EasyPrivacy.txt",
])

print("[*] Flagging tracking requests...")
requests_df["is_tracking"] = requests_df["url"].apply(
    lambda u: rules.should_block(u) if u else False
)

# Keep only third-party tracking requests
tracking = requests_df[
    (requests_df["is_tracking"]) &
    (requests_df["is_third_party_channel"] == 1) &
    (requests_df["request_domain"] != "")
].copy()

print(f"[*] Third-party tracking requests: {len(tracking):,}")

# ─────────────────────────────────────────────
# BUILD BIPARTITE GRAPH
#
# HOW IT WORKS:
#   Nodes: websites (e.g., "nytimes.com") AND trackers (e.g., "doubleclick.net")
#   Edges: website → tracker (an edge means tracker was seen on that site)
#
# From this graph we can ask:
#   - Which trackers connect to the most sites? (high degree = dominant tracker)
#   - Which sites share the same set of trackers? (similarity clustering)
# ─────────────────────────────────────────────
print("\n[*] Building bipartite graph (sites ↔ trackers)...")

# Aggregate: unique (site, tracker) pairs
site_tracker_pairs = (
    tracking.groupby(["site_url", "request_domain"])
    .size()
    .reset_index(name="request_count")
)

# Create bipartite graph
B = nx.Graph()

sites = site_tracker_pairs["site_url"].unique()
trackers = site_tracker_pairs["request_domain"].unique()

# Add nodes with type labels (important for bipartite algorithms)
B.add_nodes_from(sites, bipartite="site")
B.add_nodes_from(trackers, bipartite="tracker")

# Add edges
for _, row in site_tracker_pairs.iterrows():
    B.add_edge(row["site_url"], row["request_domain"], weight=row["request_count"])

print(f"  Sites in graph   : {len(sites)}")
print(f"  Trackers in graph: {len(trackers)}")
print(f"  Edges            : {B.number_of_edges()}")

# ─────────────────────────────────────────────
# ANALYSIS 1: Tracker prevalence (reach)
# How many sites does each tracker appear on?
# ─────────────────────────────────────────────
print("\n[Analysis 1] Tracker Prevalence (reach across sites)")

tracker_reach = (
    site_tracker_pairs.groupby("request_domain")["site_url"]
    .nunique()
    .sort_values(ascending=False)
    .reset_index()
    .rename(columns={"site_url": "num_sites"})
)
tracker_reach["pct_sites"] = (tracker_reach["num_sites"] / len(sites) * 100).round(1)

print(tracker_reach.head(20).to_string(index=False))
tracker_reach.to_csv("./datadir/step7_tracker_reach.csv", index=False)

# ─────────────────────────────────────────────
# ANALYSIS 2: Concentration (Lorenz / top-N share)
#
# CONCEPT: If 5 trackers appear on 80% of sites, tracking is highly
# concentrated. This is similar to how income inequality is measured.
# ─────────────────────────────────────────────
print("\n[Analysis 2] Concentration")

total_tracker_appearances = tracker_reach["num_sites"].sum()
tracker_reach["cumulative_share"] = (
    tracker_reach["num_sites"].cumsum() / total_tracker_appearances * 100
)

top5_share = tracker_reach.head(5)["num_sites"].sum() / total_tracker_appearances * 100
top10_share = tracker_reach.head(10)["num_sites"].sum() / total_tracker_appearances * 100

print(f"  Top 5 trackers  account for {top5_share:.1f}% of all tracking appearances")
print(f"  Top 10 trackers account for {top10_share:.1f}% of all tracking appearances")
print(f"  Total unique trackers: {len(tracker_reach)}")
print(f"  Trackers on only 1 site: "
      f"{(tracker_reach['num_sites'] == 1).sum()} "
      f"({(tracker_reach['num_sites'] == 1).sum()/len(tracker_reach)*100:.1f}%)")

# ─────────────────────────────────────────────
# ANALYSIS 3: Co-occurrence matrix
#
# CONCEPT: Two trackers "co-occur" if they both appear on the same site.
# High co-occurrence suggests they belong to the same ad ecosystem
# (e.g., Google Analytics and DoubleClick often appear together).
# ─────────────────────────────────────────────
print("\n[Analysis 3] Tracker Co-occurrence")

# Build a site × tracker binary matrix
pivot = (
    site_tracker_pairs.pivot_table(
        index="site_url", columns="request_domain", values="request_count", fill_value=0
    )
    .clip(upper=1)  # binary: 1 if tracker present, 0 if not
)

# Only keep top 30 trackers (co-occurrence matrix gets huge otherwise)
top30 = tracker_reach.head(30)["request_domain"].tolist()
pivot_top = pivot[[c for c in top30 if c in pivot.columns]]

# Co-occurrence = how many sites have BOTH tracker A and tracker B
cooccurrence = pivot_top.T.dot(pivot_top)
print(f"  Co-occurrence matrix shape: {cooccurrence.shape}")

# Find highest co-occurring pairs (excluding diagonal)
cooc_vals = []
cols = list(cooccurrence.columns)
for i in range(len(cols)):
    for j in range(i+1, len(cols)):
        cooc_vals.append({
            "tracker_a": cols[i],
            "tracker_b": cols[j],
            "shared_sites": int(cooccurrence.iloc[i, j])
        })

cooc_df = pd.DataFrame(cooc_vals).sort_values("shared_sites", ascending=False)
print("\n  Top 10 most co-occurring tracker pairs:")
print(cooc_df.head(10).to_string(index=False))
cooc_df.to_csv("./datadir/step7_cooccurrence.csv", index=False)

# ─────────────────────────────────────────────
# VISUALISATION 1: Top 20 trackers bar chart
# ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
top20 = tracker_reach.head(20)
ax.barh(top20["request_domain"][::-1], top20["num_sites"][::-1], color="steelblue")
ax.set_xlabel("Number of sites tracker appears on")
ax.set_title("Top 20 Third-Party Trackers by Reach")
ax.axvline(x=len(sites) * 0.5, color="red", linestyle="--", label="50% of sites")
ax.legend()
plt.tight_layout()
plt.savefig("./datadir/step7_tracker_reach.png", dpi=150)
print("\n[✓] Bar chart saved to ./datadir/step7_tracker_reach.png")
plt.close()

# ─────────────────────────────────────────────
# VISUALISATION 2: Mini bipartite graph (top 10 trackers)
# Shows which major trackers appear on which sites
# ─────────────────────────────────────────────
try:
    top10_trackers = tracker_reach.head(10)["request_domain"].tolist()
    sub_edges = [
        (s, t)
        for s, t in B.edges()
        if t in top10_trackers
    ]
    G_sub = nx.Graph()
    G_sub.add_edges_from(sub_edges)

    site_nodes = [n for n in G_sub.nodes() if n not in top10_trackers]
    tracker_nodes = [n for n in G_sub.nodes() if n in top10_trackers]

    pos = nx.bipartite_layout(G_sub, tracker_nodes)
    fig, ax = plt.subplots(figsize=(12, 8))
    nx.draw_networkx_nodes(G_sub, pos, nodelist=tracker_nodes,
                           node_color="red", node_size=300, ax=ax)
    nx.draw_networkx_nodes(G_sub, pos, nodelist=site_nodes,
                           node_color="lightblue", node_size=50, ax=ax)
    nx.draw_networkx_labels(G_sub, pos,
                             labels={n: n for n in tracker_nodes},
                             font_size=7, ax=ax)
    nx.draw_networkx_edges(G_sub, pos, alpha=0.2, ax=ax)
    ax.set_title("Bipartite Graph: Sites (blue) ↔ Top 10 Trackers (red)")
    ax.axis("off")
    plt.tight_layout()
    plt.savefig("./datadir/step7_bipartite.png", dpi=150)
    print("[✓] Bipartite graph saved to ./datadir/step7_bipartite.png")
    plt.close()
except Exception as e:
    print(f"[!] Could not generate bipartite graph: {e}")

print("\n[✓] Step 7 complete. Results saved to ./datadir/")
