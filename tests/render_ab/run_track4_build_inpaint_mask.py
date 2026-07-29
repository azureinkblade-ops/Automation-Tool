"""Track 4 inpainting fallback: create a narrow hip/thigh mask preview.
Evidence-only; does not modify source, Map B, registry, or production code.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app  # establish the repo GPU/PIL import path before importing PIL
from PIL import Image, ImageDraw, ImageFilter

SRC = ROOT / "tests" / "render_ab" / "output" / "map_compare_B" / "917364" / "D.png"
OUT = ROOT / "tests" / "render_ab" / "output" / "track4_inpaint"
OUT.mkdir(parents=True, exist_ok=True)

im = Image.open(SRC).convert("RGB")
w, h = im.size
# Character occupies center. Mask a narrow diagonal strip along the visible
# OUTER hip/robe panel (viewer-left). This avoids face, torso center, hands,
# and front knee while providing room for a jian hilt + scabbard.
# Coordinates are proportional so the probe remains auditable at native size.
poly = [
    (int(w * 0.43), int(h * 0.47)),
    (int(w * 0.50), int(h * 0.49)),
    (int(w * 0.43), int(h * 0.78)),
    (int(w * 0.34), int(h * 0.77)),
]
mask = Image.new("L", im.size, 0)
draw = ImageDraw.Draw(mask)
draw.polygon(poly, fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(radius=max(4, int(w * 0.008))))
mask.save(OUT / "seed917364_jian_mask.png")

preview = im.copy()
overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
od.polygon(poly, fill=(255, 0, 0, 90), outline=(255, 0, 0, 255), width=max(2, w // 250))
preview = Image.alpha_composite(preview.convert("RGBA"), overlay).convert("RGB")
preview.save(OUT / "seed917364_jian_mask_preview.png")
print({"source": str(SRC), "size": [w, h], "polygon": poly,
       "mask": str(OUT / 'seed917364_jian_mask.png'),
       "preview": str(OUT / 'seed917364_jian_mask_preview.png')})
