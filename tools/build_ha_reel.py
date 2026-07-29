#!/usr/bin/env python3
"""Build a 9:16 HA manhwa teaser reel from the REAL manhwa pages (curated approved/ set).

Each page: crop bottom third (iconic panel), cover-scale to 1080x1920, gentle zoom,
burn teaser caption in a BOTTOM band as SHORT STACKED LINES (pre-wrapped so nothing
overflows the 1080px frame). End card: title + CTA + hashtags.

ffmpeg: tools/ffmpeg/bin/ffmpeg.exe. No AI gen.
"""
import os, subprocess, tempfile, shutil

ROOT = r"C:\Users\David\Documents\Automation tool"
SRC = os.path.join(ROOT, "lora-training", "comic-style", "approved")
FF = os.path.join(ROOT, "tools", "ffmpeg", "bin", "ffmpeg.exe")
OUTDIR = os.path.join(ROOT, "output")
os.makedirs(OUTDIR, exist_ok=True)

# (file, teaser caption)  -- curated approved/ set. SEQUENCED FROM THE PROLOGUE
# (011-019, where the System first appears) so the teaser hooks at the story's start,
# not chapter 1. All chosen pages have a clean bottom/iconic panel.
PAGES = [
    ("azink_comic_011_apartment_shift.png",
     "The room felt heavier."),
    ("azink_comic_013_system_initializing.png",
     "A system no one understands just initialized."),
    ("azink_comic_016_pain_knees.png",
     "Pain tore through his chest."),
    ("azink_comic_017_ember_core.png",
     "A dormant ember, finally caught flame."),
    ("azink_comic_019_closing_pulse.png",
     "The System pulsed once. Watching."),
    ("azink_comic_015_sync_lines.png",
     "Something was waking in him."),
]
DUR = 2.5
END_DUR = 3.0
# Caption rendering: short lines so they never exceed 1080px. At fontsize 38 a line
# should stay <= ~20 chars to be safe. We wrap on word boundaries to MAX_CHARS.
CAP_FS = 38
MAX_CHARS = 20

def esc(s):
    return s.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")

def _synth_music(path, dur, sr=44100):
    """Write an original 18s-ish ambient piece: 3-chord pad progression + bell arpeggio.
    Pure stdlib. Returns nothing; writes a 16-bit stereo WAV."""
    import math, struct, wave
    # chord blocks (root, fifth, upper) cycling every 6s: Am-ish, F-ish, C-ish
    chords = [
        (110.00, 164.81, 261.63),   # A2 / E4 / C4
        ( 87.31, 110.00, 130.81),   # F2 / A3 / C3
        (130.81, 196.00, 261.63),   # C3 / G3 / C4
    ]
    arp = [261.63, 329.63, 392.00, 440.00, 523.25, 659.25]  # C4 E4 G4 A4 C5 E5
    n = int(dur * sr)
    left = [0.0] * n
    right = [0.0] * n
    block = 6.0  # seconds per chord
    for i in range(n):
        t = i / sr
        b = min(int(t // block), len(chords) - 1)
        r, fv, up = chords[b]
        # pad: three sines with a slow tremolo so it breathes
        lfo = 0.85 + 0.15 * math.sin(2 * math.pi * 0.15 * t)
        pad = (0.16 * math.sin(2 * math.pi * r * t)
               + 0.10 * math.sin(2 * math.pi * fv * t)
               + 0.06 * math.sin(2 * math.pi * up * t)) * lfo
        # arpeggio: a pluck every 0.5s, note from scale, quick exp decay
        st0 = b * block
        k = int((t - st0) // 0.5)
        ph = t - st0 - k * 0.5
        nt = arp[k % len(arp)]
        plk = 0.13 * math.exp(-ph * 5.0) * math.sin(2 * math.pi * nt * ph)
        s = pad + plk
        left[i] = s
        right[i] = s
    # normalize to peak ~0.8, fade in/out 1s
    peak = max(1e-6, max(abs(x) for x in left))
    gain = 0.8 / peak
    fade = int(sr * 1.0)
    out = []
    for i in range(n):
        g = gain
        if i < fade:
            g *= i / fade
        elif i > n - fade:
            g *= (n - i) / fade
        lv = max(-1.0, min(1.0, left[i] * g))
        rv = max(-1.0, min(1.0, right[i] * g))
        out.append(struct.pack("<hh", int(lv * 32767), int(rv * 32767)))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(out))

def wrap(text, max_chars=MAX_CHARS):
    """Split into lines of <=max_chars on word boundaries (keeps apostrophes)."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def bottom_band_filters(lines, fs=CAP_FS):
    """drawtext filters, stacked, centered, sitting in the bottom band."""
    n = len(lines)
    lh = int(fs * 1.35)  # line height
    total_h = n * lh
    # bottom of band anchored ~120px from frame bottom
    base_y = f"(h - {total_h + 60})"
    filters = []
    for idx, line in enumerate(lines):
        y = f"{base_y} + {idx * lh}"
        filters.append(
            f"drawtext=text='{esc(line)}':fontcolor=white:fontsize={fs}:"
            f"box=1:boxcolor=black@0.55:boxborderw=14:x=(w-text_w)/2:y={y}:"
            f"shadowcolor=black:shadowx=2:shadowy=2"
        )
    return ",".join(filters)

clips = []
tmp = tempfile.mkdtemp(prefix="ha_reel_")
try:
    for i, (fname, caption) in enumerate(PAGES):
        src = os.path.join(SRC, fname)
        seg = os.path.join(tmp, f"page_{i}.mp4")
        cap_filters = bottom_band_filters(wrap(caption))
        # Show the FULL strip (never crop baked art text): scale to FIT inside 1080x1920
        # (any aspect), pad remaining space black, caption in bottom band. No crop.
        vf = (
            f"scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"format=yuv420p,"
            f"{cap_filters}"
        )
        cmd = [FF, "-y", "-loop", "1", "-i", src, "-t", str(DUR), "-vf", vf,
               "-r", "30", "-pix_fmt", "yuv420p", seg]
        print(f"[page {i}] {fname} -> {wrap(caption)}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clips.append(seg)

    end = os.path.join(tmp, "end.mp4")
    title = "HEAVENLY ASCENSION SYSTEM"
    cta = "Follow for more \u2014 new info coming soon"
    tags1 = "#HeavenlyAscensionSystem #manhwa #webtoon #cultivation"
    tags2 = "#fantasy #webnovel #xianxia #webcomic #fyp"
    vf = (
        f"color=c=0x0a0a14:s=1080x1920:d={END_DUR},"
        f"format=yuv420p,"
        f"drawtext=text='{esc(title)}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y=h*0.36:shadowcolor=black:shadowx=3:shadowy=3,"
        f"drawtext=text='{esc(cta)}':fontcolor=0xffd27f:fontsize=34:x=(w-text_w)/2:y=h*0.52:shadowcolor=black:shadowx=2:shadowy=2,"
        f"drawtext=text='{esc(tags1)}':fontcolor=0xbfc6d4:fontsize=22:x=(w-text_w)/2:y=h*0.64:shadowcolor=black:shadowx=2:shadowy=2,"
        f"drawtext=text='{esc(tags2)}':fontcolor=0xbfc6d4:fontsize=22:x=(w-text_w)/2:y=h*0.69:shadowcolor=black:shadowx=2:shadowy=2"
    )
    cmd = [FF, "-y", "-f", "lavfi", "-i", vf, "-t", str(END_DUR),
           "-r", "30", "-pix_fmt", "yuv420p", end]
    print("[end card]")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    clips.append(end)

    out = os.path.join(OUTDIR, "ha_reel_teaser.mp4")
    silent = os.path.join(tmp, "silent.mp4")
    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    cmd = [FF, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", silent]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- Background music: synthesize an original EVOLVING piece (no copyright risk) ---
    # 3-chord progression (Am -> F -> C feel), pad shifts every 6s, + bell arpeggio
    # of real notes every 0.5s so it moves instead of droning. Python stdlib.
    music = os.path.join(tmp, "music.wav")
    total = len(PAGES) * DUR + END_DUR
    _synth_music(music, total)
    # Mux music under the video (video stream copied, audio encoded aac).
    cmd = [FF, "-y", "-i", silent, "-i", music,
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("WROTE", out)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
