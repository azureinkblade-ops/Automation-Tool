import os, sys, json
sys.path.insert(0, os.getcwd())
import app as app_mod
import automation_db

# Map each Phase-1 state to its DB read (must match what the loader will use
# after retirement) and its JSON file. Parity = DB blob == JSON file.
STATES = [
    # key, db_reader, json_file, note
    ("postRecords", lambda: automation_db.load_post_records(app_mod.ROOT), app_mod.POST_RECORDS_FILE, "table"),
    ("chapterLedger", lambda: automation_db.load_chapter_ledger(app_mod.ROOT), app_mod.CHAPTER_LEDGER_FILE, "table"),
    ("releaseStatus", lambda: automation_db.load_release_status(app_mod.ROOT), app_mod.RELEASE_STATUS_FILE, "table"),
    ("approvalCleared", lambda: automation_db.load_approval_cleared_state(app_mod.ROOT), app_mod.APPROVAL_INBOX_CLEARED_FILE, "table"),
    ("promoRotation", lambda: app_mod.load_state_snapshot_from_database("promoRotation"), app_mod.PROMO_ROTATION_STATE_FILE, "kv"),
    ("chapterPath", lambda: app_mod.load_state_snapshot_from_database("chapterPath"), app_mod.CHAPTER_PATH_FILE, "kv"),
    ("chapterReleaseQueue", lambda: app_mod.load_state_snapshot_from_database("chapterReleaseQueue"), app_mod.CHAPTER_RELEASE_QUEUE_FILE, "kv"),
    ("youtubeDailyStatus", lambda: app_mod.load_state_snapshot_from_database("youtubeDailyStatus"), app_mod.YOUTUBE_DAILY_STATUS_FILE, "kv"),
    ("recoveryLog", lambda: app_mod.load_state_snapshot_from_database("recoveryLog"), app_mod.RECOVERY_LOG_FILE, "kv(new)"),
]

problems = []
checked = 0
for key, db_read, json_file, kind in STATES:
    checked += 1
    db = db_read()
    db = db if isinstance(db, dict) else {}
    db_c = {k: v for k, v in db.items() if k != "_source"}
    js = None
    if json_file.exists():
        try:
            js = json.loads(json_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            problems.append(f"{key}: JSON read error: {exc}")
            continue
    # updatedAt is a cosmetic write-time stamp carried only by the JSON; the DB
    # table/kv stores the substantive data. Strip it before comparing.
    db_c = {k: v for k, v in db.items() if k not in ("_source", "updatedAt")}
    js_c = {k: v for k, v in (js or {}).items() if k not in ("_source", "updatedAt")}
    db_ok = bool(db_c)
    js_ok = bool(js_c)
    if not db_ok and not js_ok:
        print(f"  {key}: both empty/fresh (kind={kind}) -> OK")
        continue
    if db_ok and not js_ok:
        # DB has data, JSON absent. Safe ONLY if JSON was already retired or never
        # written. Flag for awareness (data lives in DB = source of truth).
        print(f"  {key}: DB present, JSON ABSENT (kind={kind}) -> DB is source (fine to retire JSON)")
        continue
    if js_ok and not db_ok:
        problems.append(f"{key}: JSON has data but DB EMPTY -> DATA LOSS if JSON deleted")
        continue
    agree = json.dumps(db_c, sort_keys=True, default=str) == json.dumps(js_c, sort_keys=True, default=str)
    if not agree:
        problems.append(f"{key}: DB != JSON (divergence) -> cannot safely delete JSON")
    else:
        print(f"  {key}: DB==JSON OK (kind={kind})")

print(f"\nChecked {checked} Phase-1 states.")
if problems:
    print("PARITY FAILED:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("PARITY OK (or DB-source where JSON absent): safe to retire JSON.")
