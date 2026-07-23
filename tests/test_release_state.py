"""Characterization tests for release_state (Task 3 extraction).

Required regression contracts (from the plan):
- load_chapter_ledger() returns a dict.
- chapter_ledger_updates_for_folder(...) derives (abbr, chapter, updates).
- update_chapter_ledger(...) updates the chapter ledger AND mirrors to SQLite
  (dual-store). After Phase-3 retirement the JSON mirror (chapter_ledger.json)
  is NOT written; the SQLite chapter_ledger table is the sole source of truth.

The harness now runs against an ISOLATED temporary repository root + temporary
SQLite database. It points config/repository dependencies at that root so the
check never touches live state or retired JSON paths. No retired mirror may
appear anywhere in the isolated root.

Run: python tests/test_release_state.py   (from repo root)

NOTE: standalone characterization script. The executable body is guarded by
``if __name__ == "__main__":`` so pytest can import the module for collection
without executing it.
"""
import os, sys, tempfile, json
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _main():
    import app as app_mod
    import app_config as config
    import release_state as rs
    import automation_db
    from storage import database as storage_db
    from storage.retired_state import RETIRED_FILE_NAMES

    FAILS = []

    def check(name, got, want):
        if got != want:
            FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

    # --- isolated repository root + SQLite database ---
    ROOT = Path(tempfile.mkdtemp(prefix="rs_iso_"))
    storage_db.initialize_databases(ROOT)
    # Point config + extracted-module globals at the isolated root so every
    # SQLite write lands in the temp DB, never the live automation_state.db.
    config.ROOT = ROOT
    config.OUTPUT_DIR = ROOT
    config.CHAPTER_LEDGER_FILE = ROOT / "chapter_ledger.json"
    rs.ROOT = ROOT
    rs.OUTPUT_DIR = ROOT
    rs.CHAPTER_LEDGER_FILE = ROOT / "chapter_ledger.json"
    app_mod.ROOT = ROOT
    app_mod.OUTPUT_DIR = ROOT
    app_mod.CHAPTER_LEDGER_FILE = ROOT / "chapter_ledger.json"
    # Task 8 inversion: wire app.py's moved functions to the extracted modules.
    app_mod.wire_extracted_modules()
    # Re-assert the isolated root after wiring (wiring may rebind references).
    rs.ROOT = ROOT
    config.ROOT = ROOT
    app_mod.ROOT = ROOT

    try:
        # --- load_chapter_ledger returns a dict (contract) ---
        ledger = rs.load_chapter_ledger()
        check("load_chapter_ledger returns dict", isinstance(ledger, dict), True)
        check("load_chapter_ledger has chapters key", "chapters" in ledger, True)
        check("matches app load_chapter_ledger", rs.load_chapter_ledger() == app_mod.load_chapter_ledger(), True)

        # --- chapter_ledger_updates_for_folder derives (abbr, chapter, updates) ---
        campaign_folder = ROOT / "EN_Chapter_10"
        campaign_folder.mkdir(parents=True, exist_ok=True)
        md = {"abbr": "EN", "novel": "Eternal Nexus", "chapter": "10", "title": "The Spire Opens"}
        abbr, ch, updates = rs.chapter_ledger_updates_for_folder(campaign_folder, md, "promoPackBuilt")
        check("updates_for_folder abbr", abbr, "EN")
        check("updates_for_folder chapter", ch, 10)
        check("updates_for_folder status set", updates.get("promoPackBuilt"), True)
        check("updates_for_folder campaign folder", updates.get("folders", {}).get("campaign"), str(campaign_folder))
        abbr2, ch2, updates2 = app_mod.chapter_ledger_updates_for_folder(campaign_folder, md, "promoPackBuilt")
        check("updates_for_folder matches app", (abbr, ch, updates) == (abbr2, ch2, updates2), True)

        # --- update_chapter_ledger mirrors to SQLite (dual-store); NO JSON mirror ---
        entry = rs.update_chapter_ledger("EN", 10, {"promoPackBuilt": True, "shortsPackBuilt": True, "folders": {"campaign": str(campaign_folder)}})
        check("update returns entry", isinstance(entry, dict), True)
        check("update sets promoPackBuilt", entry.get("promoPackBuilt"), True)

        # Verify the relational/snapshot-backed SQLite state DIRECTLY (isolated DB).
        db_entry = automation_db.load_chapter_ledger_entry(ROOT, "EN", 10)
        check("sqlite ledger entry present", isinstance(db_entry, dict), True)
        check("sqlite entry promoPackBuilt", db_entry.get("promoPackBuilt"), True)
        check("sqlite entry shortsPackBuilt", db_entry.get("shortsPackBuilt"), True)

        # Parity with app's update result (same isolated root); ignore volatile stamp.
        entry_app = app_mod.update_chapter_ledger("EN", 10, {"promoPackBuilt": True, "shortsPackBuilt": True, "folders": {"campaign": str(campaign_folder)}})
        e1 = {k: v for k, v in entry.items() if k != "updatedAt"}
        e2 = {k: v for k, v in entry_app.items() if k != "updatedAt"}
        check("update matches app entry", e1, e2)

        # --- chapter_ledger_entry reads back (SQLite-backed) ---
        e1 = rs.chapter_ledger_entry("EN", 10)
        e2 = app_mod.chapter_ledger_entry("EN", 10)
        check("chapter_ledger_entry matches app", e1, e2)
        check("chapter_ledger_entry promoPackBuilt", e1.get("promoPackBuilt"), True)

        # --- release_status_for_chapter with injected real app collaborators ---
        collabs = {name: getattr(app_mod, name) for name in rs.REQUIRED_RELEASE_STATUS_COLLABORATORS}
        app_rs = app_mod.release_status_for_chapter("EN", 10)
        pb_rs = rs.release_status_for_chapter("EN", 10, collaborators=collabs)
        check("release_status_for_chapter matches app", pb_rs, app_rs)

        # --- Phase-3 guard: NO retired mirror may appear in the isolated root ---
        retired_found = [n for n in RETIRED_FILE_NAMES if (ROOT / n).exists()]
        check("no retired mirror in isolated root", retired_found, [])
        # Specifically, the legacy chapter_ledger.json is NOT written (SQLite only).
        check("no chapter_ledger.json created", (ROOT / "chapter_ledger.json").exists(), False)
    finally:
        # Nothing to restore: all writes went to the isolated temp root/DB.
        pass

    if FAILS:
        print("FAIL", len(FAILS))
        for f in FAILS:
            print(" -", f)
        raise SystemExit(1)
    print("PASS all release_state characterization checks (isolated SQLite + parity with app.py)")


if __name__ == "__main__":
    _main()
