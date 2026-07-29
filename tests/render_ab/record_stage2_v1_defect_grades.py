"""Persist the V1 subtle-defect re-review grades gathered from full-res vision
passes into the per-case defect_review.json templates, then emit a summary.

Grades are recorded exactly as assessed during the vision pass (pass/minor/
defect/na). This is the review-assistant's structured record; it is NOT an
automated pass. The artifact is the honest output of the manual inspection
David requested.

Run:
  PYTHONPATH= python tests/render_ab/record_stage2_v1_defect_grades.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".hermes/evidence/stage2-v1-defect-reviews"

# (case_id, item) -> (grade, note). grades: pass / minor / defect / na
G = {
    # v1-001
    "v1-001": {
        "sword_guard_hand_alignment": ("pass", "crossguard horizontal above grip, plausible"),
        "blade_perspective": ("defect", "blade flat/2D, no cylindrical volume or convergence"),
        "hand_grip_deformation": ("minor", "grip hand stiff, low knuckle definition"),
        "fingers_intersect_weapon": ("pass", "fingers wrap hilt, no clip"),
        "scabbard_attachment": ("na", "sword unsheathed"),
        "lighting_consistency": ("defect", "cool blue blade ignores warm firelight"),
        "edge_blending": ("minor", "seam at hand/hilt; blade stands out vs bg"),
        "halo_artifacts": ("na", "none"),
        "metal_reflections": ("defect", "matte, no specular/reflections"),
        "texture_discontinuities": ("defect", "over-smooth blade vs detailed armor"),
    },
    # v1-002
    "v1-002": {
        "sword_guard_hand_alignment": ("pass", "guard aligns with grip; central scabbard centred"),
        "blade_perspective": ("minor", "central scabbard perfectly vertical vs leaning stance"),
        "hand_grip_deformation": ("minor", "left fingers slightly elongated/merged"),
        "fingers_intersect_weapon": ("pass", "no clip"),
        "scabbard_attachment": ("minor", "hangs center crotch, attachment vague"),
        "lighting_consistency": ("defect", "cool flat scabbard vs warm key light"),
        "edge_blending": ("defect", "sharp scabbard edge vs smoke, cut-paste look"),
        "halo_artifacts": ("minor", "slight dark halo around scabbard"),
        "metal_reflections": ("defect", "scabbard fully matte"),
        "texture_discontinuities": ("minor", "uniform ribbed scabbard texture"),
    },
    # v1-003
    "v1-003": {
        "sword_guard_hand_alignment": ("pass", "roughly centred, hand slightly small for blade"),
        "blade_perspective": ("defect", "uniform width, flat 2D, no taper"),
        "hand_grip_deformation": ("minor", "left hand stiff/claw-like, fused fingers"),
        "fingers_intersect_weapon": ("pass", "no clip through blade"),
        "scabbard_attachment": ("na", "no scabbard"),
        "lighting_consistency": ("defect", "cool blue ignores warm ambient/rim"),
        "edge_blending": ("minor", "soft seam at hand/hilt"),
        "halo_artifacts": ("minor", "soft bloom near blade tip/edges"),
        "metal_reflections": ("defect", "matte plastic-like, no specular"),
        "texture_discontinuities": ("defect", "perfectly smooth blade vs detailed scene"),
    },
    # v1-004
    "v1-004": {
        "sword_guard_hand_alignment": ("pass", "crossguard horizontal above grip"),
        "blade_perspective": ("defect", "uniform width, flat ruler-like, no taper"),
        "hand_grip_deformation": ("defect", "left hand blobby/mitten, no articulation"),
        "fingers_intersect_weapon": ("defect", "fingers clip/merge into hilt"),
        "scabbard_attachment": ("na", "unsheathed"),
        "lighting_consistency": ("minor", "cool highlight slightly disconnected from warm scene"),
        "edge_blending": ("pass", "blends into bg"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "plausible highlights on spear/sword"),
        "texture_discontinuities": ("minor", "rock under feet smoother than surroundings"),
    },
    # v1-005
    "v1-005": {
        "sword_guard_hand_alignment": ("pass", "hand rests near scabbard tip, passive plausible"),
        "blade_perspective": ("pass", "scabbard vertical/slight angle, scale ok"),
        "hand_grip_deformation": ("defect", "left hand skeletal/claw, thumb oversized"),
        "fingers_intersect_weapon": ("minor", "fingers overlap lower scabbard"),
        "scabbard_attachment": ("pass", "belt frog on left hip, secure"),
        "lighting_consistency": ("pass", "consistent upper-left-front key"),
        "edge_blending": ("pass", "clean extraction, no seam"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "buckle/sword tip specular plausible"),
        "texture_discontinuities": ("minor", "thigh embroidery blurrier than sleeve"),
    },
    # v1-006
    "v1-006": {
        "sword_guard_hand_alignment": ("pass", "horizontal fitting above hands, plausible"),
        "blade_perspective": ("pass", "parallel lines, consistent scale"),
        "hand_grip_deformation": ("minor", "left hand blocky/mitten, no finger sep"),
        "fingers_intersect_weapon": ("minor", "left fingers merge/clip into scabbard"),
        "scabbard_attachment": ("na", "held in hands"),
        "lighting_consistency": ("pass", "cool highlights consistent with scene"),
        "edge_blending": ("pass", "seamless"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "stylized flat highlights fit style"),
        "texture_discontinuities": ("minor", "waist armor pattern abrupt under robe fold"),
    },
    # v1-007
    "v1-007": {
        "sword_guard_hand_alignment": ("pass", "crossguard correct vs grip"),
        "blade_perspective": ("minor", "flat/wide, lacks volume/taper"),
        "hand_grip_deformation": ("minor", "grip hand indistinct/fused"),
        "fingers_intersect_weapon": ("pass", "no clip"),
        "scabbard_attachment": ("pass", "belt on right hip, natural hang"),
        "lighting_consistency": ("minor", "blue glow flat, casts little light on scene"),
        "edge_blending": ("pass", "seamless"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "armor/hilt plausible"),
        "texture_discontinuities": ("pass", "continuous textures"),
    },
    # v1-008
    "v1-008": {
        "sword_guard_hand_alignment": ("minor", "left-hand guard obscured, wrist slightly off"),
        "blade_perspective": ("defect", "horizontal blade flat 2D plane, no volume"),
        "hand_grip_deformation": ("defect", "left hand claw-like, thumb merged"),
        "fingers_intersect_weapon": ("defect", "fingers clip/merge into hilt"),
        "scabbard_attachment": ("na", "none visible"),
        "lighting_consistency": ("defect", "horizontal blade cool white like light source"),
        "edge_blending": ("defect", "hard edge vs fire haze, pasted layer"),
        "halo_artifacts": ("defect", "faint white/blue halo on blade"),
        "metal_reflections": ("defect", "uniform matte, no specular"),
        "texture_discontinuities": ("defect", "smooth blade vs detailed armor"),
    },
    # v1-009
    "v1-009": {
        "sword_guard_hand_alignment": ("minor", "hands small/indistinct vs hilt"),
        "blade_perspective": ("defect", "small sword flat 2D"),
        "hand_grip_deformation": ("minor", "hands melted/indistinct"),
        "fingers_intersect_weapon": ("minor", "left fingers soft-merge into hilt"),
        "scabbard_attachment": ("minor", "sheath on hip, attachment slightly floating"),
        "lighting_consistency": ("defect", "small sword stark white vs warm fire"),
        "edge_blending": ("pass", "smooth into smoke/fire"),
        "halo_artifacts": ("pass", "natural atmospheric glow"),
        "metal_reflections": ("minor", "small sword flat, no reflections"),
        "texture_discontinuities": ("minor", "cloak very smooth; bg stone repetitive"),
    },
    # v1-010
    "v1-010": {
        "sword_guard_hand_alignment": ("pass", "crossguards above grips"),
        "blade_perspective": ("minor", "blades long/thin, slightly flat perspective"),
        "hand_grip_deformation": ("minor", "left hand claw-like fused; right stiff"),
        "fingers_intersect_weapon": ("pass", "no clip"),
        "scabbard_attachment": ("na", "both drawn"),
        "lighting_consistency": ("pass", "rim light from orb consistent"),
        "edge_blending": ("pass", "seamless"),
        "halo_artifacts": ("pass", "natural rim, no digital halo"),
        "metal_reflections": ("pass", "blades reflect warm light"),
        "texture_discontinuities": ("minor", "chest armor smooth/repetitive"),
    },
    # v1-011
    "v1-011": {
        "sword_guard_hand_alignment": ("pass", "blue sword crossguard above right hand"),
        "blade_perspective": ("pass", "vertical, consistent"),
        "hand_grip_deformation": ("defect", "left hand blocky/mitten gripping scabbard"),
        "fingers_intersect_weapon": ("pass", "right hand wrapped below guard"),
        "scabbard_attachment": ("na", "held in hand"),
        "lighting_consistency": ("minor", "blue sword no cast light; secondary front light"),
        "edge_blending": ("minor", "dragon wing/smoke soft blend, AI artifact"),
        "halo_artifacts": ("pass", "fits aesthetic"),
        "metal_reflections": ("pass", "armor specular plausible"),
        "texture_discontinuities": ("minor", "left thigh armor smoother"),
    },
    # v1-012
    "v1-012": {
        "sword_guard_hand_alignment": ("pass", "crossguard above two-hand grip"),
        "blade_perspective": ("pass", "vertical, fantasy scale consistent"),
        "hand_grip_deformation": ("minor", "left gauntlet fingers fused/blocky"),
        "fingers_intersect_weapon": ("pass", "no clip"),
        "scabbard_attachment": ("na", "unsheathed"),
        "lighting_consistency": ("pass", "moon key light consistent"),
        "edge_blending": ("pass", "smooth integration"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "stylized specular plausible"),
        "texture_discontinuities": ("minor", "left knee guard smoother than right"),
    },
    # v1-013
    "v1-013": {
        "sword_guard_hand_alignment": ("pass", "crossguards correct vs hands"),
        "blade_perspective": ("pass", "blades logical; straight sword vertical ok"),
        "hand_grip_deformation": ("minor", "fingers clumped/fused; slightly elongated"),
        "fingers_intersect_weapon": ("pass", "no clip"),
        "scabbard_attachment": ("pass", "blue scabbard on left hip, plausible angle"),
        "lighting_consistency": ("pass", "blue scabbard in shadow justifies cool tone"),
        "edge_blending": ("pass", "smooth transition"),
        "halo_artifacts": ("pass", "backlight glow fits fire"),
        "metal_reflections": ("pass", "armor/sword reflect firelight"),
        "texture_discontinuities": ("minor", "left boot less defined than right"),
    },
    # v1-014
    "v1-014": {
        "sword_guard_hand_alignment": ("minor", "hand low/compressed against guard"),
        "blade_perspective": ("defect", "dark flat blue-grey strip glitch on blade"),
        "hand_grip_deformation": ("defect", "right hand mitten-mass merging hilt"),
        "fingers_intersect_weapon": ("defect", "fingers merge into gold hilt/guard"),
        "scabbard_attachment": ("pass", "saya on left hip via sash, plausible"),
        "lighting_consistency": ("defect", "flat dark blue strip unrelated to scene light"),
        "edge_blending": ("defect", "prominent straight blue seam across waist + blade"),
        "halo_artifacts": ("pass", "no halo"),
        "metal_reflections": ("minor", "silver blade flat, blue strip zero reflection"),
        "texture_discontinuities": ("defect", "blue waist line cuts robe/sash, no continuity"),
    },
    # v1-015
    "v1-015": {
        "sword_guard_hand_alignment": ("pass", "crossguard above grip, aligned"),
        "blade_perspective": ("pass", "angles down consistent with stance"),
        "hand_grip_deformation": ("minor", "fingers merged/indistinct on grip"),
        "fingers_intersect_weapon": ("pass", "no clip through blade"),
        "scabbard_attachment": ("pass", "sheath left hip, proper attach"),
        "lighting_consistency": ("pass", "backlit rim consistent"),
        "edge_blending": ("pass", "natural into haze"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "specular on blade/armor"),
        "texture_discontinuities": ("minor", "pillar grooves repetitive; fg debris repetitive"),
    },
    # v1-016 (staff/spear - non-sword)
    "v1-016": {
        "sword_guard_hand_alignment": ("na", "staffs/spears, no sword guard"),
        "blade_perspective": ("minor", "staff slightly flat, low convergence"),
        "hand_grip_deformation": ("minor", "left fingers elongated/fused, talon-like"),
        "fingers_intersect_weapon": ("pass", "wrap shaft, no clip"),
        "scabbard_attachment": ("na", "no scabbard"),
        "lighting_consistency": ("pass", "warm left light consistent"),
        "edge_blending": ("minor", "wing/sky boundary soft seam"),
        "halo_artifacts": ("minor", "head rim-light halo artifact"),
        "metal_reflections": ("minor", "armor highlights diffuse, plastic-like"),
        "texture_discontinuities": ("minor", "two wings differ in texture; chest dense vs skirt"),
    },
    # v1-017 (back view, scabbard)
    "v1-017": {
        "sword_guard_hand_alignment": ("pass", "hilt near hip, standard grip"),
        "blade_perspective": ("na", "sheathed, cannot judge"),
        "hand_grip_deformation": ("minor", "right hand blurry, fingers merged"),
        "fingers_intersect_weapon": ("pass", "no intersect"),
        "scabbard_attachment": ("pass", "scabbard on left hip, attached"),
        "lighting_consistency": ("pass", "rim/front shadow consistent"),
        "edge_blending": ("pass", "blends into debris"),
        "halo_artifacts": ("pass", "rim light natural"),
        "metal_reflections": ("pass", "bracers specular plausible"),
        "texture_discontinuities": ("minor", "right pillar smoother than left"),
    },
    # v1-018 (staff, back view)
    "v1-018": {
        "sword_guard_hand_alignment": ("pass", "grip plausible (staff)"),
        "blade_perspective": ("pass", "vertical shaft consistent"),
        "hand_grip_deformation": ("minor", "hand blocky, fused with sleeve"),
        "fingers_intersect_weapon": ("pass", "no clip"),
        "scabbard_attachment": ("na", "staff, no scabbard"),
        "lighting_consistency": ("pass", "consistent"),
        "edge_blending": ("minor", "feet/robe slightly soft vs steps"),
        "halo_artifacts": ("minor", "soft glow around hair/topknot"),
        "metal_reflections": ("na", "no metal visible"),
        "texture_discontinuities": ("minor", "robe plastic-smooth vs stone/moss"),
    },
    # v1-019
    "v1-019": {
        "sword_guard_hand_alignment": ("pass", "crossguard angled, low-guard plausible"),
        "blade_perspective": ("minor", "slightly flat, abrupt foreshorten at hilt"),
        "hand_grip_deformation": ("minor", "fingers thick/merged, thumb hidden"),
        "fingers_intersect_weapon": ("minor", "fingers blend into grip slightly"),
        "scabbard_attachment": ("na", "drawn"),
        "lighting_consistency": ("pass", "warm left key consistent"),
        "edge_blending": ("pass", "painterly smooth"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "gold/steel plausible"),
        "texture_discontinuities": ("minor", "fur uniform; chest gold dense in shadow"),
    },
    # v1-020
    "v1-020": {
        "sword_guard_hand_alignment": ("pass", "hand below crossguard, plausible"),
        "blade_perspective": ("minor", "blade angle slightly disconnected from arm"),
        "hand_grip_deformation": ("minor", "hand claw-mass, no knuckle detail"),
        "fingers_intersect_weapon": ("minor", "fingers merge with hilt"),
        "scabbard_attachment": ("na", "back hilt only, scabbard not clear"),
        "lighting_consistency": ("pass", "warm highlights vs cool shadow consistent"),
        "edge_blending": ("pass", "seamless into mist"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "specular consistent"),
        "texture_discontinuities": ("pass", "continuous textures"),
    },
    # v1-021
    "v1-021": {
        "sword_guard_hand_alignment": ("pass", "guard aligns with forearm"),
        "blade_perspective": ("pass", "blades converge downward logically"),
        "hand_grip_deformation": ("minor", "left fingers smoothed/fused"),
        "fingers_intersect_weapon": ("minor", "left index clips hilt/guard"),
        "scabbard_attachment": ("na", "drawn"),
        "lighting_consistency": ("pass", "front-left key consistent"),
        "edge_blending": ("minor", "hair/cloth jagged alpha edge vs white bg"),
        "halo_artifacts": ("defect", "dark halo around silhouette (white bg)"),
        "metal_reflections": ("pass", "polished steel specular"),
        "texture_discontinuities": ("minor", "arm tattoo flat; left thigh denim blurrier"),
    },
    # v1-022
    "v1-022": {
        "sword_guard_hand_alignment": ("pass", "both guards align with grips"),
        "blade_perspective": ("pass", "vertical consistent"),
        "hand_grip_deformation": ("defect", "left hand merged claw-mass, no finger def"),
        "fingers_intersect_weapon": ("pass", "right hand wraps hilt; left curled"),
        "scabbard_attachment": ("minor", "hip object floats, fabric-like not rigid"),
        "lighting_consistency": ("pass", "arch backlight consistent"),
        "edge_blending": ("pass", "smooth"),
        "halo_artifacts": ("minor", "overdone head/shoulder glow"),
        "metal_reflections": ("pass", "blade/armor plausible"),
        "texture_discontinuities": ("minor", "left pillar repetitive stone"),
    },
    # v1-023
    "v1-023": {
        "sword_guard_hand_alignment": ("minor", "grip low on hilt, sliding"),
        "blade_perspective": ("pass", "vertical greatsword, fantasy scale ok"),
        "hand_grip_deformation": ("defect", "right hand fused claw-mass, wrong anatomy"),
        "fingers_intersect_weapon": ("pass", "left hand wraps, no blade clip"),
        "scabbard_attachment": ("na", "both drawn"),
        "lighting_consistency": ("pass", "rim light matches pillars/sky"),
        "edge_blending": ("minor", "fg dark structure hard edge vs sharp legs"),
        "halo_artifacts": ("pass", "none"),
        "metal_reflections": ("pass", "specular consistent, diffuse style"),
        "texture_discontinuities": ("minor", "left column blurry top; cloak too smooth"),
    },
    # v1-024 (face closeup, no weapon)
    "v1-024": {
        "sword_guard_hand_alignment": ("na", "no sword in frame"),
        "blade_perspective": ("na", "no blade"),
        "hand_grip_deformation": ("na", "no hands visible"),
        "fingers_intersect_weapon": ("na", "no hands/weapon"),
        "scabbard_attachment": ("na", "no scabbard"),
        "lighting_consistency": ("pass", "key light consistent"),
        "edge_blending": ("pass", "blends into black bg"),
        "halo_artifacts": ("pass", "sharp rim, no halo"),
        "metal_reflections": ("pass", "chains specular plausible"),
        "texture_discontinuities": ("minor", "left chain blurrier; breastplate morph-like artifact"),
    },
}

ITEM_ORDER = [
    "sword_guard_hand_alignment", "blade_perspective", "hand_grip_deformation",
    "fingers_intersect_weapon", "scabbard_attachment", "lighting_consistency",
    "edge_blending", "halo_artifacts", "metal_reflections", "texture_discontinuities",
]
ITEM_LABEL = {
    "sword_guard_hand_alignment": "sword guard alignment",
    "blade_perspective": "blade perspective",
    "hand_grip_deformation": "hand grip deformation",
    "fingers_intersect_weapon": "fingers intersect weapon",
    "scabbard_attachment": "scabbard attachment",
    "lighting_consistency": "lighting consistency",
    "edge_blending": "edge blending/seam",
    "halo_artifacts": "halo artifacts",
    "metal_reflections": "metal reflections",
    "texture_discontinuities": "texture discontinuities",
}

written = 0
per_item = defaultdict(Counter)
per_case_grades = {}
for cid, items in G.items():
    path = OUT / f"{cid}.json"
    if not path.exists():
        continue
    rec = json.loads(path.read_text(encoding="utf-8"))
    new_items = []
    for it in ITEM_ORDER:
        grade, note = items[it]
        applicable = grade != "na"
        new_items.append({
            "item": it,
            "label": ITEM_LABEL[it],
            "applicable": applicable,
            "grade": grade,
            "note": note,
        })
        if applicable:
            per_item[it][grade] += 1
    rec["items"] = new_items
    rec["reviewed"] = True
    rec["review_method"] = "full-resolution vision pass (Hermes review-assist)"
    rec["reviewed_at"] = "2026-07-27"
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    per_case_grades[cid] = {it: items[it][0] for it in ITEM_ORDER}
    written += 1

# summary
summary = {
    "schema_version": 1,
    "suite": "stage2-v1-defect-review",
    "reviewed_at": "2026-07-27",
    "cases_reviewed": written,
    "method": "full-resolution vision pass of 24 candidates against 10-item subtle-defect checklist",
    "per_item_grade_counts": {it: dict(per_item[it]) for it in ITEM_ORDER},
    "note": ("Grades are review-assistant judgements from full-res inspection, not "
             "automated. 'defect' = clear subtle defect; 'minor' = small/disqualifying-"
             "only-in-context; 'na' = not applicable to object type. This does NOT "
             "change the V1 descriptive status: reliability was described on gross "
             "7-gate review; this re-review surfaces subtle-defect prevalence the "
             "thumbnail sheet hid."),
}
(OUT / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

# human-readable per-item table
lines = ["V1 subtle-defect re-review - per-item grade counts (applicable only):", ""]
header = f"{'item':<28}{'pass':>6}{'minor':>7}{'defect':>8}"
lines.append(header)
lines.append("-" * len(header))
for it in ITEM_ORDER:
    c = per_item[it]
    lines.append(f"{ITEM_LABEL[it]:<28}{c.get('pass',0):>6}{c.get('minor',0):>7}{c.get('defect',0):>8}")
lines.append("")
lines.append(f"Cases reviewed: {written}/24")
Path(OUT / "_per_item_table.txt").write_text("\n".join(lines), encoding="utf-8")

print("\n".join(lines))
print(f"\nWrote {written} defect_review.json + _summary.json + _per_item_table.txt")
