"""Apply graded verdicts to audit-review templates.

grades.json schema:
  {"v1-001": {"grades": {item: grade, ...}, "notes": {item: "note text", ...}},
   "v1-020": {"grades": {...}, "notes": {...}, "audit_notes": ["FIXTURE_METADATA_MISMATCH: ..."]}}

This is the ONLY place grades are written. It requires the crop path to already
exist (paired evidence). It persists:
  - per-item grade / note / evidence_ref
  - an item-level "correction" flag when the note contains CORRECTION/FIXTURE/RETRACT
  - a top-level "audit_notes" list (free-text audit flags, e.g. fixture mismatch)
Sets reviewed=True. Never overwrites identity_source / evidence / applicable_items
structure -- only fills grade fields.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORRECTION_MARKERS = ("CORRECTION", "FIXTURE", "RETRACT", "TARGET_ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("grades_json", type=Path)
    parser.add_argument("--out-dir", type=Path,
                        default=ROOT / ".hermes/evidence/stage2-v1-audit-reviews")
    args = parser.parse_args()
    data = json.loads(args.grades_json.read_text(encoding="utf-8"))
    out_dir = args.out_dir.resolve()
    written = 0
    for cid, block in data.items():
        tpl = out_dir / f"{cid}.json"
        if not tpl.exists():
            print(f"SKIP {cid}: template missing")
            continue
        rec = json.loads(tpl.read_text(encoding="utf-8"))
        notes = block.get("notes", {})
        grades = block.get("grades", {})
        cats = block.get("categories", {})      # item -> Measured|Observed|Inferred
        basis_map = block.get("basis", {})       # item -> [basis strings]
        crop = rec["evidence"].get("crop_path")
        for it in rec["applicable_items"]:
            item = it["item"]
            if item in grades:
                it["grade"] = grades[item]
                it["note"] = notes.get(item, "")
                it["evidence_ref"] = crop
                it["correction"] = any(m in it["note"].upper() for m in CORRECTION_MARKERS)
                # provenance-of-conclusion: default Observed unless the grade file
                # explicitly classifies it. Never infer category from the grade string.
                if item in cats:
                    it["finding_category"] = cats[item]
                if item in basis_map:
                    it["review_basis"] = basis_map[item]
        # top-level audit flags (e.g. fixture metadata mismatch) -- persisted verbatim
        audit_notes = block.get("audit_notes", [])
        if audit_notes:
            rec.setdefault("audit_notes", [])
            for an in audit_notes:
                if an not in rec["audit_notes"]:
                    rec["audit_notes"].append(an)
        rec["reviewed"] = True
        rec["reviewed_at"] = datetime.now(timezone.utc).astimezone().isoformat()
        rec["reviewer"] = "Hermes review-assist (vision on manifest-crop)"
        tpl.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        written += 1
    print(f"Applied grades to {written} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
