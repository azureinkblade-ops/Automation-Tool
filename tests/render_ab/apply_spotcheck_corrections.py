"""Apply the independent spot-check corrections from the human review of the
contact sheets / evidence panels (2026-07-27). These OVERRIDE the fresh automated
grades where the spot-check found them wrong. Each override is tagged
independent_spotcheck_correction=True so it is distinguishable from the automated
fresh pass.

Scope (per spot-check):
- sheathed_sword v1-001..v1-006: attachment/semantic defective (sword-like object
  present but not convincingly worn; freestanding/oversized/vertical).
- drawn_sword v1-007..v1-010: multiple parallel blades -> duplicate/floating defect.
- scabbard_weapon_repair v1-011..v1-014: attachment/substitution defective.
- non_weapon_prop v1-015..v1-018: cyan marker, not a jade lantern -> all 4 defect.
Hand-repair and clothing-defect cases are LEFT AS-IS (pending separate confirmation).
v1-020 remains excluded.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".hermes/evidence/stage2-v1-audit-reviews"

# case -> {gate: grade}
CORR = {}
def setg(cid, **kw):
    CORR.setdefault(cid, {}).update(kw)

# --- sheathed sword: all six ---
for cid in ["v1-001", "v1-002", "v1-003", "v1-004", "v1-005", "v1-006"]:
    setg(cid,
         requested_object_present="minor",       # sword-like object exists, not an attached sheathed jian
         placement_attachment_valid="defect",
         no_duplicate_floating_substitution="pass",  # single object; only attachment broken
         prompt_semantic_satisfaction="defect",
         scabbard_attachment="defect")
# v1-001 extra (explicitly called out)
setg("v1-001", edge_blending="defect", texture_discontinuities="defect")

# --- drawn sword: multiple parallel blades ---
for cid in ["v1-007", "v1-008", "v1-009", "v1-010"]:
    setg(cid,
         no_duplicate_floating_substitution="defect",
         prompt_semantic_satisfaction="defect")

# --- scabbard / weapon repair (v1-011..014) ---
for cid in ["v1-011", "v1-012", "v1-013", "v1-014"]:
    setg(cid,
         placement_attachment_valid="defect",
         no_duplicate_floating_substitution="defect",
         prompt_semantic_satisfaction="defect")
setg("v1-011", requested_object_present="minor")
setg("v1-012", requested_object_present="minor")
setg("v1-013", requested_object_present="minor")
setg("v1-014", requested_object_present="minor")

# --- non-weapon prop: cyan marker, not a lantern (all four) ---
for cid in ["v1-015", "v1-016", "v1-017", "v1-018"]:
    setg(cid,
         requested_object_present="defect",
         prop_plausibility="defect",
         placement_attachment_valid="defect",
         prompt_semantic_satisfaction="defect")

TAG = "independent_spotcheck_correction"
NOTE = "Corrected by independent spot-check of sheets/evidence panels: automated fresh grade contradicted by displayed evidence."

for f in sorted(OUT.glob("v1-*.json")):
    cid = f.stem
    d = json.load(open(f, encoding="utf-8"))
    if d.get("evaluation_excluded"):
        continue
    if cid not in CORR:
        continue
    for it in d["applicable_items"]:
        if it["item"] in CORR[cid]:
            it["grade"] = CORR[cid][it["item"]]
            it["independent_spotcheck_correction"] = True
            existing = (it.get("note") or "").replace(" [FRESH-REJUDGED on evidence panel]", "")
            it["note"] = (existing + " " + NOTE).strip()
            # keep review_freshness as fresh (the override IS the corrected fresh call)
    # recompute overall_accept so the summary reflects corrected grades
    json.dump(d, open(f, "w"), indent=2)
    print(f"{cid}: applied spot-check corrections -> {CORR[cid]}")
print("spot-check corrections applied")
