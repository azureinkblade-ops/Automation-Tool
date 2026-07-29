"""Build a labeled contact sheet for Stage 2 V1 source qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pattern", default="_generated_bg_*/*.png")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()

    from PIL import Image, ImageDraw

    candidates = []
    seen = set()
    unique_index = 0
    for path in sorted(args.root.glob(args.pattern)):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        if unique_index < args.offset:
            unique_index += 1
            continue
        unique_index += 1
        candidates.append((path, digest))
        if args.limit and len(candidates) >= args.limit:
            break

    thumb_w, thumb_h, label_h = 256, 448, 42
    columns = 5
    rows = (len(candidates) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + label_h)), "#101319")
    draw = ImageDraw.Draw(sheet)
    index_rows = []
    for index, (path, digest) in enumerate(candidates, start=1):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        x = ((index - 1) % columns) * thumb_w
        y = ((index - 1) // columns) * (thumb_h + label_h)
        cell = Image.new("RGB", (thumb_w, thumb_h), "#080a0d")
        cell.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
        sheet.paste(cell, (x, y))
        folder = path.parent.name.replace("_generated_bg_", "")
        label = f"{index:02d} {folder} / {path.stem}"
        draw.text((x + 5, y + thumb_h + 4), label, fill="white")
        index_rows.append({
            "index": index,
            "path": str(path.resolve()),
            "sha256": digest,
            "folder": folder,
            "filename": path.name,
            "width": Image.open(path).width,
            "height": Image.open(path).height,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    args.index.write_text(json.dumps({"count": len(index_rows), "rows": index_rows}, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(index_rows), "sheet": str(args.output), "index": str(args.index)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
