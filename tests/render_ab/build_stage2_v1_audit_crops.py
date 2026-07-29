"""Build a full-resolution crop of each case's target region for paired-evidence
review. Crop is derived from the mask bounding box (manifest-driven), saved next
to the case template. The vision pass references these crop files as evidence_ref.

Usage:
  PYTHONPATH= python tests/render_ab/build_stage2_v1_audit_crops.py \
      --manifest .hermes/evidence/stage2-validation-v1-manifest.json \
      --out-dir .hermes/evidence/stage2-v1-audit-reviews
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manparent = args.manifest.resolve().parent
    out_dir = args.out_dir.resolve()

    for c in manifest["cases"]:
        cid = c["case_id"]
        cand = ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png"
        mask = (manparent / c["mask_path"]).resolve() if c.get("mask_path") else None
        if not cand.exists() or mask is None or not mask.exists():
            print(f"{cid}: skip, candidate/mask missing")
            continue
        try:
            from PIL import Image
            import numpy as np
            m = np.asarray(Image.open(mask).convert("L"))
            ys, xs = np.where(m > 127)
            if len(xs) == 0:
                print(f"{cid}: empty mask, skip crop")
                continue
            # pad 12% and clamp
            h, w = m.shape
            x0, x1 = max(0, xs.min() - w // 12), min(w, xs.max() + w // 12)
            y0, y1 = max(0, ys.min() - h // 12), min(h, ys.max() + h // 12)
            img = Image.open(cand).convert("RGB")
            crop = img.crop((x0, y0, x1, y1))
            cdir = out_dir / cid
            cdir.mkdir(parents=True, exist_ok=True)
            crop_path = cdir / "target_crop.png"
            crop.save(crop_path)
            # update template evidence.crop_path
            tpl = out_dir / f"{cid}.json"
            rec = json.loads(tpl.read_text(encoding="utf-8"))
            rec["evidence"]["crop_path"] = \
                str(crop_path.relative_to(ROOT)).replace("\\", "/")
            tpl.write_text(json.dumps(rec, indent=2), encoding="utf-8")
            print(f"{cid}: crop {crop.size} -> {crop_path.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"{cid}: crop error {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
