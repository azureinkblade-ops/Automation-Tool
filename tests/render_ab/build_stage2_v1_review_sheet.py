"""Build Stage 2 V1 review contact sheets: source | candidate | diff per case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def add_label(image: Image.Image, text: str) -> Image.Image:
    font = ImageDraw.getfont() if hasattr(ImageDraw, "getfont") else None
    labeled = image.copy()
    draw = ImageDraw.Draw(labeled)
    draw.text((6, 4), text, fill=(255, 255, 0))
    return labeled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--max", type=int, default=24)
    args = parser.parse_args()

    manifest = args.manifest.resolve()
    base = manifest.parent
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    cells: list[Image.Image] = []
    for index, case in enumerate(payload["cases"][: args.max]):
        cid = case["case_id"]
        source = base / case["source_path"]
        cand = ROOT / "tests/render_ab/output/stage2_v1" / cid / "candidate.png"
        diff = ROOT / "tests/render_ab/output/stage2_v1" / cid / "diff.png"
        try:
            s = Image.open(source).convert("RGB").resize((384, 384))
            c = Image.open(cand).convert("RGB").resize((384, 384)) if cand.exists() else Image.new("RGB", (384, 384), (20, 20, 20))
            d = Image.open(diff).convert("RGB").resize((384, 384)) if diff.exists() else Image.new("RGB", (384, 384), (20, 20, 20))
        except Exception as exc:
            s = Image.new("RGB", (384, 384), (60, 0, 0))
            c = Image.new("RGB", (384, 384), (60, 0, 0))
            d = Image.new("RGB", (384, 384), (60, 0, 0))
        row = Image.fromarray(np.hstack([
            np.asarray(add_label(s, f"{cid} SRC")),
            np.asarray(add_label(c, "CAND")),
            np.asarray(add_label(d, "DIFF")),
        ]))
        cells.append(row)

    cols = args.cols
    rows = [
        Image.fromarray(np.hstack([np.asarray(cell) for cell in cells[i : i + cols]]))
        for i in range(0, len(cells), cols)
    ]
    sheet = Image.fromarray(np.vstack([np.asarray(row) for row in rows])) if rows else Image.new("RGB", (384, 384))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(json.dumps({"output": str(args.output), "cases": len(cells)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
