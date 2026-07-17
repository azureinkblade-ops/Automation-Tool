"""Characterization tests for promo_copy (Task 1 extraction).

These assert the extracted module reproduces app.py's pure-copy behavior.
For rotation-dependent functions we compare against app.py with a FRESH
promo-rotation state (rotation_next returns 0 on first call), which is exactly
what promo_copy's in-memory default does. app.py and promo_copy must agree.

Run: python tests/test_promo_copy.py   (from repo root, with PYTHONPATH unset)
"""
import sys, os, subprocess
import importlib

# Ensure a clean import environment (strip Hermes/Codex venv leakage).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# Fresh rotation state so app.py's rotation_next returns 0 (matches promo_copy default).
# rotation_next has a disk side-effect; reset BEFORE any comparison so app and pc agree.
from pathlib import Path
PROMO_STATE = Path(REPO) / "promo-image-rotation.json"
_backup = None
if PROMO_STATE.exists():
    _backup = PROMO_STATE.read_text(encoding="utf-8")
    PROMO_STATE.unlink()

import app as app_mod
import promo_copy as pc

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- pure, rotation-independent ---
check("social_profile EN name", pc.social_profile("EN")["name"], "Eternal Nexus")
check("social_profile HA name", pc.social_profile("HA")["name"], "Heavenly Ascension System")
check("social_profile by full name", pc.social_profile("Hundredfold Path")["name"], "Hundredfold Path")
check("social_profile unknown", pc.social_profile("zzz")["name"], "zzz")

a = pc.rotated_hashtags("EN", "EN-mon", chapter_text="x")
b = pc.rotated_hashtags("EN", "EN-tue", chapter_text="x")
check("rotated_hashtags differ by seed", a != b, True)
check("rotated_hashtags anchored brand", "#AzureInkblade" in a, True)
check("rotated_hashtags novel tag", "#EternalNexus" in a, True)

x1 = pc.rotated_x_hashtags("EN", "EN-mon")
x2 = pc.rotated_x_hashtags("EN", "EN-tue")
check("rotated_x_hashtags differ by seed", x1 != x2, True)
check("rotated_x_hashtags has novel", "#EternalNexus" in x1, True)

# --- agreement with app.py (fresh rotation => rotation_next returns 0) ---
app = app_mod
check("app social_profile EN", app.social_profile("EN")["name"], pc.social_profile("EN")["name"])
check("app rotated_hashtags EN-mon", app.rotated_hashtags("EN", "EN-mon", chapter_text="x"), pc.rotated_hashtags("EN", "EN-mon", chapter_text="x"))
check("app rotated_x_hashtags EN-mon", app.rotated_x_hashtags("EN", "EN-mon"), pc.rotated_x_hashtags("EN", "EN-mon"))
check("app focused_social_cta EN", app.focused_social_cta("EN", "patreon"), pc.focused_social_cta("EN", "patreon"))
check("app compact_chapter_hook", app.compact_chapter_hook("Title", "Some chapter text here."), pc.compact_chapter_hook("Title", "Some chapter text here."))
check("app normalized chapter id", app.normalize_chapter_id("Chapter 12", ""), pc.normalize_chapter_id("Chapter 12", ""))
check("app normalize prologue", app.normalize_chapter_id("Prologue", ""), pc.normalize_chapter_id("Prologue", ""))
check("app slugify", app.slugify("Hello World!"), pc.slugify("Hello World!"))
check("app engaged prompt", app.engagement_prompt_line("EN", "stakes"), pc.engagement_prompt_line("EN", "stakes"))
check("app platform engaged", app.platform_engagement_prompt_line("EN", "stakes", "instagram"), pc.platform_engagement_prompt_line("EN", "stakes", "instagram"))

# build_platform_posts needs material; compare a representative call (rr-live off).
# It depends on two app/DB collaborators (chapter_ledger_entry, release_status_for_chapter)
# that live in app.py / release_state (Task 3) and are intentionally NOT imported by
# promo_copy. Inject the REAL app collaborators so we compare apples-to-apples: the
# extracted logic must reproduce app.py exactly given the same ledger data.
# NOTE: rotation_next has a side-effect on a shared state file; reset it before EACH
# build so both calls start from a clean rotation index (otherwise app's call advances
# the counter and pc's call sees the advanced state -> false mismatch).
material = {"abbr": "EN", "novel": "Eternal Nexus", "phrases": ["A spark lit the dark."], "chapter": "12", "chapter_number": "12"}
if PROMO_STATE.exists():
    PROMO_STATE.unlink()
app_bp = app.build_platform_posts("Chapter 12", "A spark lit the dark.", material)
if PROMO_STATE.exists():
    PROMO_STATE.unlink()
pc_bp = pc.build_platform_posts(
    "Chapter 12", "A spark lit the dark.", material,
    rotation_next=app.rotation_next,
    chapter_ledger_entry=app.chapter_ledger_entry,
    release_status_for_chapter=app.release_status_for_chapter,
)
check("app build_platform_posts caption", app_bp["caption"], pc_bp["caption"])
check("app build_platform_posts x_post", app_bp["x_post"], pc_bp["x_post"])
check("app build_platform_posts focus", app_bp["post_focus"], pc_bp["post_focus"])

# restore rotation state
if _backup is not None:
    PROMO_STATE.write_text(_backup, encoding="utf-8")

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS", "all promo_copy characterization checks matched app.py")
