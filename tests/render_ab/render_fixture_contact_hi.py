"""Re-render fixture contact sheet at USABLE resolution: one case per row,
candidate at 384px tall, crisp mask overlay (alpha-blended, not resized-threshold
which loses detail), and green bbox. This makes mask<->target correspondence
independently decidable instead of relying on a 256px downscale.
"""
from pathlib import Path
import json, sys, argparse
import numpy as np
from PIL import Image
import cv2

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--hi", type=int, default=10**9)
    args = ap.parse_args()
    man = json.loads(args.manifest.read_text(encoding="utf-8"))
    mp = args.manifest.resolve().parent
    TH = 384
    pad = 8
    label_h = 22
    row_w = (TH * 3) + pad * 4 + 220  # 3 panels + spacing + metrics gutter
    lo = getattr(args, "lo", 0); hi = getattr(args, "hi", len(man["cases"]))
    visible = man["cases"][lo:hi]
    n = len(visible)
    sheet = np.zeros((n * (TH + label_h + 6), row_w, 3), dtype=np.uint8)
    row = 0
    for i, c in enumerate(man["cases"]):
        if i < lo or i >= hi:
            continue
        cid = c["case_id"]
        ot = c["object_type"]
        cand = ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png"
        mask = (mp / c["mask_path"]).resolve()
        y0 = row * (TH + label_h + 6)
        row += 1
        # candidate (aspect-preserving resize to TH tall)
        if cand.exists():
            cim = np.asarray(Image.open(cand).convert("RGB"))
            h, w = cim.shape[:2]
            tw = int(TH * w / h)
            cim = np.asarray(Image.fromarray(cim).resize((tw, TH)))
        else:
            tw = TH; cim = np.full((TH, TH, 3), 30, np.uint8)
        # mask at FULL res -> bbox
        a = np.asarray(Image.open(mask).convert("L"))
        mh, mw = a.shape
        ys, xs = np.where(a > 127)
        bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
        # scale factors mask->candidate thumb
        sx = tw / mw; sy = TH / mh
        # overlay: blend red onto candidate where mask true (resized mask)
        mthumb = (np.asarray(Image.open(mask).convert("L").resize((tw, TH))) > 127)
        ov = cim.copy()
        ov[mthumb] = (ov[mthumb] * 0.35 + np.array([255, 40, 40]) * 0.65).astype(np.uint8)
        # bbox in thumb coords
        rx0, rx1 = int(bx0 * sx), int(bx1 * sx)
        ry0, ry1 = int(by0 * sy), int(by1 * sy)
        bb = cim.copy()
        cv2.rectangle(bb, (rx0, ry0), (rx1, ry1), (0, 255, 0), 2)
        # paste 3 panels
        sheet[y0:y0 + TH, pad:pad + tw] = cim
        sheet[y0:y0 + TH, pad * 2 + tw:pad * 2 + 2 * tw] = ov
        sheet[y0:y0 + TH, pad * 3 + 2 * tw:pad * 3 + 3 * tw] = bb
        # metrics text gutter
        gx = pad * 4 + 3 * tw
        lines = [cid, ot, f"target={c.get('target_region')}",
                 f"bbox=({bx0},{by0})-({bx1},{by1})", f"mask={mw}x{mh}"]
        for li, t in enumerate(lines):
            cv2.putText(sheet, t[:34], (gx, y0 + 18 + li * 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (210, 210, 210), 1)
        cv2.putText(sheet, "L:cand C:mask R:bbox", (pad, y0 + TH + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 200, 255), 1)
    Image.fromarray(sheet).save(args.out)
    print("WROTE", args.out)


if __name__ == "__main__":
    main()
