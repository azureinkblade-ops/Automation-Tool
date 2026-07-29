"""Apply the fresh re-judgment pass over the INHERITED items of the 23 valid
cases. Source of fresh grades: _fresh_inherited_grades.json (from vision passes
on evidence panels built by build_evidence_panels.py).

For each inherited item found in the fresh-grades file:
  - overwrite grade with the fresh value
  - set review_freshness = "fresh"
  - set review_basis per the audit evidence-basis table
  - append a note marking it re-judged this pass
Already-fresh items (requested_object_present, prompt_semantic_satisfaction,
prop_plausibility) and v1-020 (excluded) are left untouched.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".hermes/evidence/stage2-v1-audit-reviews"
FRESH = json.load(open(ROOT / "tests/render_ab/_fresh_inherited_grades.json"))

# evidence basis by gate (from the audit table)
BASIS = {
    "object_recognizable": ["target_crop"],
    "placement_attachment_valid": ["context_crop", "full_candidate"],
    "no_duplicate_floating_substitution": ["full_source", "full_candidate", "context_crop"],
    "identity_preserved": ["full_source", "full_candidate", "full_diff", "mask_overlay"],
    "pose_preserved": ["full_source", "full_candidate", "full_diff", "mask_overlay"],
    "anatomy_preserved": ["full_source", "full_candidate", "full_diff", "mask_overlay", "context_crop"],
    "clothing_composition_preserved": ["full_source", "full_candidate", "full_diff", "mask_overlay"],
    "sword_guard_hand_alignment": ["target_crop"],
    "blade_perspective": ["target_crop"],
    "hand_grip_deformation": ["target_crop"],
    "fingers_intersect_weapon": ["target_crop"],
    "scabbard_attachment": ["context_crop", "full_candidate"],
    "lighting_consistency": ["target_crop", "full_candidate"],
    "edge_blending": ["target_crop"],
    "halo_artifacts": ["target_crop"],
    "metal_reflections": ["target_crop"],
    "texture_discontinuities": ["target_crop"],
    "garment_repair_coherent": ["target_crop", "context_crop"],
    "garment_texture_continuity": ["target_crop", "context_crop"],
    "requested_object_present": ["target_crop", "full_candidate", "manifest_prompt"],
    "prompt_semantic_satisfaction": ["full_source", "full_candidate", "target_crop", "manifest_prompt"],
}

for f in sorted(OUT.glob("v1-*.json")):
    cid = f.stem
    d = json.load(open(f, encoding="utf-8"))
    if d.get("evaluation_excluded"):
        continue  # v1-020 untouched
    grades = FRESH.get(cid)
    if not grades:
        continue
    panel = (OUT / cid / "evidence_panel.png")
    panel_rel = str(panel.relative_to(ROOT)).replace("\\", "/") if panel.exists() else None
    for it in d["applicable_items"]:
        item = it["item"]
        if item in grades:
            it["grade"] = grades[item]
            it["review_freshness"] = "fresh"
            it["review_basis"] = BASIS.get(item, ["target_crop"])
            if "[FRESH-REJUDGED on evidence panel]" not in (it.get("note") or ""):
                it["note"] = (it.get("note") or "") + " [FRESH-REJUDGED on evidence panel]"
            if panel_rel:
                it["evidence_ref"] = panel_rel
    # preserve the already-fresh semantic gates
    json.dump(d, open(f, "w"), indent=2)
    print(f"{cid}: re-judged inherited items -> fresh")
print("fresh pass applied to 23 valid cases")
