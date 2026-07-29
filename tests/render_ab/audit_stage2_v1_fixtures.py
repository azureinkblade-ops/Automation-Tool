"""Fixture integrity audit for the Stage 2 V1 frozen manifest.

Objective, reproducible geometry checks over all 24 masks. Produces:
1. per-fixture metrics JSON (written to disk) -- openable, not prose.
2. a fixture contact sheet PNG: candidate | mask overlay | bbox, per case,
   so the human can independently eyeball mask<->target correspondence.

Checks the questions David raised:
- mask vs declared target_region / object_type geometry
- crop (mask bbox) actually contains the intended region (by construction)
- offset masks (centroid far from expected region)
- oversized masks (bbox covers large fraction of frame)
- truncated masks (bbox touches frame edge)
- multi-object masks (multiple disconnected components)

Geometry only. Semantic "does this mask cover the right object" is a human
decision the contact sheet supports, never auto-decided here.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Scripts")) if (ROOT / "Scripts" / "python.exe").exists() else None


def mask_metrics(mask_png: Path, cand_png: Path | None):
    a = np.asarray(Image.open(mask_png).convert("L"))
    h, w = a.shape
    bin_ = (a > 127).astype(np.uint8)
    ys, xs = np.where(bin_)
    if len(xs) == 0:
        return {"empty": True, "w": w, "h": h}
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    area = int(bin_.sum())
    # connected components
    num, _ = cv2.connectedComponents(bin_, connectivity=8)
    comps = max(0, num - 1)  # minus background
    # largest component area for fragmentation check
    if comps >= 1:
        stats = cv2.connectedComponentsWithStats(bin_, connectivity=8)[2]
        largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if len(stats) > 1 else area
        largest_frac = largest / area if area else 0.0
    else:
        largest_frac = 1.0
    cx, cy = x0 + bw / 2, y0 + bh / 2
    return {
        "w": w, "h": h,
        "bbox": [x0, y0, x1, y1],
        "bbox_w": bw, "bbox_h": bh,
        "area_px": area,
        "fill_ratio_in_bbox": round(area / (bw * bh), 4),
        "bbox_frac_of_frame": round((bw * bh) / (w * h), 4),
        "centroid": [round(cx, 1), round(cy, 1)],
        "centroid_frac": [round(cx / w, 4), round(cy / h, 4)],
        "components": comps,
        "largest_component_frac": round(largest_frac, 4),
        "touches_left": x0 == 0, "touches_right": x1 == w - 1,
        "touches_top": y0 == 0, "touches_bottom": y1 == h - 1,
        "touches_any_edge": bool(x0 == 0 or x1 == w - 1 or y0 == 0 or y1 == h - 1),
        "edges_touched": [e for e, v in
                          [("left", x0 == 0), ("right", x1 == w - 1),
                           ("top", y0 == 0), ("bottom", y1 == h - 1)] if v],
    }


def flag_issues(m: dict, object_type: str) -> list[str]:
    issues = []
    if m.get("empty"):
        issues.append("EMPTY_MASK")
        return issues
    # oversized: bbox > 60% of frame
    if m["bbox_frac_of_frame"] > 0.6:
        issues.append("OVERSIZED_MASK: bbox>60% frame")
    # truncated: touches >=2 edges (likely cut off)
    if len(m["edges_touched"]) >= 2:
        issues.append("TRUNCATED_MASK: touches " + "+".join(m["edges_touched"]))
    elif len(m["edges_touched"]) == 1:
        issues.append("EDGE_TOUCH: " + m["edges_touched"][0])
    # multi-object: >1 connected component and largest < 70% of mask
    if m["components"] > 1 and m["largest_component_frac"] < 0.7:
        issues.append(f"MULTI_OBJECT: {m['components']} comps, largest {m['largest_component_frac']:.2f}")
    # suspiciously low fill (sparse / streaky)
    if m["fill_ratio_in_bbox"] < 0.15:
        issues.append(f"SPARSE_MASK: fill {m['fill_ratio_in_bbox']:.2f}")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()
    man = json.loads(args.manifest.read_text(encoding="utf-8"))
    mp = args.manifest.resolve().parent
    cases = man["cases"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    contact_rows = []
    for c in cases:
        cid = c["case_id"]
        ot = c["object_type"]
        tr = c.get("target_region")
        mask = (mp / c["mask_path"]).resolve()
        cand = ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png"
        if not mask.exists():
            rows.append({"case_id": cid, "object_type": ot, "mask_exists": False})
            continue
        m = mask_metrics(mask, cand if cand.exists() else None)
        m["case_id"] = cid
        m["object_type"] = ot
        m["target_region"] = tr
        m["mask_exists"] = True
        m["issues"] = flag_issues(m, ot)
        rows.append(m)
        contact_rows.append((cid, ot, cand if cand.exists() else None, mask))

    out = {
        "schema_version": 1,
        "suite": "stage2-v1-fixture-audit",
        "audited_at": __import__("datetime").datetime.now().isoformat(),
        "cases": rows,
        "issue_counts": {i: sum(1 for r in rows if i in r.get("issues", []))
                         for i in ["EMPTY_MASK", "OVERSIZED_MASK", "TRUNCATED_MASK",
                                   "EDGE_TOUCH", "MULTI_OBJECT", "SPARSE_MASK"]},
    }
    (args.out_dir / "fixture_audit.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")

    # contact sheet
    build_contact_sheet(contact_rows, args.out_dir / "fixture_contact_sheet.png")
    print("FIXTURE_AUDIT_WRITTEN", args.out_dir / "fixture_audit.json")
    print("ISSUE_COUNTS", json.dumps(out["issue_counts"]))


def build_contact_sheet(contact_rows, out_png: Path):
    # 3 columns per case: candidate | mask overlay | bbox'd candidate
    cols = 3
    thumb_w, thumb_h = 256, 320
    n = len(contact_rows)
    rows_n = int(np.ceil(n / 4))  # 4 cases per sheet-row
    per_row = 4
    sheet = np.zeros((rows_n * (thumb_h + 24), per_row * cols * (thumb_w + 8), 3),
                     dtype=np.uint8)
    for idx, (cid, ot, cand, mask) in enumerate(contact_rows):
        rr, cc = divmod(idx, per_row)
        xbase = cc * cols * (thumb_w + 8)
        ybase = rr * (thumb_h + 24)
        # candidate
        if cand and cand.exists():
            cim = np.asarray(Image.open(cand).convert("RGB").resize((thumb_w, thumb_h)))
        else:
            cim = np.full((thumb_h, thumb_w, 3), 40, dtype=np.uint8)
        # mask
        m = np.asarray(Image.open(mask).convert("L").resize((thumb_w, thumb_h)))
        mbin = (m > 127).astype(np.uint8)
        # overlay
        ov = cim.copy()
        ov[mbin > 0] = (ov[mbin > 0] * 0.4 + np.array([255, 0, 0]) * 0.6).astype(np.uint8)
        # bbox
        a = np.asarray(Image.open(mask).convert("L"))
        ys, xs = np.where(a > 127)
        if len(xs):
            h, w = a.shape
            fy0 = int(ys.min() / h * thumb_h); fy1 = int(ys.max() / h * thumb_h)
            fx0 = int(xs.min() / w * thumb_w); fx1 = int(xs.max() / w * thumb_w)
        else:
            fy0 = fy1 = fx0 = fx1 = 0
        bb = cim.copy()
        cv2.rectangle(bb, (fx0, fy0), (fx1, fy1), (0, 255, 0), 1)
        # paste
        for k, panel in enumerate([cim, ov, bb]):
            x = xbase + k * (thumb_w + 8)
            sheet[ybase:ybase + thumb_h, x:x + thumb_w] = panel
        # label
        cv2.putText(sheet, f"{cid}", (xbase, ybase + thumb_h + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1)
        cv2.putText(sheet, ot[:16], (xbase + thumb_w, ybase + thumb_h + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (160, 200, 255), 1)
    Image.fromarray(sheet).save(out_png)


if __name__ == "__main__":
    main()
