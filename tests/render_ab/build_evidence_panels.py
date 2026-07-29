"""Build a per-case evidence panel for the fresh re-judgment pass.
Panel layout (left->right):
  source | candidate | diff | context-expanded crop | mask overlay
context-expanded crop = mask bbox expanded by 60% on each side (clamped).
Output: .hermes/evidence/stage2-v1-audit-reviews/<cid>/evidence_panel.png
Plus a JSON map of evidence refs for the script that applies fresh grades.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from PIL import Image
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".hermes/evidence/stage2-v1-audit-reviews"
MAN = ROOT / ".hermes/evidence/stage2-validation-v1-manifest.json"
cases = json.load(open(MAN))["cases"]

margin_frac = 0.6
panel_map = {}
for c in cases:
    cid = c["case_id"]
    if cid == "v1-020":
        continue  # excluded fixture
    rec = json.load(open(OUT / f"{cid}.json"))
    if rec.get("evaluation_excluded"):
        continue
    ev = rec["evidence"]
    src = np.array(Image.open(ROOT / ev["source_path"]).convert("RGB"))
    cand = np.array(Image.open(ROOT / ev["candidate_path"]).convert("RGB"))
    diffp = ROOT / ev["diff_path"]
    diff = np.array(Image.open(diffp).convert("RGB")) if diffp.exists() else np.zeros_like(src)
    maskp = ROOT / ev["mask_path"]
    mask = np.array(Image.open(maskp).convert("L"))
    # context-expanded crop from mask bbox
    ys, xs = np.where(mask > 127)
    if len(xs) == 0:
        # fallback to existing target crop bbox
        tc = np.array(Image.open(ROOT / ev["crop_path"]).convert("RGB")) if Path(ROOT / ev["crop_path"]).exists() else cand
        ctx = tc
    else:
        h, w = mask.shape
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        mw, mh = int((x1 - x0) * margin_frac), int((y1 - y0) * margin_frac)
        x0, x1 = max(0, x0 - mw), min(w, x1 + mw)
        y0, y1 = max(0, y0 - mh), min(h, y1 + mh)
        ctx = cand[y0:y1, x0:x1]
    # mask overlay on candidate
    ov = cand.copy()
    ov[mask > 127] = (ov[mask > 127] * 0.4 + np.array([255, 0, 0]) * 0.6).astype(int)
    # resize all to common height
    TH = 384
    def rz(a):
        a = np.array(a)
        sh, sw = a.shape[:2]
        return np.array(Image.fromarray(a).resize((max(1, int(TH * sw / sh)), TH)))
    imgs = [rz(src), rz(cand), rz(diff), rz(ctx), rz(ov)]
    gap = 6
    total_w = sum(i.shape[1] for i in imgs) + gap * (len(imgs) - 1)
    panel = np.zeros((TH, total_w, 3), np.uint8)
    x = 0
    for i in imgs:
        panel[:, x:x + i.shape[1]] = i
        x += i.shape[1] + gap
    pp = OUT / cid / "evidence_panel.png"
    pp.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(panel).save(pp)
    panel_map[cid] = {
        "panel": str(pp.relative_to(ROOT)).replace("\\", "/"),
        "source": str(ROOT / ev["source_path"]).replace("\\", "/"),
        "candidate": str(ROOT / ev["candidate_path"]).replace("\\", "/"),
        "diff": str(ROOT / ev["diff_path"]).replace("\\", "/"),
        "context_crop": str(pp.relative_to(ROOT)).replace("\\", "/"),
        "mask_overlay": str(ROOT / ev["mask_overlay_path"]).replace("\\", "/") if ev.get("mask_overlay_path") else None,
    }
    print(cid, "panel built")
json.dump(panel_map, open(OUT / "_evidence_panels.json", "w"), indent=2)
print("panels built for", len(panel_map), "valid cases")
