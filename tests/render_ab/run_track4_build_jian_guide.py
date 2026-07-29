"""Build a simple structural jian guide inside the approved inpaint mask.
The guide is not a final asset; it gives the inpaint pipeline explicit weapon
geometry while all pixels outside the mask remain the frozen source.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app
from PIL import Image, ImageDraw

SRC = ROOT / "tests" / "render_ab" / "output" / "map_compare_B" / "917364" / "D.png"
OUT = ROOT / "tests" / "render_ab" / "output" / "track4_inpaint"
GUIDE = OUT / "seed917364_jian_guide.png"

im = Image.open(SRC).convert("RGB")
d = ImageDraw.Draw(im)
# Jian at the visible outer hip. Place the guard BELOW the hands so all three
# components remain readable: wrapped hilt, horizontal guard, rigid scabbard.
# Scabbard body (dark teal, broad enough not to become a ribbon).
d.polygon([(332, 713), (358, 718), (306, 1022), (275, 1014)],
          fill=(24, 58, 64), outline=(205, 211, 205))
d.line([(336, 716), (285, 1016)], fill=(170, 187, 182), width=3)
# Strong silver guard, visibly perpendicular to the scabbard.
d.polygon([(314, 700), (372, 711), (370, 722), (312, 711)],
          fill=(210, 216, 212), outline=(58, 67, 66))
# Wrapped hilt above guard and distinct pommel.
d.polygon([(338, 705), (352, 708), (362, 658), (348, 655)],
          fill=(92, 51, 35), outline=(205, 190, 160))
for y in range(661, 704, 8):
    d.line([(347, y), (359, y + 3)], fill=(191, 157, 104), width=2)
d.ellipse((348, 646, 365, 663), fill=(210, 216, 212), outline=(55, 65, 64), width=2)
# Scabbard cap.
d.polygon([(271, 1007), (309, 1016), (306, 1030), (268, 1021)],
          fill=(190, 199, 193), outline=(45, 58, 59))
im.save(GUIDE)
print(GUIDE)
