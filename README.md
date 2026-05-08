# OpenWPM Web Tracking Measurement Pipeline

A comprehensive Python-based web privacy measurement pipeline built on **OpenWPM** (Open Web Privacy Measurement) for analyzing web tracking, fingerprinting, and cookie usage across websites.

## Overview

This project implements a multi-stage measurement pipeline to detect and analyze:
- **Tracking Cookies** — Identification and classification of tracking cookies (HTTP vs JavaScript)
- **Tracking Requests** — Detection using EasyList/EasyPrivacy filter lists
- **Fingerprinting** — Canvas and AudioContext fingerprinting techniques
- **Tracker Ecosystem** — Co-occurrence patterns and tracker distribution
- **HAR Comparison** — Reconciling browser-instrumented requests with test page captures

## Pipeline Architecture

```
┌─────────────────────────────────────────┐
│  Phase 1: Crawling (crawler.py)         │
│  • OpenWPM browser automation           │
│  • HTTP/JS/Cookie instrumentation       │
│  • Custom link extraction + consent     │
│  → Output: crawl.sqlite + HAR files     │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
    ┌──▼─────────────────────┐    ┌──────────────────────────┐
    │ Phase 2: Analysis      │    │ Phase 2b: Link Parsing   │
    │                        │    │                          │
    │ • Step 5: Cookies      │    │ • Extract linked domains │
    │ • Step 6: Requests     │    │ • Build reference graph  │
    │ • Step 7: Ecosystem    │    │                          │
    │ • Step 8: Fingerprint  │    │                          │
    │ • Step 9: HAR diff     │    │                          │
    └────────────────────────┘    └──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
    ┌──▼──────────────┐  ┌──────────────────────┐
    │ CSV Exports    │  │ SQLite Database      │
    │ • Tracking     │  │ • http_requests      │
    │ • Ecosystem    │  │ • javascript         │
    │ • Fingerprint  │  │ • cookies            │
    │ • HAR diff     │  │ • site_visits        │
    └────────────────┘  └──────────────────────┘
```

## Installation

### Prerequisites
- Python 3.8+
- OpenWPM installed and configured
- Firefox (used by OpenWPM)
- Linux/WSL environment recommended

### Setup

```bash
# Clone or navigate to the project directory
cd WebMeasurmentStudy

# Install required Python packages
pip install openwpm pandas numpy matplotlib networkx adblockparser tranco

# Create data directory
mkdir -p datadir/links datadir/screenshots datadir/sources
```

## Usage

### Phase 1: Web Crawling

#### Basic Usage

```bash
# Crawl Tranco top 100 sites (default)
python crawler.py

# Crawl Tranco top 500 sites in headless mode
python crawler.py --tranco --n 500 --headless

# Crawl custom list from CSV/text file
python crawler.py --file sites.csv --headless

# Crawl specific number of sites
python crawler.py --n 50
```

#### What the Crawler Records
- **HTTP Requests/Responses**: All network traffic with headers and response bodies
- **Cookies**: Both HTTP-only and JavaScript-accessible cookies
- **JavaScript API Calls**: All calls to sensitive APIs (Canvas, AudioContext, localStorage, etc.)
- **DOM Links**: Live DOM extraction via `ExtractLinksCommand`
- **Page Source**: HTML snapshots and server responses

#### Output Files
- `datadir/crawl.sqlite` — SQLite database with instrumentation data
- `datadir/crawl.log` — Detailed crawl logs
- `datadir/sources/` — Captured HTML/page sources
- `datadir/links/` — JSON files with extracted links per domain

### Phase 2: Analysis Pipeline

Each analysis step reads from the SQLite database and generates CSV reports.

#### Step 5: Tracking Cookies Analysis
```bash
python step5_tracking_cookies.py
```

**Detects**:
- Common tracking cookies: `_ga`, `_fbp`, `__gads`, etc.
- First-party vs third-party classification
- HTTP-Set vs JavaScript-Set distinction

**Output**: `datadir/step5_cookie_summary.csv`

#### Step 6: Tracking Requests Detection
```bash
python step6_tracking_requests.py
```

**Methodology**:
- Downloads or caches EasyList and EasyPrivacy filter lists
- Matches HTTP requests against tracking rules
- Supports regional filter lists (Liste_AR, EasyList_China)

**Outputs**:
- `datadir/step6_tracking_domains_per_site.csv`
- `datadir/step6_top_tracking_domains.csv`

#### Step 7: Tracker Ecosystem Analysis
```bash
python step7_ecosystem.py
```

**Analyzes**:
- Tracker concentration and prevalence
- Co-occurrence patterns (which trackers appear together)
- First-party vs third-party tracking

**Outputs**:
- `datadir/step7_tracker_site_mapping.csv` — Full tracker ↔ site mapping
- `datadir/step7_tracker_reach.csv` — Tracker prevalence
- `datadir/step7_first_party_tracking.csv` — Self-hosted tracking
- `datadir/step7_third_party_tracking.csv` — Third-party trackers
- `datadir/step7_cooccurrence.csv` — Tracker co-occurrence matrix

Please run recoveer_step6.py and recover_7.py at this point to fix the issue of third party channel by openwpm

#### Step 8: Fingerprinting Analysis
```bash
python step8_fingerprinting.py
```

**Detects**:
- **Canvas Fingerprinting**: `canvas.toDataURL()` calls with data URLs
- **AudioContext Fingerprinting**: Web Audio API operations on floating-point audio buffers

**Outputs**:
- `datadir/step8_canvas_fp.csv` — Canvas fingerprinting prevalence
- `datadir/step8_audio_fp.csv` — AudioContext fingerprinting prevalence

#### Step 9: HAR vs Crawl Comparison
```bash
python step9_har_vs_crawl_diff.py
```

**Purpose**: Compare requests captured via OpenWPM instrumentation against manual HAR captures (useful for validation and test page analysis)

**Outputs**:
- `datadir/step9_all_requests.csv` — Crawl request log
- `datadir/step9_tracking_filter.csv` — Tracked requests
- `datadir/step9_tracking_heuristic.csv` — Heuristic-based detection
- `datadir/har_only_tracking_requests.csv` — HAR-only trackers

#### Step 9 Test Case Analysis
```bash
python step9_test_case.py
```

Analyzes specific test pages (e.g., `salim.webprivacylab.com`) for synthetic fingerprinting/tracking scenarios.

### Utility Scripts

- `demo.py` — Quick demonstration of pipeline steps
- `exploredataset.py` — Dataset exploration and summary statistics
- `test_custom_commads_*.py` — Unit tests for custom commands
Then run step9_har_vs_crawl_diff.py to for th manual inspection
## Custom Commands

The pipeline uses custom OpenWPM commands for enhanced measurements:

### `ExtractLinksCommand`
Extracts all hyperlinks from the live DOM (including iframes) via JavaScript execution, preventing file I/O synchronization issues.

```python
from custom_commands import ExtractLinksCommand

cmd = ExtractLinksCommand(base_url="https://example.com", max_links=50)
# Internally: waits for DOM stability → collects links from page + iframes → writes JSON
```

### `CookieConsentCommand`
Auto-clicks cookie consent banners to enable tracking measurements.

### `SleepCommand`
Adds page delay for JavaScript and dynamic content loading.

## Data Structure

### SQLite Database (`crawl.sqlite`)

#### `http_requests` Table
```sql
visit_id          -- References site_visits
url               -- Request URL
method            -- GET, POST, etc.
is_third_party_channel -- Boolean flag
response_status   -- HTTP status code
```

#### `javascript` Table
```sql
visit_id          -- References site_visits
symbol            -- JS property accessed (e.g., "CanvasRenderingContext2D.fillText")
operation         -- "get", "set", or "call"
value             -- Accessed value (base64 for canvas data URLs)
script_url        -- URL of script making the call
```

#### `cookies` Table
```sql
visit_id          -- References site_visits
name              -- Cookie name
value             -- Cookie value
host              -- Domain that set the cookie
is_http_only      -- Boolean flag
is_secure         -- HTTPS-only flag
```

#### `site_visits` Table
```sql
visit_id          -- Unique visit identifier
site_url          -- The website being crawled
visit_date        -- Timestamp of visit
```

### CSV Exports

All analysis steps export results to `datadir/` as CSV files with headers for easy import into analysis tools (R, Excel, Pandas, etc.).

## Project Structure

```
WebMeasurmentStudy/
├── crawler.py                          # Main crawling script
├── step5_tracking_cookies.py           # Cookie detection
├── step6_tracking_requests.py          # Request filtering
├── step7_ecosystem.py                  # Tracker ecosystem
├── step8_fingerprinting.py             # Fingerprinting detection
├── step9_har_vs_crawl_diff.py          # HAR comparison
├── step9_test_case.py                  # Test page analysis
│
├── custom_commands.py                  # Custom OpenWPM commands
├── demo.py                             # Quick demo pipeline
├── exploredataset.py                   # Dataset exploration
│
├── sites.csv                           # List of sites to crawl
├── sites1.csv                          # Alternative site list
├── cookies.txt                         # Known tracking cookies (reference)
│
├── easylist.txt, easyprivacy.txt       # Filter list caches
├── datadir/                            # Output directory (created at runtime)
│   ├── crawl.sqlite                    # Main database
│   ├── crawl.log                       # Detailed logs
│   ├── step5_cookie_summary.csv        # Cookie analysis
│   ├── step6_*.csv                     # Request tracking
│   ├── step7_*.csv                     # Ecosystem mapping
│   ├── step8_*.csv                     # Fingerprinting results
│   ├── step9_*.csv                     # HAR comparison
│   ├── links/                          # Domain → links mapping (JSON)
│   ├── screenshots/                    # Browser screenshots
│   └── sources/                        # Page sources
│
└── README.md                           # This file
```

## Key Concepts

### Tracking Detection Methods

1. **Cookie-based**: Well-known tracking cookie names and patterns
2. **Filter List-based** (Step 6): EasyList/EasyPrivacy tracking URL patterns
3. **Heuristic-based**: Third-party requests to known tracker domains
4. **Fingerprinting**: Detection of Canvas/AudioContext API abuse

### First-party vs Third-party

- **First-party**: Request domain matches the visited website
- **Third-party**: Request domain differs from the visited website (classic tracking)

### Filter Lists

- **EasyList**: General-purpose ad blocking rules
- **EasyPrivacy**: Privacy-specific tracking detection
- **Regional**: Localized ad/tracking rules

## Configuration

Key environment variables and settings:
- `NUM_BROWSERS` in `crawler.py` — Number of parallel browser instances (default: 2)
- `display_mode` — "native", "headless", or "xvfb"
- `FILTER_LISTS` in step 6 — Which tracking filter lists to use
- Database path — `DB_PATH = "./datadir/crawl.sqlite"`

## Output Examples

### Cookie Analysis (step5_cookie_summary.csv)
```
site,tracking_cookie,category,first_party,http_set_count,js_set_count
amazon.com,_gid,Google Analytics,false,45,0
amazon.com,__gads,Google Ads,false,32,10
```

### Tracking Requests (step6_top_tracking_domains.csv)
```
tracking_domain,request_count,site_count,category
google-analytics.com,5432,89,analytics
facebook.com,3210,76,social
doubleclick.net,2891,64,advertising
```

### Fingerprinting (step8_canvas_fp.csv)
```
site,fingerprinting_detected,script_url,method_calls,data_url_count
amazon.com,true,https://example-tracker.com/fp.js,fillRect|toDataURL,5
```

## Performance Notes

- **Crawl Time**: ~30-60 minutes for 100 sites (depends on network, page complexity)
- **Analysis Time**: 5-15 minutes for full pipeline (step 5-9)
- **Storage**: ~500 MB-2 GB per 100 sites (SQLite + sources)
- **Memory**: 4-8 GB recommended for concurrent browser instances

## Troubleshooting

### Crawl Hangs
- Reduce `NUM_BROWSERS` (try 1)
- Use `--headless` mode for stability
- Check Firefox binary path in OpenWPM config

### Missing Tracking Detections
- Ensure filter lists are up-to-date (delete cache files in `datadir/`)
- Verify JavaScript instrumentation is enabled in `crawler.py`
- Check database for raw HTTP/JS data before concluding no tracking

### SQLite Errors
- Ensure `datadir/` directory exists
- Check disk space and permissions
- Delete corrupted database and re-crawl if needed

## References

- **OpenWPM**: https://github.com/mozilla/openwpm
- **EasyList**: https://easylist.to/
- **Canvas Fingerprinting**: [Detecting Canvas Fingerprinting](https://arxiv.org/abs/1503.01142)
- **AudioContext Fingerprinting**: [AudioContext API Fingerprinting](https://arxiv.org/abs/1503.01142)

## License

This project is part of ENGR-UH 4323 (Web Privacy) coursework, Spring 2026.

## Contributing

To add new analysis steps:
1. Create a new `stepN_*.py` script that reads from `crawl.sqlite`
2. Export results as CSV to `datadir/stepN_*.csv`
3. Update this README with the new step's purpose and usage

---

**Last Updated**: Spring 2026  
**Author**: Muhammad Arhum Azeem
