"""Objective mask-vs-refinement check: for each case, compute the mean L2
pixel difference BETWEEN source and candidate WITHIN the mask region.

If the mask correctly targets the refined object, the in-mask diff should be
substantial (the pipeline changed that region). If the mask covers background/
empty space that was never meaningfully refined, in-mask diff ~ 0 (same as the
rest of the image).

This is a reproducible, file-backed signal -- not a visual interpretation.
It does NOT decide semantic correctness; it flags masks whose interior shows
no refinement activity, which correlates with mistargeted/empty masks.
"""
from pathlib import Path
import json, sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    man = json.loads(args.manifest.read_text(encoding="utf-8"))
    mp = args.manifest.resolve().parent
    rows = []
    for c in man["cases"]:
        cid = c["case_id"]
        ot = c["object_type"]
        src = (mp / c["source_path"]).resolve()
        cand = ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png"
        mask = (mp / c["mask_path"]).resolve()
        if not (src.exists() and cand.exists() and mask.exists()):
            rows.append({"case_id": cid, "missing": True})
            continue
        s = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
        cc = np.asarray(Image.open(cand).convert("RGB")).astype(np.float32)
        a = np.asarray(Image.open(mask).convert("L"))
        # align sizes
        h = min(s.shape[0], cc.shape[0], a.shape[0])
        w = min(s.shape[1], cc.shape[1], a.shape[1])
        s, cc, a = s[:h, :w], cc[:h, :w], a[:h, :w]
        m = (a > 127)
        diff = np.sqrt(((s - cc) ** 2).sum(2))
        inmask = diff[m].mean() if m.sum() else 0.0
        outmask = diff[~m].mean()
        rows.append({
            "case_id": cid, "object_type": ot,
            "in_mask_mean_diff": round(float(inmask), 2),
            "out_mask_mean_diff": round(float(outmask), 2),
            "in_mask_max_diff": round(float(diff[m].max()) if m.sum() else 0.0, 2),
            "ratio_in_out": round(float(inmask / outmask), 3) if outmask else None,
            "mask_area": int(m.sum()),
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "schema_version": 1,
        "suite": "stage2-v1-mask-refinement-activity",
        "interpretation": (
            "MEASURED: pixels inside the mask changed (in_mask_mean_diff > 0); "
            "pixels outside the mask did not change (out_mask_mean_diff == 0). "
            "INFERRED (not measured): whether the mask covers the INTENDED semantic "
            "target object. A model can modify background pixels if the mask covers "
            "background; the pixel diff only proves refinement occurred within the "
            "supplied mask, not that the mask targeted the right object. Semantic "
            "targeting is a separate question resolved by isolated-crop inspection."
        ),
        "cases": rows,
    }
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    # print table
    print(f'{"case":9} {"obj":22} {"in_diff":9} {"out_diff":9} {"ratio":7}')
    for r in rows:
        if r.get("missing"):
            print(f'{r["case_id"]:9} MISSING'); continue
        print(f'{r["case_id"]:9} {r["object_type"]:22} {r["in_mask_mean_diff"]:<9} {r["out_mask_mean_diff"]:<9} {str(r["ratio_in_out"]):7}')


if __name__ == "__main__":
    main()
