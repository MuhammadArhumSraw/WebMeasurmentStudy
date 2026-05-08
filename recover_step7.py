import pandas as pd
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

print("=" * 60)
print("RECOVERING STEP 7 FROM SAVED CSV")
print("=" * 60)

# ─────────────────────────────────────────────
# LOAD SAVED DATA
# ─────────────────────────────────────────────
df = pd.read_csv(
    "./datadir/step7_all_tracking_requests.csv"
)

print(f"Loaded rows: {len(df):,}")

# keep only detected tracking requests
df = df[df["is_tracking"] == True]

print(f"Tracking rows: {len(df):,}")

# fix missing third-party values
df["is_third_party_channel"] = (
    df["is_third_party_channel"]
    .fillna(1)
)

# normalize values
df["is_third_party_channel"] = (
    df["is_third_party_channel"]
    .astype(int)
)

# ─────────────────────────────────────────────
# SAVE FIRST / THIRD PARTY
# ─────────────────────────────────────────────
first_party = df[
    df["is_third_party_channel"] == 0
]

third_party = df[
    df["is_third_party_channel"] == 1
]

first_party.to_csv(
    "./datadir/step7_first_party_tracking.csv",
    index=False
)

third_party.to_csv(
    "./datadir/step7_third_party_tracking.csv",
    index=False
)

print(f"First-party rows : {len(first_party):,}")
print(f"Third-party rows : {len(third_party):,}")

# ─────────────────────────────────────────────
# TRACKER ↔ SITE MAP
# ─────────────────────────────────────────────
tracker_site = (
    df.groupby([
        "site_url",
        "request_domain",
        "is_third_party_channel"
    ])
    .size()
    .reset_index(name="request_count")
)

tracker_site["party_type"] = np.where(
    tracker_site["is_third_party_channel"] == 1,
    "third_party",
    "first_party"
)

tracker_site.to_csv(
    "./datadir/step7_tracker_site_mapping.csv",
    index=False
)

print(f"Tracker-site pairs: {len(tracker_site):,}")

# ─────────────────────────────────────────────
# ONLY THIRD-PARTY FOR ECOSYSTEM
# ─────────────────────────────────────────────
tracking = tracker_site[
    tracker_site["is_third_party_channel"] == 1
]

print(f"Third-party relations: {len(tracking):,}")

# ─────────────────────────────────────────────
# TRACKER REACH
# ─────────────────────────────────────────────
tracker_reach = (
    tracking.groupby("request_domain")["site_url"]
    .nunique()
    .sort_values(ascending=False)
    .reset_index()
    .rename(columns={"site_url": "num_sites"})
)

tracker_reach["pct_sites"] = (
    tracker_reach["num_sites"]
    / tracking["site_url"].nunique()
    * 100
).round(1)

print("\nTop trackers:\n")
print(tracker_reach.head(20).to_string(index=False))

tracker_reach.to_csv(
    "./datadir/step7_tracker_reach.csv",
    index=False
)

# ─────────────────────────────────────────────
# CO-OCCURRENCE
# ─────────────────────────────────────────────
pivot = (
    tracking.pivot_table(
        index="site_url",
        columns="request_domain",
        values="request_count",
        fill_value=0
    )
    .clip(upper=1)
)

if pivot.empty:
    print("No co-occurrence data.")
    exit()

top30 = tracker_reach.head(30)["request_domain"]

pivot_top = pivot[
    [c for c in top30 if c in pivot.columns]
]

cooccurrence = pivot_top.T.dot(pivot_top)

pairs = []

cols = list(cooccurrence.columns)

for i in range(len(cols)):
    for j in range(i + 1, len(cols)):

        pairs.append({
            "tracker_a": cols[i],
            "tracker_b": cols[j],
            "shared_sites": int(cooccurrence.iloc[i, j])
        })

cooc_df = (
    pd.DataFrame(pairs)
    .sort_values("shared_sites", ascending=False)
)

cooc_df.to_csv(
    "./datadir/step7_cooccurrence.csv",
    index=False
)

print("\nTop co-occurring trackers:\n")
print(cooc_df.head(10).to_string(index=False))

# ─────────────────────────────────────────────
# BAR CHART
# ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))

top20 = tracker_reach.head(20)

ax.barh(
    top20["request_domain"][::-1],
    top20["num_sites"][::-1]
)

ax.set_xlabel("Number of sites")
ax.set_title("Top 20 Third-Party Trackers")

plt.tight_layout()

plt.savefig(
    "./datadir/step7_tracker_reach.png",
    dpi=150
)

print("\nSaved tracker reach graph")

# ─────────────────────────────────────────────
# BIPARTITE GRAPH
# ─────────────────────────────────────────────
B = nx.Graph()

for _, row in tracking.iterrows():

    B.add_edge(
        row["site_url"],
        row["request_domain"]
    )

top10 = (
    tracker_reach.head(10)["request_domain"]
    .tolist()
)

sub_edges = [
    (s, t)
    for s, t in B.edges()
    if t in top10
]

G = nx.Graph()
G.add_edges_from(sub_edges)

plt.figure(figsize=(12, 8))

pos = nx.spring_layout(G, seed=42)

nx.draw(
    G,
    pos,
    node_size=50,
    with_labels=False
)

plt.title("Sites ↔ Top Trackers")

plt.savefig(
    "./datadir/step7_bipartite.png",
    dpi=150
)

print("Saved bipartite graph")

print("\nDONE")
