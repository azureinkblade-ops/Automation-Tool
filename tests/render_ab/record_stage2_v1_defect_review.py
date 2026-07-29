"""Record the ordinal high-resolution subtle-defect review for one V1 case.

Writes tests/render_ab/output/stage2_v1/<case_id>/defect-review.json
(kept beside the candidate so the review stays co-located with the artifact it
describes). Mirrors the layout of record_stage2_v1_review.py.

Usage:
    PYTHONPATH= python tests/render_ab/record_stage2_v1_defect_review.py \
        --case-id v1-001 --reviewer human \
        --scores-json '{"grip_alignment":3,...}' \
        --notes-json '{"grip_alignment":"clean"}'
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [
    "grip_alignment", "blade_perspective", "finger_intersections",
    "lighting_consistency", "metal_reflections", "edge_blending",
    "texture_continuity", "halo_artifacts", "scabbard_attachment",
    "overall_realism",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--reviewer", required=True,
                    choices=["human", "auxiliary-vision-proxy"])
    ap.add_argument("--scores-json", required=True, help="JSON map item->0..3")
    ap.add_argument("--notes-json", default="{}", help="JSON map item->note")
    args = ap.parse_args()

    scores = json.loads(args.scores_json)
    notes = json.loads(args.notes_json)
    for it in ITEMS:
        if it not in scores:
            print(f"MISSING_SCORE: {it}")
            return 2
        if not (isinstance(scores[it], int) and 0 <= scores[it] <= 3):
            print(f"BAD_SCORE: {it}={scores[it]}")
            return 2

    blocking = [it for it in ITEMS
                if it in ("grip_alignment", "finger_intersections",
                          "edge_blending", "halo_artifacts") and scores[it] == 0]

    record = {
        "case_id": args.case_id,
        "review_type": "high_resolution_subtle_defect",
        "reviewer": args.reviewer,
        "scale": "0=severe,1=moderate,2=minor,3=none",
        "scores": scores,
        "notes": notes,
        "min_score": min(scores.values()),
        "blocking_defects": blocking,
        "reviewed_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    out_dir = ROOT / "tests/render_ab/output/stage2_v1" / args.case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "defect-review.json"
    out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"written": str(out_path), "blocking_defects": blocking,
                      "min_score": record["min_score"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
