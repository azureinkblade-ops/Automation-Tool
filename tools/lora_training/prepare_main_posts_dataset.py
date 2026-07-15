"""C3 prep for azink_main LoRA (Workstream C).

COPY-ONLY, CPU-only, no GPU. Stages clean training images for azink_main:
- Source A: lora-training/main-posts/approved/  (15 curated, already captioned)
- Source B: campaigns/ + tiktok-posts/ chapters 19-25, NON-deep, KEYFRAME only
  (filenames starting EN_/HA_/HP_/SF_). Excludes reel/animated + promo-card + 'other'
  to avoid Pexels-stock / text-overlay contamination (user directive).

Each staged image is center-cropped to 1024x1024 and paired with a .txt caption that
starts with the azink_main trigger (adapted from caption_tiktok_ch20plus.py).
Originals are COPIED, never moved.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO = Path(r"C:\Users\David\Documents\Automation tool")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
TRIGGER = "azink_main"
NOVEL = {
    "EN": "Eternal Nexus cyberpunk LitRPG scene with Kael Veyra",
    "HA": "Heavenly Ascension cultivation scene with Kai and golden ember qi",
    "HP": "Hundredfold Path xianxia scene with Liang and jade token",
    "SF": "Soulforge Era undercity scene with Jarek and gold eyes",
}
DEST = REPO / "lora-training" / "main-posts" / "datasets" / "train-1024"
RES = 1024


def chapter_of(folder: str) -> str:
    for ch in folder.split("-"):
        if ch.isdigit():
            return ch
    return "?"


def is_keyframe(name: str) -> bool:
    return name[:3].upper() in ("EN_", "HA_", "HP_", "SF_")


def caption_for(code: str, folder: str) -> str:
    novel = NOVEL.get(code.upper(), "fantasy web novel scene")
    ch = chapter_of(folder)
    return f"{TRIGGER}, {novel}, chapter {ch} character scene keyframe, cinematic fantasy illustration"


def center_crop_1024(src: Path, dst: Path) -> None:
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((RES, RES), Image.LANCZOS)
    im.save(dst, "PNG")


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0

    # Source A: approved/ (already captioned -> keep original caption from captions/ if present)
    approved = REPO / "lora-training" / "main-posts" / "approved"
    captions_dir = REPO / "lora-training" / "main-posts" / "captions"
    for f in sorted(approved.iterdir()):
        if f.suffix.lower() not in IMG_EXT:
            continue
        dst_img = DEST / f.name
        if not dst_img.exists():
            center_crop_1024(f, dst_img)
        copied += 1
        # Prefer the curated caption in captions/; fall back to a generic azink_main caption.
        src_cap = captions_dir / f.with_suffix(".txt").name
        dst_cap = DEST / f.with_suffix(".txt").name
        if src_cap.exists():
            shutil.copy2(src_cap, dst_cap)
        elif not dst_cap.exists():
            code = f.name[:2].upper()
            dst_cap.write_text(caption_for(code, f.name), encoding="utf-8")

    # Source B: campaigns/ + tiktok-posts/ chapters 19-25, non-deep, keyframe only
    def chap_campaign(p: Path) -> int | None:
        m = re.search(r"chapter[-_](\d+)", p.name.lower()) or re.search(r"-ch(\d+)", p.name.lower())
        return int(m.group(1)) if m else None

    def chap_tiktok(p: Path) -> int | None:
        m = re.search(r"^(en|ha|hp|sf)-(\d+)", p.name.lower())
        return int(m.group(2)) if m else None

    for root, chapfn in (("campaigns", chap_campaign), ("tiktok-posts", chap_tiktok)):
        base = REPO / root
        if not base.exists():
            continue
        for d in base.iterdir():
            if not d.is_dir():
                continue
            if "-deep" in d.name.lower():  # exclude deep (Pexels risk)
                continue
            c = chapfn(d)
            if c is None or not (19 <= c <= 25):
                continue
            for f in d.iterdir():
                if f.suffix.lower() not in IMG_EXT:
                    continue
                if not is_keyframe(f.name):  # keyframe only
                    continue
                dst_img = DEST / f"{d.name}__{f.name}"
                if dst_img.exists():
                    skipped += 1
                    continue
                center_crop_1024(f, dst_img)
                code = f.name[:2].upper()
                (DEST / (dst_img.name[:-4] + ".txt")).write_text(
                    caption_for(code, d.name), encoding="utf-8"
                )
                copied += 1

    pairs = len(list(DEST.glob("*.png"))) + len(list(DEST.glob("*.jpg")))
    caps = len(list(DEST.glob("*.txt")))
    print(f"[prep] copied={copied} skipped(dup)={skipped}")
    print(f"[prep] staged image files={pairs}, caption files={caps} -> {DEST}")


if __name__ == "__main__":
    main()
