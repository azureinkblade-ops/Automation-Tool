from __future__ import annotations

import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def timed(name: str, fn):
    started = time.perf_counter()
    try:
        value = fn()
        ok = True
        error = ""
    except Exception as exc:
        value = None
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    summary = ""
    if isinstance(value, list):
        summary = f"list[{len(value)}]"
    elif isinstance(value, dict):
        summary = "dict{" + ", ".join(list(value.keys())[:8]) + "}"
    return {
        "name": name,
        "ok": ok,
        "seconds": round(elapsed, 3),
        "summary": summary,
        "error": error,
    }


def main() -> int:
    app.load_env_file()
    checks = [
        ("pack_control_blank", lambda: app.pack_control_summary("")),
        ("deep_fast_5", lambda: app.existing_deep_tiktok_packs(False, 5, True)),
        ("pending_deep_tiktok_items", app.pending_deep_tiktok_items),
        ("pending_daily_shorts_items", app.pending_daily_shorts_items),
        ("pending_patreon_items", app.pending_patreon_items),
        ("pending_manual_social_items", app.pending_manual_social_items),
        ("unresolved_recovery_items", app.unresolved_recovery_items),
        ("comment_assistant_status", app.comment_assistant_status),
        ("youtube_created_not_uploaded", app.youtube_created_not_uploaded),
        ("deep_fast_20", lambda: app.existing_deep_tiktok_packs(False, 20, True)),
        ("story_hook_fast_20", lambda: app.story_hook_video_packs(20, True)),
        ("release_cached", lambda: app.chapter_release_upload_queue_status(False)),
        ("youtube_status_cached", lambda: app.read_youtube_daily_status(False)),
        ("approval_inbox", app.approval_inbox),
    ]
    report = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checks": [timed(name, fn) for name, fn in checks],
    }
    path = ROOT / "app-function-profile.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if any(not item["ok"] for item in report["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
