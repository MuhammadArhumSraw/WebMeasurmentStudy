"""
STEP 4 — Explore the OpenWPM Dataset
Web Privacy Project - ENGR-UH 4323 Spring 2026

PURPOSE:
  This script connects to your crawl database and prints out:
  - All table names and their schemas
  - Row counts for each table
  - Example rows from the most important tables
  - How to JOIN tables together

RUN: python step4_explore_dataset.py
"""

import sqlite3
import pandas as pd

DB_PATH = "./datadir/crawl.sqlite"

# ─────────────────────────────────────────────
# Connect
# ─────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row  # lets us access columns by name

print("=" * 65)
print("  OpenWPM Database Explorer")
print(f"  Database: {DB_PATH}")
print("=" * 65)

# ─────────────────────────────────────────────
# List all tables
# ─────────────────────────────────────────────
tables = pd.read_sql(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;", conn
)
print(f"\n[1] Tables in the database ({len(tables)} total):")
for t in tables["name"]:
    count = pd.read_sql(f"SELECT COUNT(*) as n FROM {t};", conn)["n"][0]
    print(f"    {t:<30} → {count:,} rows")

# ─────────────────────────────────────────────
# Schema for each important table
# ─────────────────────────────────────────────
important_tables = [
    "site_visits",
    "crawl_history",
    "http_requests",
    "http_responses",
    "http_redirects",
    "javascript",
    "javascript_cookies",
]

print("\n" + "=" * 65)
print("  [2] Schemas of Important Tables")
print("=" * 65)

for table in important_tables:
    try:
        df = pd.read_sql(f"PRAGMA table_info({table});", conn)
        print(f"\n  TABLE: {table}")
        print(f"  {'Column':<35} {'Type':<15}")
        print(f"  {'-'*35} {'-'*15}")
        for _, row in df.iterrows():
            print(f"  {row['name']:<35} {row['type']:<15}")
    except Exception as e:
        print(f"  [!] Could not read schema for {table}: {e}")

# ─────────────────────────────────────────────
# Example rows from key tables
# ─────────────────────────────────────────────
print("\n" + "=" * 65)
print("  [3] Example Rows")
print("=" * 65)

example_queries = {
    "site_visits (what sites were crawled)":
        "SELECT visit_id, site_url, site_rank FROM site_visits LIMIT 5;",

    "http_requests (outgoing requests from the browser)":
        """SELECT visit_id, url, top_level_url, is_third_party_channel,
                  resource_type, method
           FROM http_requests LIMIT 5;""",

    "http_responses (responses received)":
        """SELECT visit_id, url, response_status, location
           FROM http_responses LIMIT 5;""",

    "http_redirects (redirect chains)":
        """SELECT visit_id, old_request_url, new_request_url, response_status
           FROM http_redirects LIMIT 5;""",

    "javascript (JS API calls — fingerprinting lives here)":
        """SELECT visit_id, script_url, symbol, operation, value
           FROM javascript LIMIT 5;""",

    "javascript_cookies (cookies set by JS)":
        """SELECT visit_id, host, name, value, is_http_only, is_session
           FROM javascript_cookies LIMIT 5;""",
}

for description, query in example_queries.items():
    print(f"\n  ── {description}")
    try:
        df = pd.read_sql(query, conn)
        print(df.to_string(index=False))
    except Exception as e:
        print(f"  [!] Error: {e}")

# ─────────────────────────────────────────────
# Key JOIN questions answered
# ─────────────────────────────────────────────
print("\n" + "=" * 65)
print("  [4] Answering the JOIN questions from the project")
print("=" * 65)

print("""
Q1: When crawling multiple websites, all JavaScript events are stored
    in the same javascript table. How can you determine which JavaScript
    execution corresponds to which specific site visit?

A: Every row in the javascript table has a 'visit_id' column.
   This visit_id is a foreign key that links to site_visits.visit_id.
   By JOINing on visit_id, you can filter JS calls to a specific site.

   Example SQL:
     SELECT j.symbol, j.operation, sv.site_url
     FROM javascript j
     JOIN site_visits sv ON j.visit_id = sv.visit_id
     WHERE sv.site_url = 'https://example.com';

Q2: How can you associate an entry in http_responses with its
    corresponding http_requests entry?

A: Both tables share a 'request_id' column (also called 'id' in some
   OpenWPM versions). You JOIN them on request_id to match each
   response to its originating request.

   Example SQL:
     SELECT req.url, req.method, resp.response_status
     FROM http_requests req
     JOIN http_responses resp ON req.id = resp.request_id
     LIMIT 10;
""")

# ─────────────────────────────────────────────
# Third-party detection check
# ─────────────────────────────────────────────
print("=" * 65)
print("  [5] Quick third-party request check")
print("=" * 65)

try:
    df = pd.read_sql("""
        SELECT
            COUNT(*) as total_requests,
            SUM(CASE WHEN is_third_party_channel = 1 THEN 1 ELSE 0 END) as third_party,
            SUM(CASE WHEN is_third_party_channel = 0 THEN 1 ELSE 0 END) as first_party
        FROM http_requests;
    """, conn)
    print(df.to_string(index=False))
except Exception as e:
    print(f"  [!] {e}")

conn.close()
print("\n[✓] Done. Use the schemas above to guide your analysis scripts.")