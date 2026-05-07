"""
STEP 6 + 7 — Combined (FULL OUTPUT VERSION)
"""

import sqlite3
import requests
import pandas as pd
import numpy as np
import os
from urllib.parse import urlparse
from adblockparser import AdblockRules

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx


DB_PATH = "./datadir/crawl.sqlite"


# ─────────────────────────────────────────────
# FILTER LISTS
# ─────────────────────────────────────────────
FILTER_LISTS = {
    "EasyList": "https://easylist.to/easylist/easylist.txt",
    "EasyPrivacy": "https://easylist.to/easylist/easyprivacy.txt",
}

REGIONAL_LISTS = {
    "Liste_AR": "https://easylist-downloads.adblockplus.org/Liste_AR.txt",
    "IndianList": "https://easylist-downloads.adblockplus.org/indianlist.txt",
}


# ─────────────────────────────────────────────
# DOWNLOAD + BUILD RULES
# ─────────────────────────────────────────────
def download_filter_list(name, url):
    path = f"./datadir/{name}.txt"

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    with open(path, "w", encoding="utf-8") as f:
        f.write(resp.text)

    return resp.text.splitlines()


def build_rules(names, all_lists):
    rules = []
    for n in names:
        rules.extend(download_filter_list(n, all_lists[n]))
    return AdblockRules(rules)


# ─────────────────────────────────────────────
# FAST CHECK
# ─────────────────────────────────────────────
def check_tracking_fast(df, rules):
    res = []
    append = res.append

    urls = df["url"].values
    is_tp = df["is_third_party_channel"].values
    rtypes = df["resource_type"].values

    for i in range(len(df)):
        options = {
            "third-party": bool(is_tp[i]),
            "script": rtypes[i] == "script",
            "image": rtypes[i] == "image",
            "xmlhttprequest": rtypes[i] in ("xmlhttprequest", "xhr"),
        }
        try:
            append(rules.should_block(urls[i], options))
        except:
            append(False)

    return res


# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)

df = pd.read_sql("""
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

total_sites = df["site_url"].nunique()


# ─────────────────────────────────────────────
# DOMAIN EXTRACTION
# ─────────────────────────────────────────────
def get_domain(url):
    try:
        return urlparse(url).netloc
    except:
        return ""

df["request_domain"] = df["url"].apply(get_domain)


# ─────────────────────────────────────────────
# BUILD RULES ONCE
# ─────────────────────────────────────────────
all_lists = {**FILTER_LISTS, **REGIONAL_LISTS}

rules_global = build_rules(["EasyList", "EasyPrivacy"], all_lists)
rules_regional = build_rules(
    ["EasyList", "EasyPrivacy", "Liste_AR", "IndianList"],
    all_lists
)


# ─────────────────────────────────────────────
# DETECTION ONCE PER RULESET
# ─────────────────────────────────────────────
df["tracked_global"] = check_tracking_fast(df, rules_global)
df["tracked_regional"] = check_tracking_fast(df, rules_regional)


# ─────────────────────────────────────────────
# STEP 6 METRICS (UNCHANGED OUTPUTS)
# ─────────────────────────────────────────────
def compute_metrics(df, col, label):
    tracked = df[df[col]]

    sites_any = tracked["site_url"].nunique()
    first_party = tracked[tracked["is_third_party_channel"] == 0]
    third_party = tracked[tracked["is_third_party_channel"] == 1]

    per_site = (
        tracked.groupby("site_url")["request_domain"]
        .nunique()
        .reset_index()
        .rename(columns={"request_domain": "unique_tracking_domains"})
    )

    top_domains = (
        tracked.groupby("request_domain")["site_url"]
        .nunique()
        .sort_values(ascending=False)
        .head(15)
        .reset_index()
        .rename(columns={"site_url": "sites_seen_on"})
    )

    per_site.to_csv(f"./datadir/step6_per_site_{label}.csv", index=False)
    top_domains.to_csv(f"./datadir/step6_top_domains_{label}.csv", index=False)


compute_metrics(df, "tracked_global", "Global")
compute_metrics(df, "tracked_regional", "Regional")


# ─────────────────────────────────────────────
# STEP 7 — ECOSYSTEM (REUSE tracked_regional)
# ─────────────────────────────────────────────
tracking = df[
    (df["tracked_regional"]) &
    (df["is_third_party_channel"] == 1) &
    (df["request_domain"] != "")
].copy()

if tracking.empty:
    print("No tracking data — stopping.")
    exit()


pairs = (
    tracking.groupby(["site_url", "request_domain"])
    .size()
    .reset_index(name="count")
)

# Tracker reach
reach = (
    pairs.groupby("request_domain")["site_url"]
    .nunique()
    .sort_values(ascending=False)
    .reset_index()
    .rename(columns={"site_url": "num_sites"})
)

reach.to_csv("./datadir/step7_tracker_reach.csv", index=False)


# ─────────────────────────────────────────────
# CO-OCCURRENCE
# ─────────────────────────────────────────────
pivot = (
    pairs.pivot_table(
        index="site_url",
        columns="request_domain",
        values="count",
        fill_value=0
    ).clip(upper=1)
)

top30 = reach.head(30)["request_domain"].tolist()
pivot_top = pivot[[c for c in top30 if c in pivot.columns]]

co = pivot_top.T.dot(pivot_top)

co_vals = []
cols = list(co.columns)

for i in range(len(cols)):
    for j in range(i+1, len(cols)):
        co_vals.append({
            "tracker_a": cols[i],
            "tracker_b": cols[j],
            "shared_sites": int(co.iloc[i, j])
        })

co_df = pd.DataFrame(co_vals).sort_values("shared_sites", ascending=False)
co_df.to_csv("./datadir/step7_cooccurrence.csv", index=False)


# ─────────────────────────────────────────────
# PLOTS
# ─────────────────────────────────────────────
plt.figure(figsize=(10, 6))
top20 = reach.head(20)
plt.barh(top20["request_domain"][::-1], top20["num_sites"][::-1])
plt.tight_layout()
plt.savefig("./datadir/step7_tracker_reach.png")
plt.close()


# Bipartite graph
B = nx.Graph()
for _, r in pairs.iterrows():
    B.add_edge(r["site_url"], r["request_domain"])

top10 = reach.head(10)["request_domain"].tolist()
edges = [(s, t) for s, t in B.edges() if t in top10]

G = nx.Graph()
G.add_edges_from(edges)

plt.figure(figsize=(10, 8))
pos = nx.spring_layout(G, k=0.5)
nx.draw(G, pos, node_size=50)
plt.savefig("./datadir/step7_bipartite.png")
plt.close()


print("[✓] Full pipeline complete")