"""Build clean full-resolution per-case HR review sheets (candidate | diff).

Case ID goes in a SEPARATE black header strip ABOVE the artwork; no text is
burned into the image pixels (unlike the 384px contact sheet). Output:
.hermes/evidence/defect_review/<case_id>_hr.png
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tests/render_ab/output/stage2_v1"
DST = ROOT / ".hermes/evidence/defect_review"
DST.mkdir(parents=True, exist_ok=True)


def main() -> int:
    manifest = json.loads(
        (ROOT / ".hermes/evidence/stage2-validation-v1-manifest.json").read_text()
    )
    count = 0
    for case in manifest["cases"]:
        cid = case["case_id"]
        c = Image.open(SRC / cid / "candidate.png").convert("RGB")
        d = Image.open(SRC / cid / "diff.png").convert("RGB")
        hdr_h = 30
        w = c.width + d.width
        sheet = Image.new("RGB", (w, c.height + hdr_h), (0, 0, 0))
        sheet.paste(c, (0, hdr_h))
        sheet.paste(d, (c.width, hdr_h))
        draw = ImageDraw.Draw(sheet)
        draw.text((6, 6), f"{cid}   LEFT: candidate    RIGHT: diff", fill=(255, 255, 0))
        sheet.save(DST / f"{cid}_hr.png")
        count += 1
    print(json.dumps({"hr_sheets": count, "dst": str(DST)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
