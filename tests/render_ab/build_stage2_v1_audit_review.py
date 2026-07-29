"""Audit-grade Stage 2 V1 visual re-review pipeline (replaces INVALID defect-review).

Design forced by audit (INVALID_PENDING_AUDIT on prior artifact):
1. CASE IDENTITY IS LOADED ONLY FROM THE FROZEN MANIFEST. No handwritten or
   image-inferred object labels are permitted; the manifest object_type drives
   everything.
2. RUBRIC APPLICABILITY IS DERIVED FROM object_type, not from what the image
   'looks like'. Weapon checks apply only to weapon classes.
3. EVERY VERDICT CARRIES PAIRED EVIDENCE: source path, candidate path,
   mask-overlay path, full-res crop path, grade, note, reviewer, timestamp.
4. THE SUMMARY VALIDATOR FAILS if:
   - case count != 24
   - allocation != 6/4/4/4/3/3
   - an item is graded on an inapplicable class
   - a case is missing its required crop / evidence reference
   - a face appears despite the facial-cleanup exclusion contract

This script only builds the manifest-driven templates + mask overlays + crops
and VALIDATES consistency. The actual visual grades are filled by a separate
vision pass that MUST reference the per-case template (no free-text grades
without an evidence ref). The validator refuses to emit a summary until every
case has reviewed=True with complete evidence refs.

Usage:
  PYTHONPATH= python tests/render_ab/build_stage2_v1_audit_review.py \
      --manifest .hermes/evidence/stage2-validation-v1-manifest.json \
      --out-dir .hermes/evidence/stage2-v1-audit-reviews
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ALLOC = {
    "sheathed_sword": 6,
    "drawn_sword": 4,
    "scabbard_weapon_repair": 4,
    "non_weapon_prop": 4,
    "hand_repair": 3,
    "clothing_defect": 3,
}
WEAPON_CLASSES = {"sheathed_sword", "drawn_sword", "scabbard_weapon_repair"}

# Per-class rubric. Each item carries the classes it applies to.
RUBRIC = {
    "object_recognizable": "all",
    "placement_attachment_valid": "all",
    "no_duplicate_floating_substitution": "all",
    "identity_preserved": "all",
    "pose_preserved": "all",
    "anatomy_preserved": "all",
    "clothing_composition_preserved": "all",
    # weapon-specific subtle checks
    "sword_guard_hand_alignment": WEAPON_CLASSES,
    "blade_perspective": WEAPON_CLASSES,
    "hand_grip_deformation": WEAPON_CLASSES | {"hand_repair"},
    "fingers_intersect_weapon": WEAPON_CLASSES,
    "scabbard_attachment": {"sheathed_sword", "scabbard_weapon_repair"},
    "lighting_consistency": "all",
    "edge_blending": "all",
    "halo_artifacts": "all",
    "metal_reflections": WEAPON_CLASSES,
    "texture_discontinuities": "all",
# non-weapon / hand / clothing specific
    "prop_plausibility": {"non_weapon_prop"},
    "hand_anatomy_valid": {"hand_repair", "non_weapon_prop"},
    "garment_repair_coherent": {"clothing_defect"},
    "garment_texture_continuity": {"clothing_defect"},
    # PROMPT-CONTRACT GATES (added after audit found "recognizable content" !=
    # "requested edit completed"). These force the reviewer to verify the EXACT
    # requested object/state, copied from the manifest prompt -- not merely that
    # some object is visible.
    "requested_object_present": "all",
    "prompt_semantic_satisfaction": "all",
}

# Expected target, copied verbatim from the frozen manifest prompt per class.
# The reviewer MUST grade requested_object_present against THIS text, not against
# a loose object class. This is what prevents "a sword is visible -> pass" on a
# non-weapon-prop case whose contract is a jade talisman lantern.
EXPECTED_TARGET = {
    "sheathed_sword": "one attached sheathed jian (sword in scabbard)",
    "drawn_sword": "one coherent drawn jian extending from the hand",
    "scabbard_weapon_repair": "one coherent repaired weapon/scabbard assembly",
    "non_weapon_prop": "one palm-sized glowing jade talisman lantern, held or attached naturally near the character, clearly non-weapon",
    "hand_repair": "the repaired target hand (matching the hand_repair intent)",
    "clothing_defect": "one coherent repaired garment region",
}

# Whole-image preservation gates that CANNOT be judged from a local crop alone.
# Their review_basis MUST include full source + candidate + diff + mask_overlay.
WHOLE_IMAGE_GATES = {
    "identity_preserved", "pose_preserved", "clothing_composition_preserved",
    "anatomy_preserved",
}


def applicable_items(object_type: str) -> list[str]:
    out = []
    for item, classes in RUBRIC.items():
        if classes == "all" or object_type in classes:
            out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manparent = args.manifest.resolve().parent
    cases = manifest["cases"]
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- validation gate 1: identity + allocation ----
    if len(cases) != 24:
        print(f"VALIDATION_FAIL: case count {len(cases)} != 24")
        return 2
    alloc = Counter(c.get("object_type") for c in cases)
    if dict(alloc) != EXPECTED_ALLOC:
        print(f"VALIDATION_FAIL: allocation {dict(alloc)} != {EXPECTED_ALLOC}")
        return 2

    # ---- build per-case templates with manifest-derived identity ----
    templates = []
    for c in cases:
        cid = c["case_id"]
        ot = c["object_type"]
        source = (manparent / c["source_path"]).resolve() if c.get("source_path") else None
        cand = ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png"
        mask = (manparent / c["mask_path"]).resolve() if c.get("mask_path") else None
        diff = ROOT / "tests/render_ab/output/stage2_v1" / cid / "diff.png"
        items = []
        for it in applicable_items(ot):
            basis = ["isolated_crop", "mask_overlay"]
            if it in WHOLE_IMAGE_GATES:
                # these require whole-image evidence, not just the local crop
                basis = ["full_source", "full_candidate", "full_diff", "mask_overlay"]
            extra = {}
            if it == "requested_object_present":
                extra["expected_target"] = EXPECTED_TARGET.get(ot, "")
            item_rec = {
                "item": it,
                "applicable": True,
                "grade": "pending",   # MUST be filled by vision pass w/ evidence
                "note": "",
                "evidence_ref": "",    # crop/image ref, required before reviewed=True
                "finding_category": "Observed",
                "review_basis": basis,
            }
            if extra:
                item_rec.update(extra)
            items.append(item_rec)
        rec = {
            "case_id": cid,
            "object_type": ot,
            "strata": c.get("strata"),
            "target_region": c.get("target_region"),
            "expected_target": EXPECTED_TARGET.get(ot, ""),
            "identity_source": "FROZEN_MANIFEST",  # explicit: never image-inferred
            "evidence": {
                "source_path": str(source.relative_to(ROOT)).replace("\\", "/") if source.exists() else None,
                "candidate_path": str(cand.relative_to(ROOT)).replace("\\", "/") if cand.exists() else None,
                "mask_path": str(mask.relative_to(ROOT)).replace("\\", "/") if (mask and mask.exists()) else None,
                "diff_path": str(diff.relative_to(ROOT)).replace("\\", "/") if diff.exists() else None,
                "mask_overlay_path": None,   # built below
                "crop_path": None,           # built by vision pass
                # whole-image evidence refs (required basis for preservation gates)
                "full_source": str(source.relative_to(ROOT)).replace("\\", "/") if source.exists() else None,
                "full_candidate": str(cand.relative_to(ROOT)).replace("\\", "/") if cand.exists() else None,
                "full_diff": str(diff.relative_to(ROOT)).replace("\\", "/") if diff.exists() else None,
            },
            "applicable_items": items,
            "reviewed": False,
            "reviewed_at": None,
            "reviewer": None,
        }
        # build mask overlay (source + mask red tint) for paired-evidence display
        if source.exists() and mask is not None and mask.exists():
            try:
                from PIL import Image
                import numpy as np
                s = np.asarray(Image.open(source).convert("RGB")).astype(int)
                mk = np.asarray(Image.open(mask).convert("L")).astype(int)
                ov = s.copy()
                ov[mk > 127] = (ov[mk > 127] * 0.4 + np.array([255, 0, 0]) * 0.6).astype(int)
                op = out_dir / cid
                op.mkdir(exist_ok=True)
                Image.fromarray(ov.astype("uint8")).save(op / "mask_overlay.png")
                rec["evidence"]["mask_overlay_path"] = \
                    str((op / "mask_overlay.png").relative_to(ROOT)).replace("\\", "/")
            except Exception as exc:  # noqa: BLE001
                rec["evidence"]["mask_overlay_error"] = f"{type(exc).__name__}: {exc}"
        (out_dir / f"{cid}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        templates.append(rec)

    meta = {
        "schema_version": 1,
        "suite": "stage2-v1-audit-review",
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "identity_source": "FROZEN_MANIFEST",
        "allocation": EXPECTED_ALLOC,
        "validation": "templates built; summary blocked until all 24 reviewed with evidence refs",
        "status": "TEMPLATES_PENDING_VISION_PASS",
        "contract_note": "Facial cleanup excluded from V1 (contract line 52); any face present is a contract violation.",
    }
    (out_dir / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({
        "built": str(out_dir),
        "cases": len(templates),
        "allocation_ok": True,
        "next": ("run vision pass per case; for each applicable item set grade+note"
                 "+evidence_ref(crop); set reviewed=True. Then run the validator."),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
