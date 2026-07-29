"""Validate the audit-grade Stage 2 V1 re-review and emit/refuse the summary.

Enforces the audit gates. Exits non-zero and prints VALIDATION_FAIL on ANY:
- case count != 24
- allocation != 6/4/4/4/3/3
- an item graded on an inapplicable class (applicability from manifest object_type)
- a reviewed case missing required crop/evidence reference
- a face present despite the facial-cleanup exclusion contract
- any case not reviewed (reviewed != True) when emitting summary

If all gates pass, writes _summary.json with per-item and per-class grade
counts derived ONLY from manifest identity + recorded evidence refs.

Usage:
  PYTHONPATH= python tests/render_ab/validate_stage2_v1_audit_review.py \
      --manifest .hermes/evidence/stage2-validation-v1-manifest.json \
      --out-dir .hermes/evidence/stage2-v1-audit-reviews
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
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
RUBRIC = {
    "object_recognizable": "all", "placement_attachment_valid": "all",
    "no_duplicate_floating_substitution": "all", "identity_preserved": "all",
    "pose_preserved": "all", "anatomy_preserved": "all",
    "clothing_composition_preserved": "all",
    "sword_guard_hand_alignment": WEAPON_CLASSES,
    "blade_perspective": WEAPON_CLASSES,
    "hand_grip_deformation": WEAPON_CLASSES | {"hand_repair"},
    "fingers_intersect_weapon": WEAPON_CLASSES,
    "scabbard_attachment": {"sheathed_sword", "scabbard_weapon_repair"},
    "lighting_consistency": "all", "edge_blending": "all",
    "halo_artifacts": "all", "metal_reflections": WEAPON_CLASSES,
    "texture_discontinuities": "all",
    "prop_plausibility": {"non_weapon_prop"},
    "hand_anatomy_valid": {"hand_repair", "non_weapon_prop"},
    "garment_repair_coherent": {"clothing_defect"},
    "garment_texture_continuity": {"clothing_defect"},
    "requested_object_present": "all",
    "prompt_semantic_satisfaction": "all",
}

# Whole-image preservation gates that require full source/candidate/diff evidence,
# never a local crop alone.
WHOLE_IMAGE_GATES = {
    "identity_preserved", "pose_preserved", "clothing_composition_preserved",
    "anatomy_preserved",
}


def applicable(object_type: str) -> set:
    out = set()
    for item, classes in RUBRIC.items():
        if classes == "all" or object_type in classes:
            out.add(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    out_dir = args.out_dir.resolve()
    # resolved early so the per-case loop can stay read-only when a review exists
    indep_path = out_dir / "_independent_review.json"

    errors = []

    if len(cases) != 24:
        errors.append(f"case count {len(cases)} != 24")
    alloc = Counter(c.get("object_type") for c in cases)
    if dict(alloc) != EXPECTED_ALLOC:
        errors.append(f"allocation {dict(alloc)} != {EXPECTED_ALLOC}")

    per_item = defaultdict(Counter)
    per_class_item = defaultdict(lambda: defaultdict(Counter))
    per_item_category = defaultdict(Counter)
    per_item_freshness = defaultdict(Counter)
    inherited_non_excluded = 0
    inherited_items_by_gate = defaultdict(int)
    accept_map = defaultdict(list)
    reviewed_count = 0

    for c in cases:
        cid = c["case_id"]
        ot = c["object_type"]
        path = out_dir / f"{cid}.json"
        if not path.exists():
            errors.append(f"{cid}: template missing")
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        # identity must come from frozen manifest, never image-inferred
        if rec.get("identity_source") != "FROZEN_MANIFEST":
            errors.append(f"{cid}: identity_source not FROZEN_MANIFEST")
        if rec.get("object_type") != ot:
            errors.append(f"{cid}: object_type mismatch manifest vs template")
        allowed = applicable(ot)
        # face exclusion contract
        if "face" in (rec.get("target_region") or "") or ot in ("face_repair",):
            errors.append(f"{cid}: face present despite exclusion contract")
        if not rec.get("reviewed"):
            errors.append(f"{cid}: not reviewed")
            continue
        reviewed_count += 1
        if not rec.get("evaluation_excluded"):
            # whole-image gates must use full evidence, never crop-only
            for it in rec["applicable_items"]:
                if it["item"] in WHOLE_IMAGE_GATES:
                    basis = set(it.get("review_basis", []))
                    needed = {"full_source", "full_candidate", "full_diff", "mask_overlay"}
                    if not needed.issubset(basis):
                        errors.append(
                            f"{cid}: whole-image gate '{it['item']}' review_basis "
                            f"{sorted(basis)} missing required full-image evidence {sorted(needed - basis)}")
            # mandatory prompt-contract gates must be graded
            for mand in ("requested_object_present", "prompt_semantic_satisfaction"):
                if mand not in {it["item"] for it in rec["applicable_items"]}:
                    errors.append(f"{cid}: missing mandatory gate '{mand}'")
        # derive case-level overall acceptance from mandatory gates
        grades_by_item = {it["item"]: it["grade"] for it in rec["applicable_items"]}
        mandatory = ["object_recognizable", "placement_attachment_valid",
                     "no_duplicate_floating_substitution", "requested_object_present",
                     "prompt_semantic_satisfaction"]
        if rec.get("evaluation_excluded"):
            overall = "excluded_fixture_defect"
        elif rec.get("confirmation_status") == "pending":
            # hand-repair / clothing-defect cases outside the semantic spot-check
            # scope: not yet certified by independent review -> unresolved, not pass
            overall = "unresolved"
        else:
            mand_grades = [grades_by_item.get(m) for m in mandatory]
            if any(g in (None, "pending", "") for g in mand_grades):
                errors.append(f"{cid}: mandatory gate ungraded -> cannot derive acceptance")
                overall = "indeterminate"
            elif any(g == "defect" for g in mand_grades):
                overall = "fail"
            elif any(g == "minor" for g in mand_grades):
                overall = "pass_with_minor"
            else:
                overall = "pass"
        rec["overall_accept"] = overall
        accept_map[overall].append(cid)
        # validate per-item loop below
        for it in rec["applicable_items"]:
            item = it["item"]
            grade = it["grade"]
            if item not in allowed:
                errors.append(f"{cid}: item '{item}' graded on inapplicable class {ot}")
                continue
            if grade in ("pending", "", None):
                errors.append(f"{cid}: item '{item}' not graded")
                continue
            if grade not in ("pass", "minor", "defect", "na"):
                errors.append(f"{cid}: item '{item}' invalid grade '{grade}'")
            if not it.get("evidence_ref"):
                errors.append(f"{cid}: item '{item}' grade '{grade}' missing evidence_ref")
            cat = it.get("finding_category")
            if cat not in ("Measured", "Observed", "Inferred"):
                errors.append(f"{cid}: item '{item}' missing/invalid finding_category '{cat}'")
            fr = it.get("review_freshness")
            if fr not in ("fresh", "inherited", "excluded", None):
                errors.append(f"{cid}: item '{item}' missing/invalid review_freshness '{fr}'")
            # count inherited, non-excluded graded items (block baseline eligibility)
            if fr == "inherited" and not rec.get("evaluation_excluded"):
                inherited_non_excluded += 1
                inherited_items_by_gate.setdefault(item, 0)
                inherited_items_by_gate[item] += 1
            per_item[item][grade] += 1
            per_class_item[ot][item][grade] += 1
            per_item_category[item][cat] += 1
            per_item_freshness[item][fr or "unspecified"] += 1
        # persist per-case acceptance into the template -- SKIP when an
        # independent-review artifact exists, so the records stay byte-identical
        # and the review_records_sha256 the reviewer bound to remains valid.
        if not indep_path.exists():
            rec_path = out_dir / f"{cid}.json"
            json.dump(rec, open(rec_path, "w"), indent=2)
        else:
            rec_path = out_dir / f"{cid}.json"

    if reviewed_count != 24:
        errors.append(f"reviewed count {reviewed_count} != 24")

    # hand-repair denominator excludes v1-020 (fixture defect)
    hand_cases = [c["case_id"] for c in cases if c["object_type"] == "hand_repair"]
    hand_valid = [h for h in hand_cases if not json.load(open(out_dir / f"{h}.json")).get("evaluation_excluded")]
    alloc_note = dict(EXPECTED_ALLOC)
    # Independent-review gate: eligibility requires a SEPARATE reviewer artifact
    # that is cryptographically bound to the exact records it approves.
    # The grading pipeline must NEVER write this file. The validator REJECTS
    # approval unless every binding condition holds (see _check_indep_review).
    # snapshot the summary hash BEFORE any write, so the binding check uses the
    # bytes the reviewer actually saw (the validator must not rewrite them).
    summary_sha_before = _sha256_file(out_dir / "_summary.json")
    indep = json.load(open(indep_path)) if indep_path.exists() else {}
    indep_passed, indep_reject = _check_indep_review(
        indep, out_dir, args.manifest, cases, inherited_non_excluded,
        summary_sha_before)

    if errors:
        print("VALIDATION_FAIL")
        for e in errors:
            print("  -", e)
        return 2

    summary = {
        "schema_version": 1,
        "suite": "stage2-v1-audit-review",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "cases": 24,
        "allocation": EXPECTED_ALLOC,
        "hand_repair_denominator_note": f"3 allocated; v1-020 excluded as fixture defect -> {len(hand_valid)} valid for hand-repair quality",
        "identity_source": "FROZEN_MANIFEST",
        "per_item_grade_counts": {it: dict(per_item[it]) for it in sorted(per_item)},
        "per_class_item_grade_counts": {cls: {it: dict(cnt) for it, cnt in per_class_item[cls].items()}
                                         for cls in sorted(per_class_item)},
        "overall_accept_cases": {
            "pass": sorted(accept_map.get("pass", [])),
            "pass_with_minor": sorted(accept_map.get("pass_with_minor", [])),
            "fail": sorted(accept_map.get("fail", [])),
            "unresolved": sorted(accept_map.get("unresolved", [])),
            "excluded_fixture_defect": sorted(accept_map.get("excluded_fixture_defect", [])),
            "indeterminate": sorted(accept_map.get("indeterminate", [])),
        },
        "per_item_category_counts": {it: dict(per_item_category[it]) for it in sorted(per_item_category)},
        "per_item_freshness_counts": {it: dict(per_item_freshness[it]) for it in sorted(per_item_freshness)},
        "acceptance_inputs_freshness": {
            "mandatory_gates": [
                "object_recognizable", "placement_attachment_valid",
                "no_duplicate_floating_substitution",
                "requested_object_present", "prompt_semantic_satisfaction",
            ],
            "fresh": ["requested_object_present", "prompt_semantic_satisfaction"],
            "inherited": [
                "object_recognizable", "placement_attachment_valid",
                "no_duplicate_floating_substitution",
            ],
            "note": "Case-level overall_accept is a FRESH derivation from the current recorded grades, but 3 of its 5 mandatory inputs were INHERITED from the prior visual pass. The 17/6/1 result is therefore a valid derivation, not a fully fresh visual evaluation.",
        },
        "baseline_eligibility": {
            "eligible": indep_passed,
            "blocking_reasons": (
                [] if indep_passed else [
                    "Fresh visual grades failed independent evidence spot-check",
                    "Sheathed-sword attachment judgments require correction",
                    "Drawn-sword duplicate judgments require correction",
                    "Non-weapon prop stratum requires re-scoring",
                ]
            ),
            "independent_review_passed": indep_passed,
            "independent_review_reject_reason": indep_reject,
            "independent_review_artifact": "_independent_review.json (must be authored by a SEPARATE reviewer; the grading pipeline cannot satisfy the approval schema by itself, and reviewer independence must also be established procedurally)",
            "note": ("status: VALIDATED means the summary is internally consistent and the corrected "
                     "rubric is enforced. It does NOT mean the visual baseline is correct or frozen. "
                     "baseline_eligibility requires an explicit independent-review artifact that "
                     "confirms the fresh grades match the images. 'No inherited tags remain' is a "
                     "NECESSARY but NOT SUFFICIENT condition -- fresh tags can still be wrong, as the "
                     "spot-check showed. eligibility stays false until _independent_review.json sets "
                     "independent_review_passed=true."),
        },
        "review_freshness_legend": {
            "fresh": "re-judged this turn under the corrected prompt-contract rubric",
            "inherited": "carried from the prior weaker-rubric vision pass; NOT regenerated this turn",
            "excluded": "fixture-defect case, not part of the quality denominator",
        },
        "status": "VALIDATED",
    }
    if indep_path.exists():
        # Non-mutating mode: do NOT rewrite the evidence bundle (_summary.json,
        # per-case records). Write the eligibility verdict to a SEPARATE result
        # file so the certified artifacts stay byte-identical. This keeps the
        # reviewer's hash-binding valid on re-runs.
        result = {
            "schema_version": 1,
            "validated_at": summary["validated_at"],
            "baseline_eligible": indep_passed,
            "independent_review_passed": indep_passed,
            "independent_review_reject_reason": indep_reject if not indep_passed else "",
            "summary_sha256_before_approval": summary_sha_before,
            "review_records_sha256": _records_sha256(out_dir),
            "manifest_sha256": _sha256_file(args.manifest),
            "note": "Read-only verdict. The review artifacts were NOT modified. "
                    "baseline_eligibility is authoritative from this result file.",
        }
        (out_dir / "_validator_result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        print("VALIDATION_OK (read-only; wrote _validator_result.json)")
    else:
        (out_dir / "_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        print("VALIDATION_OK")
    print(json.dumps(summary, indent=2))
    return 0


def _sha256_file(path: Path) -> str:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Explicit, stable 27-file set that defines the review-records digest.
# MUST exclude the independent-review artifact, the validator result, backups,
# and any temp files -- otherwise the approval becomes part of the directory it
# hashes (self-referential, unstable digest).
RECORDS_DIGEST_FILES = [
    *[f"v1-{i:03d}.json" for i in range(1, 25)],   # 24 per-case records
    "_summary.json",
    "_meta.json",
    "_evidence_panels.json",
]


def _records_sha256(out_dir: Path) -> str:
    """Hash exactly the frozen 27-file review-records set, deterministically.
    Excludes _independent_review.json, _validator_result.json, backups, temps."""
    d = Path(out_dir)
    h = hashlib.sha256()
    for name in RECORDS_DIGEST_FILES:
        f = d / name
        if not f.is_file():
            continue
        h.update(name.encode()); h.update(b"\x00")
        h.update(f.read_bytes()); h.update(b"\x00")
    return h.hexdigest()


def _check_indep_review(indep: dict, out_dir: Path, manifest_path: Path,
                         cases: list, inherited_non_excluded: int,
                         summary_sha_before: str):
    """Return (passed, reject_reason). The grading pipeline cannot satisfy the
    approval schema by itself -- it only sets grades, never the binding artifact.
    Reviewer independence must also be established procedurally; this function
    enforces that a separate, hash-bound artifact exists and is complete, but it
    cannot prove the reviewer's organizational independence from JSON fields alone.
    Approval is rejected unless every condition holds."""
    if not indep:
        return False, "no independent-review artifact present"
    if not indep.get("independent_review_passed"):
        return False, "independent_review_passed is not true"
    if inherited_non_excluded != 0:
        return False, f"{inherited_non_excluded} inherited grades remain"
    # reviewer identity required
    if not indep.get("reviewer") or indep.get("reviewer_role") != "independent_visual_auditor":
        return False, "reviewer identity / role missing or not independent_visual_auditor"
    # all 23 valid case IDs must be reviewed. evaluation_excluded lives on the
    # per-case review record, NOT the manifest case object, so resolve it there
    # (consistent with the hand_repair denominator at line 201).
    valid_ids = [
        c["case_id"] for c in cases
        if not json.load(open(out_dir / f"{c['case_id']}.json")).get("evaluation_excluded")
    ]
    reviewed = set(indep.get("reviewed_case_ids", []))
    missing = [c for c in valid_ids if c not in reviewed]
    if missing:
        return False, f"not all valid cases reviewed; missing {missing}"
    # no unresolved/pending cases may remain
    if indep.get("exceptions") or indep.get("unresolved_cases"):
        return False, "artifact declares unresolved/pending cases"
    # hash bindings
    man_sha = _sha256_file(manifest_path)
    summary_sha = summary_sha_before
    records_sha = _records_sha256(out_dir)
    if indep.get("manifest_sha256") != man_sha:
        return False, "manifest_sha256 mismatch"
    if indep.get("summary_sha256_before_approval") != summary_sha:
        return False, "summary_sha256_before_approval mismatch (stale approval)"
    if indep.get("review_records_sha256") != records_sha:
        return False, "review_records_sha256 mismatch"
    # timestamp must be newer than the records it approves
    try:
        rec_mtime = max((Path(out_dir) / f).stat().st_mtime
                        for f in sorted(Path(out_dir).glob("v1-*.json")))
        rev = datetime.fromisoformat(indep["reviewed_at"]) if isinstance(indep.get("reviewed_at"), str) else None
        if rev is None or rev.timestamp() < rec_mtime:
            return False, "review artifact predates the records it approves"
    except Exception:
        return False, "reviewed_at missing or unparseable"
    if indep.get("decision") != "pass":
        return False, "decision is not pass"
    return True, ""


if __name__ == "__main__":
    raise SystemExit(main())
