"""Release upload tracker (READ-ONLY) — tracks the Patreon/Royal Road upload flow.
Watches release_status.json chapter flags + patreon-draft-pending.json for transitions:
  Inner Disciple staged / posted, Path Initiate posted, Royal Road posted.
Logs a timestamped timeline to logs/release_upload_tracker.log. Never writes app state.

Safe to run alongside GPT edits / the app: only READS state files.
Usage:  python release_upload_tracker.py            # poll every 15s, heartbeat every 5 min
        python release_upload_tracker.py 30         # custom poll seconds
"""
import os
import sys
import time
from pathlib import Path

ROOT = r"C:\Users\David\Documents\Automation tool"
LOG = os.path.join(ROOT, "logs", "release_upload_tracker.log")
ROOT_PATH = Path(ROOT)
sys.path.insert(0, str(ROOT_PATH))

import automation_db  # noqa: E402

FLAGS = [
    ("patreonInnerDisciplePosted", "Inner Disciple posted"),
    ("patreonPathInitiatePosted", "Path Initiate posted"),
    ("royalRoadExists", "Royal Road posted"),
]


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def safe_release_status():
    try:
        data = automation_db.load_release_status(ROOT_PATH)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def safe_state_snapshot(key):
    try:
        data = automation_db.load_state_snapshot(ROOT_PATH, key)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def snapshot():
    """Return (chapters_dict, pending_key)."""
    rs = safe_release_status()
    chapters = {}
    if isinstance(rs, dict):
        for k, v in rs.get("chapters", {}).items():
            ab = v.get("abbr")
            ch = v.get("chapter")
            if not ab or not isinstance(ch, int):
                continue
            chapters[(ab, ch)] = {fk: bool(v.get(fk)) for fk, _ in FLAGS}
    pd = safe_state_snapshot("patreonPendingDraft")
    pending_key = (
        str(pd.get("novel")),
        str(pd.get("chapter")),
        str(pd.get("created_at", pd.get("createdAt"))),
        str(pd.get("stage", pd.get("tier"))),
    )
    return chapters, pending_key


def main():
    poll = 15
    for a in sys.argv[1:]:
        if a.isdigit():
            poll = int(a)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log("=== RELEASE UPLOAD TRACKER START (read-only) ===")
    log(f"watching: SQLite release_status + state_snapshots[patreonPendingDraft]  poll={poll}s")

    prev_ch, prev_pending = snapshot()
    # baseline: do not log already-true flags as transitions
    log(f"baseline chapters tracked: {len(prev_ch)}")
    heartbeat = 0
    while True:
        time.sleep(poll)
        cur_ch, cur_pending = snapshot()
        if cur_ch is None:
            continue  # file mid-write by GPT/app; skip this tick

        # new Patreon draft staged?
        if cur_pending != prev_pending and any(cur_pending):
            novel, ch, ts, stage = cur_pending
            log(f"DRAFT STAGED: {novel} Ch {ch} (stage={stage}, created={ts})")

        # flag transitions -> posted
        for key, flags in cur_ch.items():
            ab, ch = key
            prev = prev_ch.get(key, {})
            for fk, label in FLAGS:
                if flags.get(fk) and not prev.get(fk):
                    log(f"UPLOAD: {ab} Ch {ch} -> {label}")

        prev_ch, prev_pending = cur_ch, cur_pending
        heartbeat += 1
        if heartbeat >= 20:  # ~5 min at 15s
            heartbeat = 0
            log("heartbeat: still tracking (no new events)")


if __name__ == "__main__":
    main()
