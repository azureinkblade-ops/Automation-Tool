"""Characterization tests for youtube_pipeline + growth_analytics (Task 7 extraction).

Required regression contracts (from the plan):
- youtube_build_status(collaborators=...) returns a dict containing a 'running' key.
- queue_youtube_pinned_comment(upload) appends/updates an item in the comment queue and
  returns the queued record (with 'status' key).
- growth_analytics re-exports the growth_scheduler public API.

The harness now runs against an ISOLATED temporary repository root + temporary
SQLite database. The queued comment is mirrored into the isolated SQLite
state_snapshots (the youtubeCommentQueue repository home) and verified through
its repository API. The queue's active JSON file uses a NON-retired name inside
the isolated root, so no retired mirror (youtube-comment-queue.json) is created.

Run: python tests/test_youtube_pipeline.py   (from repo root)

NOTE: standalone characterization script. The executable body is guarded by
``if __name__ == "__main__":`` so pytest can import the module for collection
without executing it.
"""
import os, sys, json, tempfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _main():
    import app as app_mod
    import youtube_pipeline as yp
    import growth_analytics as ga
    import app_config as config
    from storage import database as storage_db
    from storage import root_state_repository as rs_repo
    from storage.retired_state import RETIRED_FILE_NAMES

    FAILS = []

    def check(name, got, want):
        if got != want:
            FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

    # --- isolated repository root + SQLite database ---
    ROOT = Path(tempfile.mkdtemp(prefix="yt_iso_"))
    storage_db.initialize_databases(ROOT)
    # Active queue file (NON-retired name) lives inside the isolated root.
    ACTIVE_QUEUE = ROOT / "youtube-comment-queue-active.json"
    config.YOUTUBE_COMMENT_QUEUE_FILE = ACTIVE_QUEUE
    yp.YOUTUBE_COMMENT_QUEUE_FILE = ACTIVE_QUEUE
    yp.YOUTUBE_COMMENT_QUEUE_LOCK = None  # uses _NullLock

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

    tmpf = Path(tempfile.mkdtemp(prefix="yt_status_"))
    (tmpf / "youtube-build-status.json").write_text(json.dumps({"running": True, "startedAt": "2026-07-17 10:00:00"}), encoding="utf-8")
    (tmpf / "youtube-video.mp4").write_text("fake", encoding="utf-8")
    status = yp.youtube_build_status(str(tmpf), collaborators=YP_COLLAB)
    check("youtube_build_status is dict", isinstance(status, dict), True)
    check("youtube_build_status has running key", "running" in status, True)
    check("youtube_build_status running matches", status.get("running"), True)
    check("youtube_build_status videoExists", status.get("videoExists"), True)
    check("youtube_build_status duration", status.get("duration"), 12.0)
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

    upload = {"id": "u123", "folder": str(tmpf), "title": "Chapter 10",
              "metadata": {"abbr": "EN", "chapter": "10"}, "pinned_comment": "Great chapter!"}
    queued = yp.queue_youtube_pinned_comment(upload, collaborators=YP_COLLAB)
    check("queue returns record", isinstance(queued, dict), True)
    check("queue record has status", "status" in queued, True)
    check("queue record uploadId", queued.get("uploadId"), "u123")
    check("queue record comment", queued.get("comment"), "Great chapter!")
    # a second call with same uploadId updates rather than duplicates
    queued2 = yp.queue_youtube_pinned_comment(upload, collaborators=YP_COLLAB)

    # --- verify the queued payload through the repository API (isolated SQLite) ---
    # The active JSON file holds the queue; mirror it into the isolated SQLite
    # state_snapshots[youtubeCommentQueue] (the repository home) and read it back.
    queued_queue = yp.read_json_safe(ACTIVE_QUEUE)
    rs_repo.save(ROOT, "youtubeCommentQueue", queued_queue)
    loaded = rs_repo.load(ROOT, "youtubeCommentQueue")
    check("repository load returns dict", isinstance(loaded, dict), True)
    items = loaded.get("items", []) if isinstance(loaded, dict) else []
    check("repository queue has single item for same uploadId", len(items), 1)
    check("repository queued uploadId", items[0].get("uploadId") if items else None, "u123")
    check("repository queued comment", items[0].get("comment") if items else None, "Great chapter!")

    # --- Phase-3 guard: NO retired mirror (youtube-comment-queue.json) is created ---
    retired_found = [n for n in RETIRED_FILE_NAMES if (ROOT / n).exists()]
    check("no retired mirror in isolated root", retired_found, [])
    check("no youtube-comment-queue.json created", (ROOT / "youtube-comment-queue.json").exists(), False)

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
    print("PASS all youtube_pipeline + growth_analytics characterization checks (isolated SQLite)")


if __name__ == "__main__":
    _main()
