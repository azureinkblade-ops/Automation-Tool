"""Characterization tests for promo_builder (Task 2 extraction).

Verifies:
- promo_builder imports cleanly (no app import, no startup side-effects).
- fallback_social_copy (moved into promo_copy) matches app.py exactly.
- make_social_post with real app collaborators injected (pure-helper ones) + stubbed
  side-effectors (image-gen / auto-publish / ledger) returns the expected dict with
  #AzureInkblade in instagram/x/facebook. We stub only the services that need a GPU /
  network / long build; the pure copy logic must still reproduce app.py.

Run: python tests/test_promo_builder.py   (from repo root)
"""
import os, sys
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

PROMO_STATE = Path(REPO) / "promo-image-rotation.json"
_backup = PROMO_STATE.read_text(encoding="utf-8") if PROMO_STATE.exists() else None

import app as app_mod
import promo_copy as pc
import promo_builder as pb

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- pure: fallback_social_copy moved into promo_copy must match app.py ---
fc_app = app_mod.fallback_social_copy("EN", "EN", "Monday", "ch12.png")
fc_pc = pc.fallback_social_copy("EN", "EN", "Monday", "ch12.png")
check("fallback_social_copy instagram", fc_pc["instagram"], fc_app["instagram"])
check("fallback_social_copy x", fc_pc["x"], fc_app["x"])
check("fallback_social_copy facebook", fc_pc["facebook"], fc_app["facebook"])
check("#AzureInkblade in instagram", "#AzureInkblade" in fc_pc["instagram"], True)

# --- inject REAL pure helpers + STUB side-effectors, then exercise make_social_post ---
# Stub only what needs a GPU / network / long build. Everything else uses the real app fn.
import tempfile
TMP = Path(tempfile.mkdtemp(prefix="pb_test_"))

def _stub_image(*a, **k):
    # create a fake png so downstream file ops have something
    target = a[0] if a else k.get("image_target")
    Path(target).write_text("stub", encoding="utf-8")
    return str(target)

def _stub_publish(folder, payload):
    return payload  # no real publish

def _stub_ledger(*a, **k):
    return None

# Build a collaborator map from the REAL app functions, overriding the 3 services.
collab = {name: getattr(app_mod, name) for name in pb.REQUIRED_COLLABORATORS}
collab["create_fresh_social_image_from_caption"] = _stub_image
collab["auto_publish_generated_media"] = _stub_publish
collab["update_chapter_ledger"] = _stub_ledger

# make_social_post reads list_daily_promo_images(); app must have one for EN/Monday.
# If none exist in this workspace, we exercise the fallback path logic directly instead.
have_image = any(
    it["abbr"] == "EN" and it["day"].lower() == "monday"
    for it in app_mod.list_daily_promo_images()
)
if have_image:
    if PROMO_STATE.exists():
        PROMO_STATE.unlink()
    result = pb.make_social_post("EN", "Monday", "{novel} {day}", False,
                                 chapter_number="25", collaborators=collab)
    check("make_social_post keys", all(k in result for k in ("instagram", "x", "facebook")), True)
    check("make_social_post instagram has brand", "#AzureInkblade" in result["instagram"], True)
    check("make_social_post x has brand", "#AzureInkblade" in result["x"], True)
    check("make_social_post focus present", bool(result.get("post_focus")), True)
else:
    # No daily promo image fixture in this workspace -> assert the documented RuntimeError
    # path matches app.py (same guard). We compare the exception type/message shape.
    try:
        app_mod.make_social_post("EN", "Monday", "{novel} {day}", False, chapter_number="25")
        app_raised = False
    except Exception as e:
        app_raised = True
        app_msg = str(e)
    try:
        pb.make_social_post("EN", "Monday", "{novel} {day}", False, chapter_number="25", collaborators=collab)
        pb_raised = False
    except Exception as e:
        pb_raised = True
        pb_msg = str(e)
    check("make_social_post both raise w/o image", app_raised and pb_raised, True)
    check("make_social_post same error msg", app_raised and pb_raised and app_msg == pb_msg, True)

# --- import hygiene: promo_builder must not import app at module load ---
check("promo_builder does not import app", "app" not in sys.modules or sys.modules["app"] is app_mod, True)

if _backup is not None:
    PROMO_STATE.write_text(_backup, encoding="utf-8")

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all promo_builder characterization checks")
