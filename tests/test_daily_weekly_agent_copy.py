"""Acceptance tests for daily/weekly social posts consuming validated Hermes agent copy.

Plan: .kilo/plans/1786132069687-daily-weekly-agent-copy-wiring.md

Verifies:
1. Agent success -> daily uses Hermes copy (contains differentiated caption, not generic).
2. Agent failure -> generic fallback unchanged.
3. Agent disabled -> generic fallback unchanged.
4. Weekly multi-novel isolation (each novel gets its own copy, no cross-bleed).
5. _agent_used truthfulness in written metadata.json / social-post-record.json.

Run: python tests/test_daily_weekly_agent_copy.py   (from repo root)
"""
import os, sys, json
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import promo_builder as pb

FAILS = []

def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")

# --- collaborator plumbing: real pure helpers + stubbed side-effectors ---
import tempfile
TMP = Path(tempfile.mkdtemp(prefix="agent_copy_test_"))

def _stub_image(*a, **k):
    target = a[0] if a else k.get("image_target")
    Path(target).write_text("stub", encoding="utf-8")
    return str(target)

def _stub_publish(folder, payload):
    return payload

def _stub_ledger(*a, **k):
    return None

_COLLAB = {name: getattr(app_mod, name) for name in pb.REQUIRED_COLLABORATORS}
_COLLAB["create_fresh_social_image_from_caption"] = _stub_image
_COLLAB["auto_publish_generated_media"] = _stub_publish
_COLLAB["update_chapter_ledger"] = _stub_ledger

# Replace list_daily_promo_images with a deterministic fixture for EN/Monday.
FAKE_IMAGE = {"abbr": "HP", "novel": "Hundredfold Path", "day": "Monday", "filename": "HP_Monday.png"}
FAKE_IMAGE_EN = {"abbr": "EN", "novel": "Emberflight", "day": "Monday", "filename": "EN_Monday.png"}

def _fake_list():
    return [FAKE_IMAGE, FAKE_IMAGE_EN]

_COLLAB["list_daily_promo_images"] = _fake_list

AGENT_CAPTION = "Silver light poured from a wound like blood, and the hall went quiet."
GENERIC = "One scene from"

# Distinct per-novel agent copy for isolation tests.
NOVEL_COPY = {
    "HP": {"caption": "HP agent copy: the gate split open under her hand.",
           "cta": "Read ahead on Patreon.", "hashtags": ["#HundredfoldPath", "#RoyalRoad"]},
    "EN": {"caption": "EN agent copy: the engine hummed with borrowed time.",
           "cta": "Read ahead on Patreon.", "hashtags": ["#Emberflight", "#RoyalRoad"]},
}

# --- Test 1: agent success -> daily uses Hermes copy ---
AGENT_HOOK = "The hall held its breath as silver light spilled from the wound."
agent_copy = {"caption": AGENT_CAPTION, "hook": AGENT_HOOK, "cta": "Read ahead on Patreon.",
              "hashtags": ["#HundredfoldPath", "#RoyalRoad"], "_source": "hermes_agent"}
meta = {}
res = pb.make_social_post("HP", "Monday", "{novel} {day}", False,
                          agent_copy=agent_copy, agent_meta=meta, collaborators=_COLLAB)
check("T1 instagram has agent caption", AGENT_CAPTION in res["instagram"], True)
check("T1 x has agent hook", AGENT_HOOK in res["x"], True)
check("T1 facebook has agent caption", AGENT_CAPTION in res["facebook"], True)
check("T1 instagram not generic", GENERIC not in res["instagram"], True)
check("T1 x not generic", GENERIC not in res["x"], True)
check("T1 source hermes_agent", res.get("source"), "hermes_agent")
check("T1 _agent_used True", meta.get("_agent_used"), True)
check("T1 _agent_source hermes_agent", meta.get("_agent_source"), "hermes_agent")

# --- Test 2: agent failure (None) -> generic fallback unchanged ---
res_fallback = pb.make_social_post("HP", "Monday", "{novel} {day}", False,
                                  chapter_number="1", collaborators=_COLLAB)
check("T2 generic fallback present", GENERIC in res_fallback["instagram"], True)
check("T2 source fallback", res_fallback.get("source"), "fallback")
check("T2 no agent caption", AGENT_CAPTION not in res_fallback["instagram"], True)

# --- Test 3: agent disabled (empty dict) -> generic fallback unchanged ---
res_disabled = pb.make_social_post("HP", "Monday", "{novel} {day}", False,
                                   agent_copy={}, chapter_number="2", collaborators=_COLLAB)
check("T3 generic fallback present", GENERIC in res_disabled["instagram"], True)
check("T3 no agent caption", AGENT_CAPTION not in res_disabled["instagram"], True)

# --- Test 4: weekly multi-novel isolation ---
def _weekly_resolver(abbr, day, template, material):
    cp = NOVEL_COPY.get(abbr)
    if not cp:
        return None, None
    m = dict(cp)
    m["_source"] = "hermes_agent"
    return m, {"_agent_requested": True, "_agent_used": True}

week = pb.build_week_social_posts(False, days=["Monday"], agent_copy_for=_weekly_resolver, collaborators=_COLLAB)
hp_post = next((p for p in week["posts"] if p.get("abbr") == "HP"), None)
en_post = next((p for p in week["posts"] if p.get("abbr") == "EN"), None)
check("T4 hp post exists", hp_post is not None, True)
check("T4 en post exists", en_post is not None, True)
check("T4 hp copy isolated", "HP agent copy" in hp_post["instagram"], True)
check("T4 en copy isolated", "EN agent copy" in en_post["instagram"], True)
check("T4 hp copy not in en", "HP agent copy" not in en_post["instagram"], True)
check("T4 en copy not in hp", "EN agent copy" not in hp_post["instagram"], True)

# --- Test 5: _agent_used truth in written artifacts ---
folder = Path(res["folder"])
md = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
rec = json.loads((folder / "social-post-record.json").read_text(encoding="utf-8"))
check("T5 metadata _agent_used True", md.get("_agent_used"), True)
check("T5 metadata _agent_source", md.get("_agent_source"), "hermes_agent")
check("T5 record agentMeta used True", rec.get("agentMeta", {}).get("_agent_used"), True)

# Fallback artifact must record _agent_used False (no agent meta passed -> absent, treat as not used).
fb_folder = Path(res_fallback["folder"])
fb_rec = json.loads((fb_folder / "social-post-record.json").read_text(encoding="utf-8"))
check("T5 fallback record no agentMeta", "_agent_used" not in fb_rec.get("agentMeta", {}), True)

if FAILS:
    print("FAIL")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("OK")
