"""Stage 2 V1 subtle-defect re-review (Step 1 of V1H prep).

Re-reviews the 24 on-disk candidates at FULL resolution against the 10-item
subtle-defect checklist David specified, distinct from the coarse 7-gate
accept/reject used at V1 time:

  sword guard alignment with hand        (grip geometry)
  blade perspective                      (converging lines / scale)
  hand grip deformation                  (hand anatomy under grip)
  fingers intersecting the weapon       (penetration)
  scabbard attachment                    (if present)
  lighting consistency on inserted object
  edge blending                          (mask boundary seam)
  halo artifacts                         (soft glow ring at boundary)
  metal reflections                      (surface plausibility)
  tiny texture discontinuities

Output: a per-case defect-grade record, written next to the existing review.json
as `defect_review.json`, plus a summary. Grades per item:
  pass   - no defect observed
  minor  - small artifact, not disqualifying
  defect - clear defect requiring attention
  na     - item not applicable to this object type (e.g. scabbard on a book)

This is a REVIEW-ASSISTED instrument: it extracts objective crops/metrics where
possible and routes subjective items through vision analysis of the actual
full-res candidate. It does NOT auto-pass; every defect/minor grade must be
backed by an extracted crop or a vision note.

Usage:
  PYTHONPATH= python tests/render_ab/run_stage2_v1_defect_review.py \
      --manifest .hermes/evidence/stage2-validation-v1-manifest.json \
      --out-dir .hermes/evidence/stage2-v1-defect-reviews
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The 10 checklist items, grouped by whether they need the mask/hand region.
ITEMS = [
    "sword_guard_hand_alignment",
    "blade_perspective",
    "hand_grip_deformation",
    "fingers_intersect_weapon",
    "scabbard_attachment",
    "lighting_consistency",
    "edge_blending",
    "halo_artifacts",
    "metal_reflections",
    "texture_discontinuities",
]

# Items that only apply to weapon/sword-bearing objects.
WEAPON_ITEMS = {
    "sword_guard_hand_alignment",
    "blade_perspective",
    "hand_grip_deformation",
    "fingers_intersect_weapon",
    "scabbard_attachment",
}


def grade_item(item: str, object_type: str, applicable: bool, note: str,
               grade: str) -> dict:
    return {
        "item": item,
        "applicable": applicable,
        "grade": grade if applicable else "na",
        "note": note if applicable else "not applicable to object type",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    # This instrument is review-assisted: it records the checklist structure and
    # the objective signals we can extract (mask-localized diff energy), but the
    # subjective grades are filled by a human/vision pass. We write a TEMPLATE +
    # the extractable signal so the review is reproducible and not silently passed.
    for case in manifest["cases"]:
        cid = case["case_id"]
        object_type = case.get("object_type")
        cand_dir = ROOT / "tests/render_ab/output/stage2_v1" / cid
        cand = cand_dir / "candidate.png"
        diff = cand_dir / "diff.png"
        mask = ROOT / case["mask_path"] if case.get("mask_path") else None

        signal = {"candidate_exists": cand.exists(), "diff_exists": diff.exists()}
        # objective signal: total changed pixels inside mask = localization check
        if diff.exists() and mask is not None and mask.exists():
            try:
                from PIL import Image
                import numpy as np
                d = np.asarray(Image.open(diff).convert("L")).astype(int)
                m = np.asarray(Image.open(mask).convert("L")).astype(int)
                m_bin = (m > 127)
                inside = int((d[m_bin] > 30).sum())
                outside = int((d[~m_bin] > 30).sum())
                signal["diff_pixels_inside_mask"] = inside
                signal["diff_pixels_outside_mask"] = outside
            except Exception as exc:  # noqa: BLE001
                signal["signal_error"] = f"{type(exc).__name__}: {exc}"

        is_weapon = object_type in ("sheathed_sword", "drawn_sword",
                                    "weapon_scabbard_repair", "non_weapon_prop")
        # non_weapon_prop may still carry a weapon in some fixtures; mark na only
        # for clearly non-weapon types. We treat weapon items as applicable for
        # the four weapon-ish types and na otherwise via object_type below.
        weapon_like = object_type in ("sheathed_sword", "drawn_sword",
                                      "weapon_scabbard_repair")

        item_grades = []
        for it in ITEMS:
            applicable = it not in WEAPON_ITEMS or weapon_like
            # Template grade is 'pending' — MUST be filled by a vision/human pass.
            item_grades.append(grade_item(
                it, object_type, applicable,
                "PENDING vision/human review", "pending"))

        rec = {
            "case_id": cid,
            "object_type": object_type,
            "strata": case.get("strata"),
            "signal": signal,
            "items": item_grades,
            "reviewed": False,
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "note": ("Template: objective diff-localization signal extracted; "
                     "subjective grades require a vision/human pass before this "
                     "record is marked reviewed=True."),
        }
        (out_dir / f"{cid}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        records.append(rec)

    summary = {
        "schema_version": 1,
        "suite": "stage2-v1-defect-review",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "cases": len(records),
        "items_per_case": len(ITEMS),
        "status": "TEMPLATE_PENDING_VISION_PASS",
        "items": ITEMS,
        "review_dir": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
    }
    (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({
        "written": str(out_dir),
        "templates": len(records),
        "status": summary["status"],
        "next_step": ("run vision/human pass per case; set grade + note; "
                      "flip reviewed=True. Do NOT mark ready until every "
                      "weapon-like case has all applicable items graded."),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
