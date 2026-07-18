"""Characterization tests for youtube_pipeline + growth_analytics (Task 7 extraction).

Required regression contracts (from the plan):
- youtube_build_status(collaborators=...) returns a dict containing a 'running' key.
- queue_youtube_pinned_comment(upload) appends/updates an item in the comment queue and
  returns the queued record (with 'status' key).
- growth_analytics re-exports the growth_scheduler public API.

Run: python tests/test_youtube_pipeline.py   (from repo root)
"""
import os, sys, json, tempfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import youtube_pipeline as yp
import growth_analytics as ga

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- youtube_build_status returns dict with 'running' key (collaborators injected) ---
YP_COLLAB = {n: getattr(app_mod, n) for n in yp.REQUIRED_COLLABORATORS if hasattr(app_mod, n)}

def fake_resolve(folder_value, *, include_campaigns=False):
    return Path(folder_value).resolve() if folder_value else Path(tempfile.gettempdir())
def fake_media_valid(path, kind="v:0"):
    return Path(str(path)).exists()
def fake_duration(path):
    return 12.0 if Path(str(path)).exists() else 0.0
def fake_min_duration(folder):
    return 8.0

YP_COLLAB["resolve_youtube_pack_folder"] = fake_resolve
YP_COLLAB["media_file_valid"] = fake_media_valid
YP_COLLAB["media_duration_seconds"] = fake_duration
YP_COLLAB["expected_youtube_min_duration"] = fake_min_duration

# A temp folder whose youtube-build-status.json says running=True
tmpf = Path(tempfile.mkdtemp(prefix="yt_status_"))
(tmpf / "youtube-build-status.json").write_text(json.dumps({"running": True, "startedAt": "2026-07-17 10:00:00"}), encoding="utf-8")
(tmpf / "youtube-video.mp4").write_text("fake", encoding="utf-8")
status = yp.youtube_build_status(str(tmpf), collaborators=YP_COLLAB)
check("youtube_build_status is dict", isinstance(status, dict), True)
check("youtube_build_status has running key", "running" in status, True)
check("youtube_build_status running matches", status.get("running"), True)
check("youtube_build_status videoExists", status.get("videoExists"), True)
check("youtube_build_status duration", status.get("duration"), 12.0)

# structural parity: our injected result has the same keys app.py would populate for a
# valid folder (app validates the folder path, so we compare against the documented shape)
check("youtube_build_status has expected keys",
      all(k in status for k in ("folder", "statusFile", "video", "videoExists", "videoValid", "duration", "minimumDuration")), True)

# --- queue_youtube_pinned_comment queues an item ---
def fake_load_queue():
    qf = yp.YOUTUBE_COMMENT_QUEUE_FILE
    data = yp.read_json_safe(qf)
    if not isinstance(data, dict):
        data = {"items": []}
    data.setdefault("items", [])
    return data
YP_COLLAB["load_youtube_comment_queue"] = fake_load_queue
YP_COLLAB["youtube_pinned_comment_text"] = lambda meta: "Pin this chapter!"

# use a temp queue file so we don't touch the real one
tmp_queue = Path(tempfile.mkdtemp(prefix="yt_q_")) / "youtube-comment-queue.json"
yp.YOUTUBE_COMMENT_QUEUE_FILE = tmp_queue
yp.YOUTUBE_COMMENT_QUEUE_LOCK = None  # uses _NullLock

upload = {"id": "u123", "folder": str(tmpf), "title": "Chapter 10",
          "metadata": {"abbr": "EN", "chapter": "10"}, "pinned_comment": "Great chapter!"}
queued = yp.queue_youtube_pinned_comment(upload, collaborators=YP_COLLAB)
check("queue returns record", isinstance(queued, dict), True)
check("queue record has status", "status" in queued, True)
check("queue record uploadId", queued.get("uploadId"), "u123")
check("queue record comment", queued.get("comment"), "Great chapter!")
# a second call with same uploadId updates rather than duplicates
queued2 = yp.queue_youtube_pinned_comment(upload, collaborators=YP_COLLAB)
qdata = json.loads(tmp_queue.read_text(encoding="utf-8"))
check("queue has single item for same uploadId", len(qdata["items"]), 1)

# --- growth_analytics re-exports growth_scheduler ---
import growth_scheduler as sched
for name in ("NOVEL_ORDER", "GOALS", "GOAL_CTAS", "HOOK_TEMPLATES", "WEEKDAYS", "DEFAULT_WEIGHTS",
             "build_weekly_growth_plan", "weighted_novel_slots", "normalize_weights",
             "monday_for", "cta_for_goal", "engagement_score"):
    check(f"growth_analytics re-exports {name}", getattr(ga, name) is getattr(sched, name), True)

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all youtube_pipeline + growth_analytics characterization checks")
