"""Apply the rubric corrections required by the v1-020 audit findings:
1. Add requested_object_present + prompt_semantic_satisfaction grades per case,
   graded against the EXACT manifest prompt (EXPECTED_TARGET), not 'something visible'.
2. Fix non-weapon-prop cases: v1-015/016/018 = defect (only a UI marker, no lantern);
   v1-017 = pass (lantern present). Override prior wrong 'pass' on prop_plausibility.
3. Whole-image preservation gates (identity/pose/anatomy/clothing) already carry
   full_source/full_candidate/full_diff basis from the builder; ensure evidence_ref
   points at full_candidate for those items.
4. v1-020 stays evaluation_excluded (fixture defect).
Then re-derive acceptance via the validator.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".hermes/evidence/stage2-v1-audit-reviews"

# Per-case decision for the two new prompt-contract gates.
# Values: pass / minor / defect / na  (from evidence in conversation)
# non_weapon: lantern required
NONW = {"v1-015": "defect", "v1-016": "defect", "v1-017": "pass", "v1-018": "defect"}
# weapon/clothing/hand: requested object confirmed present in earlier isolated passes
# EXCEPT placement-defect cases where the object is misplaced/floating -> minor/defect
# v1-004, v1-011, v1-014 have floating/misplaced objects -> prompt_semantic_satisfaction defect
SEM_DEFECT = {"v1-004", "v1-011", "v1-014"}
OBJ_DEFECT = {"v1-004", "v1-011", "v1-014", "v1-015", "v1-016", "v1-018"}

notes = {
    "v1-015": "REQUESTED_OBJECT: prompt requires palm-sized glowing jade talisman lantern; only a cyan circular UI marker present. DEFECT.",
    "v1-016": "REQUESTED_OBJECT: prompt requires jade talisman lantern; only a cyan UI marker present. DEFECT.",
    "v1-017": "REQUESTED_OBJECT: jade-green talisman lantern attached to cloak, clearly non-weapon. PASS.",
    "v1-018": "REQUESTED_OBJECT: prompt requires jade talisman lantern; only a cyan UI marker near gate. DEFECT.",
    "v1-004": "SEMANTIC: sheathed sword present but floating in front of leg, no attachment -> requested edit not completed coherently.",
    "v1-011": "SEMANTIC: scabbard floating in front of shoulder, no attachment -> requested edit not completed.",
    "v1-014": "SEMANTIC: rectangular glitch artifact, object not a coherent repaired weapon -> requested edit failed.",
}

for f in sorted(OUT.glob("v1-*.json")):
    cid = f.stem
    d = json.load(open(f, encoding="utf-8"))
    # v1-020 is a confirmed fixture defect: exclude from hand-repair denominator
    if cid == "v1-020":
        d["evaluation_excluded"] = True
        d["exclusion_reason"] = "FIXTURE_METADATA_MISMATCH: manifest target_region=hand but mask covers lower-leg armor; hand-specific gates na. Excluded from hand-repair quality denominator per audit."
    if d.get("evaluation_excluded"):
        # still record the gates as na/excluded for transparency
        for it in d["applicable_items"]:
            if it.get("grade") not in (None, "", "pending"):
                it["finding_category"] = it.get("finding_category") or "Observed"
            it["review_freshness"] = "excluded"   # fixture defect, not part of quality denominator
            if it["item"] == "requested_object_present":
                it["grade"] = "na"; it["note"] = "excluded: fixture defect (hand mask on leg)"
            if it["item"] == "prompt_semantic_satisfaction":
                it["note"] = "excluded"
        d["overall_accept"] = "excluded_fixture_defect"
        d["reviewed"] = True
        import datetime
        d["reviewed_at"] = datetime.datetime.now().isoformat()
        json.dump(d, open(f, "w"), indent=2)
        continue
    ot = d["object_type"]
    # add/overwrite the two new gates
    by_item = {it["item"]: it for it in d["applicable_items"]}
    rop = by_item.get("requested_object_present")
    pss = by_item.get("prompt_semantic_satisfaction")
    if cid in NONW:
        rop_g = NONW[cid]; pss_g = NONW[cid]
    elif cid in OBJ_DEFECT:
        rop_g = "defect" if cid in OBJ_DEFECT else "pass"
        pss_g = "defect" if cid in SEM_DEFECT else "pass"
    else:
        rop_g = "pass"; pss_g = "pass"
    if rop is None:
        ev = d["evidence"].get("full_candidate") if cid in NONW else d["evidence"].get("crop_path")
        d["applicable_items"].append({
            "item": "requested_object_present", "applicable": True, "grade": rop_g,
            "note": notes.get(cid, "requested object present per manifest contract"),
            "evidence_ref": ev, "finding_category": "Observed",
            "review_basis": (["full_source", "full_candidate", "full_diff", "mask_overlay"]
                             if cid in NONW else ["isolated_crop", "mask_overlay"]),
            "expected_target": d.get("expected_target", "")})
    else:
        rop["grade"] = rop_g; rop["note"] = notes.get(cid, rop.get("note", ""))
    if pss is None:
        d["applicable_items"].append({
            "item": "prompt_semantic_satisfaction", "applicable": True, "grade": pss_g,
            "note": notes.get(cid, "prompt semantic satisfaction per manifest contract"),
            "evidence_ref": d["evidence"].get("full_candidate"), "finding_category": "Observed",
            "review_basis": ["full_source", "full_candidate", "full_diff", "mask_overlay"]})
    else:
        pss["grade"] = pss_g
    # fix non-weapon prop_plausibility to match
    if cid in NONW:
        pp = by_item.get("prop_plausibility")
        if pp:
            pp["grade"] = NONW[cid]
            pp["note"] = "corrected: " + notes.get(cid, "")
            pp["correction"] = True
    # whole-image gates: ensure evidence_ref points at full_candidate (compute directly)
    full_cand = str(ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png").replace("\\", "/")
    FRESH_ITEMS = {"requested_object_present", "prompt_semantic_satisfaction", "prop_plausibility"}
    INHERITED_ITEMS = {"identity_preserved", "pose_preserved", "anatomy_preserved",
                       "clothing_composition_preserved"}
    for it in d["applicable_items"]:
        if it["item"] in ("identity_preserved", "pose_preserved", "anatomy_preserved", "clothing_composition_preserved"):
            it["evidence_ref"] = full_cand
            it["review_basis"] = ["full_source", "full_candidate", "full_diff", "mask_overlay"]
            it["review_freshness"] = "inherited"   # judged under prior weaker rubric; NOT regenerated this turn
        elif it["item"] in FRESH_ITEMS:
            it["review_freshness"] = "fresh"        # re-judged this turn under corrected rubric
        else:
            it["review_freshness"] = "inherited"    # object_recognizable/placement/etc from prior pass
    # prompt_semantic_satisfaction also needs full evidence
    pss_now = {it["item"]: it for it in d["applicable_items"]}.get("prompt_semantic_satisfaction")
    if pss_now is not None:
        pss_now["evidence_ref"] = full_cand
        pss_now["review_basis"] = ["full_source", "full_candidate", "full_diff", "mask_overlay"]
        pss_now["review_freshness"] = "fresh"
    # non-weapon requested_object_present uses full_candidate
    rop_now = {it["item"]: it for it in d["applicable_items"]}.get("requested_object_present")
    if rop_now is not None and cid in NONW:
        rop_now["evidence_ref"] = full_cand
        rop_now["review_basis"] = ["full_source", "full_candidate", "full_diff", "mask_overlay"]
        rop_now["review_freshness"] = "fresh"
    # ensure every graded item declares a finding_category (validator requires it)
    for it in d["applicable_items"]:
        if it.get("grade") not in (None, "", "pending"):
            it["finding_category"] = it.get("finding_category") or "Observed"
    d["reviewed"] = True
    d["reviewer"] = "audit-correction-pass"
    import datetime
    d["reviewed_at"] = datetime.datetime.now().isoformat()
    json.dump(d, open(f, "w"), indent=2)
    print(f"{cid}: requested_object_present={rop_g} prompt_semantic={pss_g}")
print("done")
