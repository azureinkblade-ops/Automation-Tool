import os, glob
from PIL import Image

ASM = os.path.expanduser("~/Documents/Automation tool/lora-training/comic-style/prologue-assembly")
out = os.path.join(ASM, "_prologue_webtoon_strip.png")

files = sorted(glob.glob(os.path.join(ASM, "[0-9][0-9]_*.png")))
imgs = [Image.open(f).convert("RGB") for f in files]

# normalize all to a common width (use the max width so nothing upscales-blurs too hard; use min to keep file smaller)
W = min(im.width for im in imgs)
gap = 24  # px black gutter between pages
bg = (7, 17, 31)  # brand navy #07111F

scaled = []
for im in imgs:
    if im.width != W:
        h = round(im.height * W / im.width)
        im = im.resize((W, h), Image.LANCZOS)
    scaled.append(im)

total_h = sum(im.height for im in scaled) + gap * (len(scaled) - 1)
strip = Image.new("RGB", (W, total_h), bg)
y = 0
for im in scaled:
    strip.paste(im, (0, y))
    y += im.height + gap

strip.save(out, "PNG")
print("pages:", len(scaled))
print("size:", strip.size)
print("out:", out)
print("bytes:", os.path.getsize(out))
