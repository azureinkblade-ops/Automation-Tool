"""Characterization tests for approval_inbox (Task 4 extraction).

Required regression contracts (from the plan):
- approval_inbox() returns a dict with 'counts' + 'total'.
- Image approval still blocks weak/unapproved media: filter_uncleared_approval_items
  must DROP items whose pack folder's metadata packStatus is a "done" state for the
  relevant kind (deepTikToks/youtube/failures gating).

Run: python tests/test_approval_inbox.py   (from repo root)
"""
import os, sys, tempfile, json
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import approval_inbox as ai

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- build a collaborator map from the REAL app functions for every required name ---
collab = {name: getattr(app_mod, name) for name in ai.REQUIRED_COLLABORATORS}

# --- approval_inbox returns counts + total and matches app.py ---
inbox = ai.approval_inbox(collaborators=collab)
check("approval_inbox is dict", isinstance(inbox, dict), True)
check("approval_inbox has counts", "counts" in inbox, True)
check("approval_inbox has total", "total" in inbox, True)
check("total == sum(counts)", inbox["total"], sum(inbox["counts"].values()))

app_inbox = app_mod.approval_inbox()
check("counts match app.py", inbox["counts"], app_inbox["counts"])
check("total matches app.py", inbox["total"], app_inbox["total"])

# --- weak-media blocking contract: filter_uncleared_approval_items drops done packs ---
TMP = Path(tempfile.mkdtemp(prefix="ai_test_"))
# youtube kind: a folder whose metadata says packStatus 'posted' must be filtered out
yt_folder = TMP / "yt_done"
yt_folder.mkdir()
(yt_folder / "metadata.json").write_text(json.dumps({"abbr": "EN", "chapter": "10", "packStatus": "posted"}), encoding="utf-8")
blocked_yt = [
    {"abbr": "EN", "chapter": "10", "folder": str(yt_folder), "video": "abc"},
]
got_yt = ai.filter_uncleared_approval_items("youtube", blocked_yt, {}, {})
check("youtube done-pack filtered out", got_yt, [])

# youtube kind: a folder still 'uploading' (not done) must be KEPT
yt_live = TMP / "yt_live"
yt_live.mkdir()
(yt_live / "metadata.json").write_text(json.dumps({"abbr": "EN", "chapter": "10", "packStatus": "uploading"}), encoding="utf-8")
live_yt = [
    {"abbr": "EN", "chapter": "10", "folder": str(yt_live), "video": "abc"},
]
got_live = ai.filter_uncleared_approval_items("youtube", live_yt, {}, {})
check("youtube live-pack kept", len(got_live), 1)

# deepTikToks kind: packStatus in PACK_DONE_STATUSES must be dropped
dt_folder = TMP / "dt_done"
dt_folder.mkdir()
(dt_folder / "metadata.json").write_text(json.dumps({"abbr": "EN", "chapter": "10", "packStatus": "queued"}), encoding="utf-8")
blocked_dt = [{"abbr": "EN", "chapter": "10", "folder": str(dt_folder)}]
got_dt = ai.filter_uncleared_approval_items("deepTikToks", blocked_dt, {}, {})
check("deepTikToks done-pack filtered out", got_dt, [])

# matches app.py's gating for the same fixtures
app_yt = app_mod.filter_uncleared_approval_items("youtube", blocked_yt, {}, {})
check("youtube gating matches app.py", got_yt, app_yt)
app_dt = app_mod.filter_uncleared_approval_items("deepTikToks", blocked_dt, {}, {})
check("deepTikToks gating matches app.py", got_dt, app_dt)

# --- keying is stable + matches app.py ---
k1 = ai.approval_item_key("youtube", {"abbr": "EN", "chapter": "10", "video": "abc"})
k2 = app_mod.approval_item_key("youtube", {"abbr": "EN", "chapter": "10", "video": "abc"})
check("approval_item_key matches app.py", k1, k2)

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all approval_inbox characterization checks (counts/total parity + weak-media blocking)")
