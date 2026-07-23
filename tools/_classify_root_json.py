"""Draft classification of root JSON files into SC-7 disposition buckets.

Writes tools/_root_json_classification.json (one row per file). Pure analysis;
moves nothing. Used to review dispositions before quarantine.
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PY = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")


def bucket(name: str) -> str:
    n = name.lower()
    active = {
        "release_status.json", "release-automation-state.json", "automatic-metrics-state.json",
        "pinned-content-plan.json", "pinned-profile-assets.json", "youtube-comment-queue.json",
        "story-hook-chatgpt-result.json", "creator-benchmarks.json", "analytics-lab.json",
        "app-regression-dashboard.json", "youtube-end-screen-plan.json", "youtube-end-screen-state.json",
    }
    if name in active:
        return "1-active-keep"
    if n.startswith("chapter-release-queue") and "backup" in n:
        return "1-active-keep"  # backups of a live queue; held per plan
    # Bucket 4: probe / large scraped dumps (transient) — before generic royal-road/patreon
    if ("probe" in n or n.endswith("-probe.json") or "dashboard" in n or "pages" in n
            or n.startswith("royal-road-") or n.startswith("patreon-path-")):
        return "4-probe-quarantine"
    # Bucket 5: cron context (HELD — referenced by scheduled tasks; confirm before quarantine)
    if n.startswith("cron-en") or n in {
        "en_context.json", "en_ctx.json", "ha_ctx.json", "hp_ctx.json", "sf_ctx.json",
    }:
        return "5-cron-context"
    # Bucket 2: chapter import/result scratch
    if (re.search(r"^(en|ha|hp|sf)[_-]?(ch)?\d+", n) or n.endswith("_import.json")
            or n.endswith("_result.json")):
        return "2-chapter-scratch-quarantine"
    # Bucket 3: regression / CI scratch (+ unclassified scratch)
    if n.startswith("reg_") or n in {
        "q0.json", "q1.json", "al.json", "app-smoke-report.json",
        "manual-posts-playwright-result.json", "creator-benchmarks-playwright-results.json",
        "release-browser-probe.json", "reg_out.json", "reg_tmp14.json", "reg_tmp15.json",
        "reg_tmp16.json", "_test_sunday_gen.png.local-sd.json", "app-function-profile.json",
        "automation-server-launch.json", "regression-report.json",
    }:
        return "3-regression-scratch-quarantine"
    return "0-unclassified"


DISPOSITION = {
    "1-active-keep": "keep",
    "2-chapter-scratch-quarantine": "quarantine",
    "3-regression-scratch-quarantine": "quarantine",
    "4-probe-quarantine": "quarantine",
    "5-cron-context": "hold",
    "0-unclassified": "review",
}


def main() -> None:
    rows = []
    for p in sorted(ROOT.glob("*.json")):
        if p.name.startswith("."):
            continue
        name = p.name
        try:
            json.loads(p.read_text(encoding="utf-8", errors="replace"))
            valid = True
        except Exception:
            valid = False
        rows.append({
            "name": name,
            "size": p.stat().st_size,
            "valid_json": valid,
            "bucket": bucket(name),
            "disposition": DISPOSITION[bucket(name)],
            "app_referenced": name in APP_PY,
        })
    cnt = Counter(r["bucket"] for r in rows)
    print("TOTAL", len(rows))
    for k, v in sorted(cnt.items()):
        print(f"  {k}: {v}")
    out = ROOT / "tools" / "_root_json_classification.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
