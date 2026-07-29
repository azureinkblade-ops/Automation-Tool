"""Render Stage 2 V1 source/mask/guide overlays for fixture QA."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def resolve(base: Path, raw: str | None) -> Path | None:
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from PIL import Image, ImageDraw

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = args.manifest.parent
    cell_w, cell_h, label_h = 512, 448, 54
    columns = 4
    rows = (len(payload["cases"]) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * (cell_h + label_h)), "#0b0d10")
    draw_sheet = ImageDraw.Draw(sheet)
    for i, case in enumerate(payload["cases"]):
        source = Image.open(resolve(base, case["source_path"])).convert("RGB")
        mask = Image.open(resolve(base, case["mask_path"])).convert("L")
        guide_path = resolve(base, case.get("guide_path"))
        guide = Image.open(guide_path).convert("RGB") if guide_path else source
        red = Image.new("RGB", source.size, (255, 32, 32))
        overlay = Image.blend(Image.composite(red, source, mask), source, 0.45)
        panels = []
        for image in (overlay, guide):
            thumb = image.copy()
            thumb.thumbnail((cell_w // 2, cell_h))
            panels.append(thumb)
        cell = Image.new("RGB", (cell_w, cell_h), "#050608")
        for panel_index, panel in enumerate(panels):
            x = panel_index * (cell_w // 2) + ((cell_w // 2 - panel.width) // 2)
            y = (cell_h - panel.height) // 2
            cell.paste(panel, (x, y))
        x0 = (i % columns) * cell_w
        y0 = (i // columns) * (cell_h + label_h)
        sheet.paste(cell, (x0, y0))
        label = f"{case['case_id']} {case['strata']['object_class']} | red=mask, right=guide"
        draw_sheet.text((x0 + 5, y0 + cell_h + 5), label, fill="white")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(json.dumps({"cases": len(payload["cases"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
