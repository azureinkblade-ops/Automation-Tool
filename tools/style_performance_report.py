"""Workstream F: compare post performance by LoRA style track.

Reads the `style_track` column on `platform_post_metrics` (populated by
`automation_db.record_post_style_track` / `backfill_style_tracks_from_packs`) and
aggregates engagement by track so David can see which image style (azink_main vs
azink_real vs azink_comic) performs better on Shorts/Reels/TikTok.

Usage:
    python tools/style_performance_report.py            # full comparison
    python tools/style_performance_report.py --backfill  # first scan packs into metrics, then report

With no engagement rows yet, it reports per-track pack coverage from tiktok-posts
as a stand-in so the comparison is never empty.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import automation_db as db  # noqa: E402


def _aggregate_from_metrics(root: Path) -> dict[str, dict]:
    db_path = db.db_path(root)
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT style_track,
                   COUNT(*) AS posts,
                   SUM(views) AS views,
                   SUM(impressions) AS impressions,
                   SUM(engagements) AS engagements
            FROM platform_post_metrics
            WHERE style_track IS NOT NULL AND style_track != ''
            GROUP BY style_track
            """
        ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        posts = r["posts"] or 0
        engagements = r["engagements"] or 0
        views = r["views"] or 0
        rate = (engagements / views) if views else 0.0
        out[r["style_track"]] = {
            "posts": posts,
            "views": views,
            "impressions": r["impressions"] or 0,
            "engagements": engagements,
            "engagement_rate": round(rate, 4),
        }
    return out


def _pack_coverage(root: Path) -> dict[str, int]:
    tiktok_dir = root / "tiktok-posts"
    counts: dict[str, int] = defaultdict(int)
    if not tiktok_dir.exists():
        return {}
    for meta in tiktok_dir.glob("*/metadata.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        track = data.get("pack_track") or data.get("style_track")
        if track:
            counts[track] += 1
    return dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare post performance by LoRA style track.")
    parser.add_argument("--backfill", action="store_true", help="Scan tiktok-posts into platform_post_metrics first.")
    parser.add_argument("--root", default=str(ROOT), help="Repo root (default: parent of tools/).")
    args = parser.parse_args()
    root = Path(args.root)

    if args.backfill:
        n = db.backfill_style_tracks_from_packs(root)
        print(f"[backfill] wrote style_track for {n} packs\n")

    metrics = _aggregate_from_metrics(root)
    coverage = _pack_coverage(root)

    print("=== Style performance (platform_post_metrics) ===")
    if not metrics:
        print("(no engagement rows yet — run Buffer metric collection, or use --backfill for pack coverage)")
    else:
        header = f"{'track':<18}{'posts':>7}{'views':>10}{'engagements':>13}{'rate':>9}"
        print(header)
        print("-" * len(header))
        for track, m in sorted(metrics.items(), key=lambda kv: kv[1]["engagement_rate"], reverse=True):
            print(f"{track:<18}{m['posts']:>7}{m['views']:>10}{m['engagements']:>13}{m['engagement_rate']:>9}")

    print("\n=== Pack coverage (tiktok-posts metadata pack_track) ===")
    if not coverage:
        print("(no packs with pack_track recorded yet)")
    else:
        for track, c in sorted(coverage.items(), key=lambda kv: kv[1], reverse=True):
            print(f"{track:<18}{c:>7} packs")

    # Verdict hint when both present
    if metrics:
        best = max(metrics.items(), key=lambda kv: kv[1]["engagement_rate"])
        print(f"\nBest-performing style by engagement rate: {best[0]} ({best[1]['engagement_rate']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
