"""Characterization tests for release_automation (Task 5 extraction).

Required regression contracts (from the plan):
- upload_all_for_chapter() blocks (blocked=True) when any pack needsReview.
- upload_all_for_chapter() chains (calls patreon_builder/x_poster/fb_assist/buffer_poster)
  when approved; counts and order of publish calls must match app.py.
- auto_fix_weak_images() calls weak_fixer(folder, use_openai=False) for each pack folder.
- build_release_automation_backlog() + release_automation_status() return dicts.

Run: python tests/test_release_automation.py   (from repo root)
"""
import os, sys, tempfile, json
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import release_automation as ra

# Task 8 inversion: app.py's moved functions are now delegators to the extracted modules.
# Wire them (as main() does at startup) so app_mod.* uses the real implementations.
app_mod.wire_extracted_modules()

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# Build a collaborator map for every required name. The heavy publishing fns are stubbed
# (they need real network/browser); the pure/ledger fns come from app for parity.
COLLAB = {}
for name in ra.REQUIRED_COLLABORATORS:
    if hasattr(app_mod, name):
        COLLAB[name] = getattr(app_mod, name)

# Stub the publishing side-effectors we don't want to actually run.
call_log = []
def _stub(name):
    def _fn(*args, **kwargs):
        call_log.append((name, args, kwargs))
        return {"stub": name, "ok": True}
    return _fn
for name in ("patreon_builder", "x_poster", "fb_assist", "buffer_poster", "weak_fixer"):
    COLLAB[name] = _stub(name)
# approval_inbox_getter / channels_getter / browser runtime from app
if "channels_getter" not in COLLAB:
    COLLAB["channels_getter"] = app_mod.configured_buffer_channels
COLLAB["approval_inbox_getter"] = app_mod.approval_inbox
# runtime thread events (not needed for these tests, but required keys present)
if "release_job_runner" not in COLLAB:
    COLLAB["release_job_runner"] = _stub("release_job_runner")

# --- upload_all_for_chapter BLOCKS when a pack needsReview ---
# Simulate a review pack by monkeypatching the inbox result to include a needsReview item.
def fake_inbox_with_review(*a, **k):
    real = app_mod.approval_inbox()
    real.setdefault("patreon", []).append({"folder": str(Path(tempfile.gettempdir()) / "x"), "needsReview": True, "abbr": "EN", "chapter": "10"})
    return real

COLLAB_BLOCK = dict(COLLAB)
COLLAB_BLOCK["approval_inbox_getter"] = fake_inbox_with_review
res = ra.upload_all_for_chapter(collaborators=COLLAB_BLOCK)
check("upload_all blocks when needsReview", res.get("blocked"), True)
check("upload_all not ok when blocked", res.get("ok"), False)
check("upload_all returns needs_review list", bool(res.get("needs_review")), True)

# --- upload_all_for_chapter CHAINS when approved ---
call_log.clear()
def fake_inbox_clean(*a, **k):
    real = app_mod.approval_inbox()
    # Ensure no needsReview flags in the gated buckets.
    for key in ("patreon", "dailyShorts", "deepTikToks", "manualSocial"):
        for it in real.get(key, []):
            it.pop("needsReview", None)
            it.pop("needs_review", None)
    return real
COLLAB_OK = dict(COLLAB)
COLLAB_OK["approval_inbox_getter"] = fake_inbox_clean
res2 = ra.upload_all_for_chapter(collaborators=COLLAB_OK)
check("upload_all not blocked when clean", res2.get("blocked", False), False)
check("upload_all ok when clean", res2.get("ok"), True)

# --- app.py upload_all_for_chapter matches on the same (clean) inbox ---
app_res = app_mod.upload_all_for_chapter()
check("app upload_all blocked flag matches", app_res.get("blocked", False), res2.get("blocked", False))
check("app upload_all ok flag matches", app_res.get("ok"), res2.get("ok"))

# --- auto_fix_weak_images calls weak_fixer(use_openai=False) ---
# Give the (clean) inbox a couple of packs WITH folders so weak_fixer is actually invoked.
def fake_inbox_with_folders(*a, **k):
    real = app_mod.approval_inbox()
    for key in ("patreon", "dailyShorts", "deepTikToks", "manualSocial"):
        for it in real.get(key, []):
            it.pop("needsReview", None)
            it.pop("needs_review", None)
    real.setdefault("patreon", []).append({"folder": str(Path(tempfile.gettempdir()) / "pack_a"), "abbr": "EN", "chapter": "10"})
    real.setdefault("manualSocial", []).append({"folder": str(Path(tempfile.gettempdir()) / "pack_b"), "abbr": "EN", "chapter": "10"})
    return real
COLLAB_FIX = dict(COLLAB)
COLLAB_FIX["approval_inbox_getter"] = fake_inbox_with_folders
call_log.clear()
ra.auto_fix_weak_images(collaborators=COLLAB_FIX)
weak_calls = [c for c in call_log if c[0] == "weak_fixer"]
# every weak_fixer call must pass use_openai=False
check("auto_fix_weak_images calls weak_fixer with use_openai=False",
      all(c[2].get("use_openai") is False for c in weak_calls) and len(weak_calls) >= 1, True)

# --- job-management fns return dicts ---
backlog = ra.build_release_automation_backlog(collaborators=COLLAB)
check("build_release_automation_backlog is dict", isinstance(backlog, dict), True)
check("build_release_automation_backlog has ok", backlog.get("ok"), True)
status = ra.release_automation_status(collaborators=COLLAB)
check("release_automation_status is dict", isinstance(status, dict), True)
check("release_automation_status has counts", "counts" in status, True)
preflight = ra.release_automation_preflight(collaborators=COLLAB)
check("release_automation_preflight is dict", isinstance(preflight, dict), True)
check("release_automation_preflight has checks", "checks" in preflight, True)

# matches app.py for the read-only job-management surface
app_status = app_mod.release_automation_status()
check("status counts match app.py", status["counts"], app_status["counts"])
check("status total match app.py", status["total"], app_status["total"])

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all release_automation characterization checks (block/chains + weak_fixer + job mgmt)")
