"""
STEP 8 — Fingerprinting Analysis (Canvas + AudioContext)
Web Privacy Project - ENGR-UH 4323 Spring 2026

PURPOSE:
  Detect Canvas fingerprinting and AudioContext fingerprinting in
  the JavaScript instrumentation data collected by OpenWPM.

HOW FINGERPRINTING WORKS (brief background):
  Canvas fingerprinting:
    Scripts draw shapes/text onto an invisible <canvas> element and then
    call canvas.toDataURL() to read back the pixel data as a base64 string.
    Because fonts, GPU drivers, and OS rendering differ per device, the
    resulting image is slightly unique per machine — creating a device
    fingerprint without cookies.

  AudioContext fingerprinting:
    Scripts use the Web Audio API to process an audio signal through
    the browser's audio engine. Tiny floating-point differences in the
    output (caused by hardware/software differences) create a stable
    identifier per device.

RUN: python step8_fingerprinting.py
"""

import sqlite3
import pandas as pd
from urllib.parse import urlparse
from adblockparser import AdblockRules

DB_PATH = "./datadir/crawl.sqlite"

print("=" * 65)
print("  Step 8: Fingerprinting Analysis")
print("=" * 65)

# ─────────────────────────────────────────────
# Load JavaScript instrumentation data
#
# OpenWPM records every JS API call:
#   symbol    = the JS property accessed (e.g. "CanvasRenderingContext2D.fillText")
#   operation = "get", "set", or "call"
#   value     = the value read/written (can be a data URL for canvas)
#   script_url = which script triggered this call
# ─────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)

js_df = pd.read_sql("""
    SELECT
        j.visit_id,
        j.script_url,
        j.symbol,
        j.operation,
        j.value,
        sv.site_url
    FROM javascript j
    JOIN site_visits sv ON j.visit_id = sv.visit_id;
""", conn)

conn.close()

print(f"[*] Total JS API calls loaded: {len(js_df):,}")
print(f"[*] Unique sites: {js_df['site_url'].nunique()}")
total_sites = js_df["site_url"].nunique()

def get_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc if parsed.netloc else ""
    except Exception:
        return ""

js_df["script_domain"] = js_df["script_url"].apply(get_domain)

# ─────────────────────────────────────────────
# CANVAS FINGERPRINTING DETECTION
#
# METHODOLOGY (based on Englehardt & Narayanan 2016, OpenWPM paper):
#   A script is fingerprinting via canvas IF it does ALL of:
#     1. Calls fillText or strokeText (writes to canvas — generates unique content)
#     2. Calls toDataURL or getImageData (reads back the pixel data)
#   This combination: write something → read it back → it's fingerprinting.
#
# We group by (visit_id, script_url) and flag if BOTH conditions are met.
# ─────────────────────────────────────────────
print("\n[Canvas Fingerprinting Detection]")

# Canvas write operations
CANVAS_WRITE = {
    "CanvasRenderingContext2D.fillText",
    "CanvasRenderingContext2D.strokeText",
    "CanvasRenderingContext2D.fillRect",
    "CanvasRenderingContext2D.arc",
}

# Canvas read operations (extracting the fingerprint)
CANVAS_READ = {
    "HTMLCanvasElement.toDataURL",
    "CanvasRenderingContext2D.getImageData",
    "HTMLCanvasElement.toBlob",
}

canvas_write_df = js_df[js_df["symbol"].isin(CANVAS_WRITE)]
canvas_read_df  = js_df[js_df["symbol"].isin(CANVAS_READ)]

# A (visit_id, script_url) pair is canvas fingerprinting if it has BOTH
write_keys = set(zip(canvas_write_df["visit_id"], canvas_write_df["script_url"]))
read_keys  = set(zip(canvas_read_df["visit_id"],  canvas_read_df["script_url"]))

canvas_fp_keys = write_keys & read_keys  # intersection = scripts doing both

# Build a DataFrame of confirmed canvas fingerprinting scripts
canvas_fp_rows = []
for visit_id, script_url in canvas_fp_keys:
    site = js_df[js_df["visit_id"] == visit_id]["site_url"].iloc[0]
    canvas_fp_rows.append({
        "visit_id": visit_id,
        "script_url": script_url,
        "script_domain": get_domain(script_url),
        "site_url": site,
    })

canvas_fp_df = pd.DataFrame(canvas_fp_rows) if canvas_fp_rows else pd.DataFrame(
    columns=["visit_id", "script_url", "script_domain", "site_url"]
)

canvas_fp_sites = canvas_fp_df["site_url"].nunique()
canvas_pct = canvas_fp_sites / total_sites * 100 if total_sites > 0 else 0

print(f"  Sites with Canvas fingerprinting: "
      f"{canvas_fp_sites}/{total_sites} ({canvas_pct:.1f}%)")

if not canvas_fp_df.empty:
    top_canvas_scripts = (
        canvas_fp_df.groupby("script_domain")["site_url"]
        .nunique()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
        .rename(columns={"site_url": "sites"})
    )
    print(f"\n  Top scripts responsible for Canvas fingerprinting:")
    print(top_canvas_scripts.to_string(index=False))
    canvas_fp_df.to_csv("./datadir/step8_canvas_fp.csv", index=False)

# ─────────────────────────────────────────────
# AUDIO FINGERPRINTING DETECTION
#
# METHODOLOGY (based on Englehardt & Narayanan 2016):
#   Scripts using AudioContext for fingerprinting will:
#     1. Create an OscillatorNode (generates a waveform)
#     2. Use an AnalyserNode or read channel data to extract float values
#
#   Key symbols to look for:
#     - AudioContext / OfflineAudioContext (context creation)
#     - OscillatorNode.type or .frequency (waveform setup)
#     - AnalyserNode.getFloatFrequencyData / Float32Array (reading output)
# ─────────────────────────────────────────────
print("\n[AudioContext Fingerprinting Detection]")

AUDIO_CONTEXT_SYMBOLS = {
    "AudioContext",
    "OfflineAudioContext",
}

AUDIO_OSCILLATOR_SYMBOLS = {
    "OscillatorNode.type",
    "OscillatorNode.frequency",
    "AudioContext.createOscillator",
    "OfflineAudioContext.createOscillator",
}

AUDIO_READ_SYMBOLS = {
    "AnalyserNode.getFloatFrequencyData",
    "AnalyserNode.getByteFrequencyData",
    "AudioBuffer.getChannelData",
    "OfflineAudioContext.startRendering",
}

# A script is audio fingerprinting if it uses an audio context AND reads output
audio_context_df    = js_df[js_df["symbol"].str.contains("AudioContext|OfflineAudioContext",
                                                           na=False)]
audio_read_df       = js_df[js_df["symbol"].isin(AUDIO_READ_SYMBOLS)]

audio_ctx_keys  = set(zip(audio_context_df["visit_id"], audio_context_df["script_url"]))
audio_read_keys = set(zip(audio_read_df["visit_id"],    audio_read_df["script_url"]))

audio_fp_keys = audio_ctx_keys & audio_read_keys

audio_fp_rows = []
for visit_id, script_url in audio_fp_keys:
    site = js_df[js_df["visit_id"] == visit_id]["site_url"].iloc[0]
    audio_fp_rows.append({
        "visit_id": visit_id,
        "script_url": script_url,
        "script_domain": get_domain(script_url),
        "site_url": site,
    })

audio_fp_df = pd.DataFrame(audio_fp_rows) if audio_fp_rows else pd.DataFrame(
    columns=["visit_id", "script_url", "script_domain", "site_url"]
)

audio_fp_sites = audio_fp_df["site_url"].nunique()
audio_pct = audio_fp_sites / total_sites * 100 if total_sites > 0 else 0

print(f"  Sites with AudioContext fingerprinting: "
      f"{audio_fp_sites}/{total_sites} ({audio_pct:.1f}%)")

if not audio_fp_df.empty:
    top_audio_scripts = (
        audio_fp_df.groupby("script_domain")["site_url"]
        .nunique()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
        .rename(columns={"site_url": "sites"})
    )
    print(f"\n  Top scripts responsible for AudioContext fingerprinting:")
    print(top_audio_scripts.to_string(index=False))
    audio_fp_df.to_csv("./datadir/step8_audio_fp.csv", index=False)

# ─────────────────────────────────────────────
# CROSS-CHECK with EasyList (are FP scripts known trackers?)
# ─────────────────────────────────────────────
print("\n[Cross-checking with EasyList/EasyPrivacy]")

def load_cached_rules() -> AdblockRules:
    lines = []
    for path in ["./datadir/EasyList.txt", "./datadir/EasyPrivacy.txt"]:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines.extend(f.readlines())
        except FileNotFoundError:
            pass
    return AdblockRules(lines) if lines else None

rules = load_cached_rules()

if rules is None:
    print("  [!] Filter lists not found. Run Step 6 first to cache them.")
else:
    for fp_name, fp_df in [("Canvas", canvas_fp_df), ("Audio", audio_fp_df)]:
        if fp_df.empty:
            continue
        unique_scripts = fp_df["script_url"].dropna().unique()
        known = sum(1 for s in unique_scripts if rules.should_block(s))
        print(f"  {fp_name} FP scripts matched by EasyList: "
              f"{known}/{len(unique_scripts)} "
              f"({known/len(unique_scripts)*100:.1f}%)")

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
print("\n" + "=" * 65)
print("  SUMMARY")
print("=" * 65)
print(f"  Canvas fingerprinting  : {canvas_fp_sites}/{total_sites} sites ({canvas_pct:.1f}%)")
print(f"  AudioCtx fingerprinting: {audio_fp_sites}/{total_sites} sites ({audio_pct:.1f}%)")
print("\n[✓] Step 8 complete. Results saved to ./datadir/")
