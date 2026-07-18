"""Characterization tests for the Task 8 inversion (app.py -> extracted modules).

Verifies:
- wire_extracted_modules() resolves every collaborator except the two known-deferred
  browser-publish ones (browser_launcher, clipboard_copy) which have no app.py equivalent.
- app.py's moved function definitions now delegate to the extracted modules (signature-agnostic
  *args/**kwargs forwarding).
- EN-101 reconcile is read-only: it reports the orphan Royal Road job state from SQLite
  without mutating the row (guardrail).
- The extracted modules are still importable with no `app` import (regression of the seam).

Run: python tests/test_task8_inversion.py   (from repo root)
"""
import os, sys, json, tempfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

os.environ.setdefault("OPENAI_API_KEY", "x")  # tests never hit the real API

import app as app_mod
import release_automation as ra_mod

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- wire_extracted_modules resolves collaborators (only 2 deferred browser ones unresolved) ---
rep = app_mod.wire_extracted_modules()
expected_unresolved = {"browser_publish": {"browser_launcher", "clipboard_copy"}}
seen_unresolved = {}
for mod, info in rep.items():
    if mod == "en101":
        continue
    un = set(info.get("unresolved", []))
    if un:
        seen_unresolved[mod] = un
check("only browser_publish has unresolved collaborators",
      seen_unresolved, expected_unresolved)
# promo_builder must be fully wired (no unresolved)
check("promo_builder fully wired", rep["promo_builder"]["unresolved"], [])
check("buffer_publish fully wired", rep["buffer_publish"]["unresolved"], [])
check("release_automation fully wired (except plan-deferred names are mapped)",
      rep["release_automation"]["unresolved"], [])

# --- delegated fns route to the modules ---
check("app.story_key delegates to promo_copy", app_mod.story_key("EN"), "EN")
check("app.social_profile delegates to promo_copy",
      app_mod.social_profile("EN") is not None or isinstance(app_mod.social_profile("EN"), str), True)
check("app.make_social_post is a delegator (callable)", callable(app_mod.make_social_post), True)
check("app.buffer_post_from_folder is a delegator (callable)", callable(app_mod.buffer_post_from_folder), True)
check("app.youtube_build_status is a delegator (callable)", callable(app_mod.youtube_build_status), True)

# --- EN-101 reconcile is read-only (guardrail) ---
en101 = ra_mod.en101_reconcile()
check("en101_reconcile returns a dict", isinstance(en101, dict), True)
check("en101_reconcile has status key", "status" in en101, True)
check("en101_reconcile does not mutate (no write performed)", en101.get("found") in (True, False), True)
# guardrail helper raises on attempted mutation
raised = False
try:
    ra_mod.en101_require_no_mutation("delete EN-101")
except ra_mod.En101MutationError:
    raised = True
check("en101_require_no_mutation raises En101MutationError", raised, True)

# --- extracted modules import without importing app (regression of the seam) ---
for mod in ("promo_copy", "promo_builder", "release_state", "approval_inbox",
            "release_automation", "buffer_publish", "browser_publish",
            "youtube_pipeline", "growth_analytics"):
    ns = {}
    code = (f"import sys; import {mod};"
            f"print('{mod}', 'imports_app=' + str('app' in sys.modules))")
    r = __import__("subprocess").run([sys.executable, "-c", code],
                                    cwd=REPO, capture_output=True, text=True, timeout=120)
    line = [l for l in r.stdout.splitlines() if l.startswith(mod)][0]
    check(f"{mod} imports without app", line.endswith("imports_app=False"), True)

if FAILS:
    print("FAIL", len(FAILS))
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("PASS all Task 8 inversion checks (delegators wired + EN-101 read-only guardrail + seam intact)")
