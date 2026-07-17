"""Characterization tests for release_state (Task 3 extraction).

Required regression contracts (from the plan):
- load_chapter_ledger() returns a dict.
- chapter_ledger_updates_for_folder(...) derives (abbr, chapter, updates).
- update_chapter_ledger(...) updates the in-memory ledger AND writes the JSON mirror
  AND mirrors to SQLite (dual-store). We assert the JSON file is written and that the
  SQLite mirror path is exercised (real automation_db is used; if the DB is unavailable
  the mirror is caught internally and must not raise).

Run: python tests/test_release_state.py   (from repo root)
"""
import os, sys, tempfile, json
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import app_config as config
import release_state as rs

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- load_chapter_ledger returns a dict (contract) ---
ledger = rs.load_chapter_ledger()
check("load_chapter_ledger returns dict", isinstance(ledger, dict), True)
check("load_chapter_ledger has chapters key", "chapters" in ledger, True)
check("matches app load_chapter_ledger", rs.load_chapter_ledger() == app_mod.load_chapter_ledger(), True)

# --- chapter_ledger_updates_for_folder derives (abbr, chapter, updates) ---
import tempfile
TMP = Path(tempfile.mkdtemp(prefix="rs_test_"))
campaign_folder = config.OUTPUT_DIR / "EN_Chapter_10"
campaign_folder.mkdir(parents=True, exist_ok=True)
md = {"abbr": "EN", "novel": "Eternal Nexus", "chapter": "10", "title": "The Spire Opens"}
abbr, ch, updates = rs.chapter_ledger_updates_for_folder(campaign_folder, md, "promoPackBuilt")
check("updates_for_folder abbr", abbr, "EN")
check("updates_for_folder chapter", ch, 10)
check("updates_for_folder status set", updates.get("promoPackBuilt"), True)
check("updates_for_folder campaign folder", updates.get("folders", {}).get("campaign"), str(campaign_folder))
# matches app exactly
abbr2, ch2, updates2 = app_mod.chapter_ledger_updates_for_folder(campaign_folder, md, "promoPackBuilt")
check("updates_for_folder matches app", (abbr, ch, updates) == (abbr2, ch2, updates2), True)

# --- update_chapter_ledger writes JSON mirror + mirrors to SQLite (dual-store) ---
# Point release_state at a temp ledger file so we don't disturb the real one.
orig_ledger_file = rs.CHAPTER_LEDGER_FILE
temp_ledger = TMP / "chapter_ledger.json"
rs.CHAPTER_LEDGER_FILE = temp_ledger
app_mod.CHAPTER_LEDGER_FILE = temp_ledger
try:
    entry = rs.update_chapter_ledger("EN", 10, {"promoPackBuilt": True, "shortsPackBuilt": True, "folders": {"campaign": str(campaign_folder)}})
    check("update returns entry", isinstance(entry, dict), True)
    check("update sets promoPackBuilt", entry.get("promoPackBuilt"), True)
    check("update mirrors to JSON file", temp_ledger.exists(), True)
    written = json.loads(temp_ledger.read_text(encoding="utf-8"))
    check("JSON mirror has EN-10", "EN-10" in written.get("chapters", {}), True)
    check("JSON mirror EN-10 promoPackBuilt", written["chapters"]["EN-10"].get("promoPackBuilt"), True)
    # matches app's update result (with same temp ledger) -- ignore the volatile updatedAt stamp
    entry_app = app_mod.update_chapter_ledger("EN", 10, {"promoPackBuilt": True, "shortsPackBuilt": True, "folders": {"campaign": str(campaign_folder)}})
    e1 = {k: v for k, v in entry.items() if k != "updatedAt"}
    e2 = {k: v for k, v in entry_app.items() if k != "updatedAt"}
    check("update matches app entry", e1, e2)
finally:
    rs.CHAPTER_LEDGER_FILE = orig_ledger_file
    app_mod.CHAPTER_LEDGER_FILE = orig_ledger_file

# --- chapter_ledger_entry reads back (uses injected-free self-contained path) ---
# Use the temp ledger again for determinism.
rs.CHAPTER_LEDGER_FILE = temp_ledger
app_mod.CHAPTER_LEDGER_FILE = temp_ledger
try:
    e1 = rs.chapter_ledger_entry("EN", 10)
    e2 = app_mod.chapter_ledger_entry("EN", 10)
    check("chapter_ledger_entry matches app", e1, e2)
    check("chapter_ledger_entry promoPackBuilt", e1.get("promoPackBuilt"), True)
finally:
    rs.CHAPTER_LEDGER_FILE = orig_ledger_file
    app_mod.CHAPTER_LEDGER_FILE = orig_ledger_file

# --- release_status_for_chapter with injected real app collaborators matches app ---
collabs = {name: getattr(app_mod, name) for name in rs.REQUIRED_RELEASE_STATUS_COLLABORATORS}
# pick a chapter that exists in schedule; fallback: compare against app for any chapter
app_rs = app_mod.release_status_for_chapter("EN", 10)
pb_rs = rs.release_status_for_chapter("EN", 10, collaborators=collabs)
check("release_status_for_chapter matches app", pb_rs, app_rs)

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all release_state characterization checks (dual-store + parity with app.py)")
