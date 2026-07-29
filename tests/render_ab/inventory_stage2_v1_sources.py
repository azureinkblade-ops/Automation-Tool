"""Inventory candidate source images for the Stage 2 V1 validation suite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXCLUDED_PARTS = {
    "stage2_refinement_replay",
    "track4_inpaint",
}
EXCLUDED_NAME_TERMS = (
    "mask",
    "guide",
    "diff",
    "candidate",
    "detected",
    "pose",
    "clean_kneel_ref",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from PIL import Image

    rows = []
    for path in sorted(args.root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        relative = path.relative_to(args.root)
        lowered_parts = {part.lower() for part in relative.parts}
        lowered_name = path.name.lower()
        exclusion = None
        if lowered_parts & EXCLUDED_PARTS:
            exclusion = "derived_stage2_or_track4_artifact"
        elif any(term in lowered_name for term in EXCLUDED_NAME_TERMS):
            exclusion = "mask_guide_diff_candidate_or_pose_asset"
        try:
            with Image.open(path) as image:
                width, height = image.size
                mode = image.mode
        except Exception as exc:
            rows.append({"path": str(path), "eligible": False, "exclusion": f"unreadable:{type(exc).__name__}"})
            continue
        rows.append({
            "path": str(path),
            "relative_path": relative.as_posix(),
            "sha256": sha256(path),
            "width": width,
            "height": height,
            "mode": mode,
            "eligible": exclusion is None and width >= 512 and height >= 512,
            "exclusion": exclusion or (None if width >= 512 and height >= 512 else "below_512"),
        })

    unique_eligible = {}
    for row in rows:
        if row.get("eligible"):
            unique_eligible.setdefault(row["sha256"], row)
    payload = {
        "schema_version": 1,
        "root": str(args.root.resolve()),
        "total_images": len(rows),
        "eligible_rows": sum(1 for row in rows if row.get("eligible")),
        "unique_eligible_sources": len(unique_eligible),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("total_images", "eligible_rows", "unique_eligible_sources")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
