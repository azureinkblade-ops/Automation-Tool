"""Generate caption .txt files for the chapter>19 TikTok image set in
lora-training/realistic-posts/train-1024/extra-tiktok-ch20plus/

Naming convention mirrors the existing azink_real train set:
  <image>.png  ->  <image>.txt
Each caption starts with the `azink_real` trigger, then a short, style-focused
description built from the novel code, chapter number, and content type.

Content types (from filename suffix):
  EN_/HA_/HP_/SF_<ch>_<n>  -> "chapter scene keyframe"
  deep-scene-<n>           -> "atmospheric scene render"
  variant-<n>              -> "alternate composition render"
  novel-promo-card         -> "novel promo card" (text/graphic overlay; weakest for style)

Novel code -> title/protagonist (from lore):
  EN = Eternal Nexus (Kael Veyra, cyberpunk LitRPG)
  HA = Heavenly Ascension System (Kai, golden ember, cultivation)
  SF = Soulforge Era (Jarek, undercity, gold eyes)
  HP = Hundredfold Path (Liang, xianxia, jade token)
"""
from pathlib import Path

DEST = Path(r"C:\Users\David\Documents\Automation tool\lora-training\realistic-posts\train-1024\extra-tiktok-ch20plus")

NOVEL = {
    "EN": "Eternal Nexus cyberpunk LitRPG scene with Kael Veyra",
    "HA": "Heavenly Ascension cultivation scene with Kai and golden ember qi",
    "HP": "Hundredfold Path xianxia scene with Liang and jade token",
    "SF": "Soulforge Era undercity scene with Jarek and gold eyes",
}

TRIGGER = "azink_real"


def chapter_of(folder: str) -> str:
    # folder like 'en-20', 'en-29-deep', 'hp-21-conflict-acd74ee7'
    num = ""
    for ch in folder.split("-"):
        if ch.isdigit():
            num = ch
            break
    return num


def caption_for(name: str) -> str:
    base = name[:-4]  # strip .png
    folder, img = base.split("__", 1)
    code = folder.split("-")[0].upper()  # en->EN
    novel = NOVEL.get(code, "fantasy web novel scene")
    ch = chapter_of(folder)
    prefix = f"{TRIGGER}, "

    if img.startswith(("EN_", "HA_", "HP_", "SF_")):
        return prefix + f"{novel}, chapter {ch} character scene keyframe, cinematic fantasy illustration"
    if img.startswith("deep-scene-"):
        return prefix + f"{novel}, chapter {ch} atmospheric scene render, moody dramatic lighting, fantasy environment"
    if img.startswith("variant-"):
        return prefix + f"{novel}, chapter {ch} alternate composition, fantasy character illustration"
    if img.startswith("novel-promo-card"):
        return prefix + f"{novel}, chapter {ch} novel promo card, text and graphic overlay (weak style signal)"
    return prefix + f"{novel}, chapter {ch} fantasy illustration"


def main() -> None:
    count = 0
    for p in sorted(DEST.glob("*.png")):
        txt = caption_for(p.name)
        (p.with_suffix(".txt")).write_text(txt + "\n", encoding="utf-8")
        count += 1
    print(f"captions written: {count}")
    # sanity: show a few
    for p in sorted(DEST.glob("*.png"))[:3]:
        print(" -", p.name, "=>", (p.with_suffix(".txt")).read_text().strip())


if __name__ == "__main__":
    main()
