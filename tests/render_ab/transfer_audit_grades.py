"""Transfer existing grades from current v1-XXX.json into freshly rebuilt
templates, preserving grade/note/correction/audit_notes and setting
finding_category='Observed' + review_basis for every graded item (honest:
grades came from vision on isolated crop + mask overlay). The fixture-mismatch
AUDIT NOTE remains an Inferred conclusion recorded at top level.

Usage: after build_stage2_v1_audit_review.py regenerates templates, run this
to repopulate grades without re-running vision.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".hermes/evidence/stage2-v1-audit-reviews"


def main():
    # back up current graded records
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = SRC.parent / f"stage2-v1-audit-reviews.bak_{stamp}"
    shutil.copytree(SRC, bak)
    print("backed up to", bak)
    # rebuild templates (fresh) -- call builder via subprocess
    import subprocess, sys
    man = ROOT / ".hermes/evidence/stage2-validation-v1-manifest.json"
    subprocess.run([sys.executable, str(ROOT / "tests/render_ab/build_stage2_v1_audit_review.py"),
                    "--manifest", str(man), "--out-dir", str(SRC)], check=True)
    # crops already exist; ensure crop_path filled
    subprocess.run([sys.executable, str(ROOT / "tests/render_ab/build_stage2_v1_audit_crops.py"),
                    "--manifest", str(man), "--out-dir", str(SRC)], check=True)
    # transfer grades
    n = 0
    for f in sorted(SRC.glob("v1-*.json")):
        cid = f.stem
        old = json.loads(f.read_text(encoding="utf-8"))
        if not old.get("reviewed"):
            continue
        new = json.loads(f.read_text(encoding="utf-8"))  # re-read fresh template
        # fresh template overwrote file? No -- build writes fresh only if missing? check
        # build_stage2_v1_audit_review writes templates fresh each run, overwriting.
        # So we must read OLD from backup instead.
    # re-read from backup
    old_dir = bak
    for f in sorted(old_dir.glob("v1-*.json")):
        cid = f.stem
        old = json.load(open(f, encoding="utf-8"))
        if not old.get("reviewed"):
            continue
        tgt = SRC / f"{cid}.json"
        new = json.load(open(tgt, encoding="utf-8"))
        # map old grades -> new items by item name
        old_items = {it["item"]: it for it in old["applicable_items"]}
        for it in new["applicable_items"]:
            oi = old_items.get(it["item"])
            if oi and oi.get("grade") not in (None, "", "pending"):
                it["grade"] = oi["grade"]
                it["note"] = oi.get("note", "")
                it["evidence_ref"] = oi.get("evidence_ref") or new["evidence"].get("crop_path")
                it["correction"] = oi.get("correction", False)
                it["finding_category"] = "Observed"
                it["review_basis"] = ["isolated_crop", "mask_overlay"]
        new["reviewed"] = True
        new["reviewed_at"] = old.get("reviewed_at")
        new["reviewer"] = old.get("reviewer")
        new["audit_notes"] = old.get("audit_notes", [])
        # the fixture-mismatch audit note is an INFERRED conclusion; mark it
        tgt.write_text(json.dumps(new, indent=2), encoding="utf-8")
        n += 1
    print(f"transferred grades to {n} cases (finding_category=Observed)")


if __name__ == "__main__":
    main()
