"""Call-site tests: production short-form builders wire the Hermes agent copy.

Plan: .kilo/plans/1786212055633-shortform-callsite-agent-wiring.md

Exercises the two production call sites added by the agent-wiring work:

  * app.make_or_generate_tiktok_pack  (Reel/Short pack, Step 1)
  * app.make_deep_tiktok_pack         (60-75s deep TikTok, Step 2)

and asserts the behavior the plan requires:

  A. A single Hermes run is shared (memoized) across the Reel/Short pack AND
     the deep TikTok, so both record provenance under one _agent_run_id.
  B. A chapter revision change re-invokes the agent (memo key includes text).
  C. A memo hit does NOT overwrite provenance (de-dup via
     _AGENT_RECORDED_PLATFORMS), so the shared run_id is written once per
     platform.
  D. An empty chapter_text fallback resolves authoritative text so the memo
     key is NOT the empty-string sha (e3b0c442...) and does not collapse every
     chapter onto one entry.
  E. Disabled / agent-failure falls back to template copy and records nothing.

Run: python tests/test_agent_shortform_callsite.py   (from repo root)
"""
import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import app as app_mod
import promo_builder as pb
import tools.agent_post_writer as apw

FAILS: list[str] = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")


AGENT_CAPTION = "When the neon rain stops screaming, Kael's system finally accepts his offer as its own."
AGENT_TITLE = "Neon Rain: Kael's Last Offer"
AGENT_COPY = {
    "caption": AGENT_CAPTION,
    "tiktok_title": AGENT_TITLE,
    "content_angle": "system betrayal",
    "intended_audience": "progression fantasy readers",
    "_source": "hermes_agent",
}

ABBR = "EN"
CHAPTER = "12"
NOVEL = "Eternal Nexus"
TITLE = "Chapter 12: Neon Rain"
CHAPTER_BODY = "Kael stood in the neon rain. The system hummed. An offer arrived." * 4

# One shared run_id for the whole memoized chapter.
RUN_ID = "run-callsite-shared"


class _FakeResult:
    def __init__(self, rid=RUN_ID, copy=None):
        self.copy = dict(AGENT_COPY) if copy is None else copy
        self.run_id = rid


def _fake_generate_post_result(abbr, title, chapter, hook, material, **kw):
    _CALLS.append((abbr, chapter, str((material or {}).get("text") or "")[:16]))
    return _FakeResult()


def _fake_agent_result_metadata(result):
    return {
        "_agent_requested": True,
        "_agent_used": False,
        "_agent_status": "ok",
        "_agent_run_id": result.run_id,
        "_agent_source": "hermes_agent",
        "_agent_fallback_reason": None,
    }


# --- promo_builder stub collaborators (so the Reel/Short pack builds offline) ---
TMP = Path(tempfile.mkdtemp(prefix="callsite_pack_test_"))
ASSET_DIR = TMP / "assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)
_IMAGE_PATHS = []
for _i in range(3):
    _p = ASSET_DIR / f"EN_12_{_i}.png"
    _p.write_text("img", encoding="utf-8")
    _p.with_name(f"{_p.name}.track").write_text("main-posts", encoding="utf-8")
    _IMAGE_PATHS.append(str(_p))
_SOUND = ASSET_DIR / "sound.mp3"
_SOUND.write_text("snd", encoding="utf-8")
PACK_FOLDER = TMP / "pack"


def _fake_assets():
    return {
        "imageGroups": [
            {
                "abbr": ABBR,
                "chapter": CHAPTER,
                "files": list(_IMAGE_PATHS),
                "tracks": ["main-posts"] * 3,
                "count": 3,
            }
        ],
        "sounds": [{"path": str(_SOUND)}],
    }


def _fake_folder(*a, **k):
    PACK_FOLDER.mkdir(parents=True, exist_ok=True)
    return PACK_FOLDER


def _fake_outro(folder, *a, **k):
    target = Path(folder) / "novel-promo-card.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("outro", encoding="utf-8")
    return str(target)


def _noop(*a, **k):
    return None


def _fake_overlays(*a, **k):
    return ["OVERLAY ONE", "OVERLAY TWO", "OVERLAY THREE", "READ ON ROYAL ROAD"]


_COLLAB = {name: getattr(app_mod, name) for name in pb.REQUIRED_COLLABORATORS}
_COLLAB.update(
    {
        "list_tiktok_assets": _fake_assets,
        "stable_chapter_folder": _fake_folder,
        "prepare_tiktok_outro_image": _fake_outro,
        "tiktok_chapter_teaser_overlays": _fake_overlays,
        "write_tiktok_video_helper": _noop,
        "generate_deep_tiktok_narration": _noop,
        "generate_tiktok_images": _noop,
        "update_chapter_ledger": _noop,
        "auto_publish_generated_media": lambda folder, payload: payload,
    }
)
pb.set_collaborators(_COLLAB)


# --- heavy deep-pack helpers stubbed at the app layer -------------------------
def _fake_docs_chapter_text(abbr, chapter_number):
    return {
        "abbr": abbr,
        "chapter": chapter_number,
        "title": TITLE,
        "heading": TITLE,
        "text": CHAPTER_BODY,
        "raw_text": CHAPTER_BODY,
    }


def _fake_deep_video_helper(*a, **k):
    return None


def _fake_run_builder(*a, **k):
    return {"created": True, "message": "ok"}


def _fake_repair(folder, metadata=None):
    return metadata or {}


def _fake_quality_gate(folder, text_kind="tiktok", full_duplicate_scan=True):
    return {"ok": True, "folder": str(folder)}


_DEEP_STUBS = {
    "docs_chapter_text": _fake_docs_chapter_text,
    "create_openai_image": _noop,
    "write_deep_tiktok_video_helper": _fake_deep_video_helper,
    "run_generated_video_builder": _fake_run_builder,
    "repair_deep_tiktok_metadata": _fake_repair,
    "folder_quality_gate": _fake_quality_gate,
    "auto_publish_generated_media": lambda folder, payload: payload,
    "reusable_pack_result": lambda *a, **k: None,
    "archive_generated_promo_image": _noop,
    "update_chapter_ledger": _noop,
    "choose_rotating_weekly_promo_audio": lambda: _SOUND,
    "media_duration_seconds": lambda *a, **k: 68.0,
    "slugify": lambda *a, **k: "12",
    "reset_generated_folder": lambda folder, *a, **k: Path(folder).mkdir(parents=True, exist_ok=True),
    "generate_deep_tiktok_narration": _noop,
    "prepare_tiktok_outro_image": _fake_outro,
    "content_hash": lambda v: "h-" + str(hash(v)),
}


def _install_deep_stubs():
    saved = {}
    for name, fn in _DEEP_STUBS.items():
        saved[name] = getattr(app_mod, name)
        setattr(app_mod, name, fn)
    return saved


def _restore_deep_stubs(saved):
    for name, fn in saved.items():
        setattr(app_mod, name, fn)


# --- provenance recording capture ---------------------------------------------
RECORDED: list = []


class _FakeDB:
    @staticmethod
    def insert_generated_social_posts(root, run_id, rows):
        RECORDED.append((run_id, list(rows)))


def _with_agent(enabled=True):
    os.environ["ENABLE_AGENT_POSTS"] = "1" if enabled else "0"


# --- Test A/B/C/D/E -----------------------------------------------------------
_CALLS = []
_ORIG_GEN = apw.generate_post_result
_ORIG_META = apw.agent_result_metadata
_ORIG_DB = app_mod.automation_db

apw.generate_post_result = _fake_generate_post_result
apw.agent_result_metadata = _fake_agent_result_metadata
app_mod.automation_db = _FakeDB
app_mod._AGENT_COPY_MEMO.clear()
app_mod._AGENT_RECORDED_PLATFORMS.clear()

try:
    _with_agent(True)
    deep_saved = _install_deep_stubs()

    # A. Reel/Short pack + deep TikTok share one Hermes run (memoized).
    RECORDED.clear()
    pack = app_mod.make_or_generate_tiktok_pack(ABBR, CHAPTER, chapter_text=CHAPTER_BODY)
    check("A reel/short pack has agent caption", AGENT_CAPTION in pack.get("instagram_reel_caption", ""), True)
    check("A reel/short pack _agent_run_id in metadata",
          json.loads((PACK_FOLDER / "metadata.json").read_text(encoding="utf-8")).get("_agent_run_id"), RUN_ID)

    deep = app_mod.make_deep_tiktok_pack(ABBR, CHAPTER)
    check("A deep caption uses agent copy", AGENT_CAPTION in deep.get("caption", ""), True)
    check("A deep title uses agent copy", deep.get("tiktok_title"), AGENT_TITLE)

    # Provenance written for both products under the SAME run_id.
    _run_ids = {r[0] for r in RECORDED}
    check("A one shared run_id across pack+deep", _run_ids, {RUN_ID})
    _all_plats = sorted(p for _, rows in RECORDED for (p, _t, _u, _fr) in rows)
    check("A platforms recorded", _all_plats,
          sorted(["instagram_reel", "tiktok_long", "youtube_short"]))
    # Single Hermes invocation because of the memo (Reel/Short + deep same chapter).
    check("A memoized -> one Hermes call", len(_CALLS), 1)

    # C. A memo hit does NOT overwrite provenance: a second full build within TTL
    # reuse the memo and must not re-record (de-dup via _AGENT_RECORDED_PLATFORMS).
    deep_saved2 = _install_deep_stubs()
    RECORDED.clear()
    _CALLS.clear()
    app_mod.make_or_generate_tiktok_pack(ABBR, CHAPTER, chapter_text=CHAPTER_BODY)
    app_mod.make_deep_tiktok_pack(ABBR, CHAPTER)
    check("C memo hit -> no new Hermes call", len(_CALLS), 0)
    check("C memo hit -> no new provenance write", len(RECORDED), 0)
    _restore_deep_stubs(deep_saved2)

    # B. A chapter revision change re-invokes the agent.
    RECORDED.clear()
    _CALLS.clear()
    app_mod._AGENT_COPY_MEMO.clear()
    app_mod.make_or_generate_tiktok_pack(ABBR, CHAPTER, chapter_text="a totally different revised body here")
    check("B revision change re-invokes agent", len(_CALLS), 1)
    app_mod._AGENT_COPY_MEMO.clear()

    # D. Empty chapter_text fallback resolves authoritative text so the memo key
    # is NOT the empty-string sha (e3b0c442...); docs_chapter_text supplies body.
    RECORDED.clear()
    _CALLS.clear()
    app_mod._AGENT_COPY_MEMO.clear()
    app_mod.make_or_generate_tiktok_pack(ABBR, CHAPTER, chapter_text="")
    check("D empty chapter_text still resolves agent", len(_CALLS), 1)
    # The resolver was handed real chapter text (not the empty sha key).
    check("D resolver received non-empty text", _CALLS[0][2] != "", True)

    _restore_deep_stubs(deep_saved)

    # E. Disabled agent -> template copy, no provenance, no Hermes call.
    _with_agent(False)
    app_mod._AGENT_COPY_MEMO.clear()
    app_mod._AGENT_RECORDED_PLATFORMS.clear()
    RECORDED.clear()
    _CALLS.clear()
    deep_saved3 = _install_deep_stubs()
    pack_off = app_mod.make_or_generate_tiktok_pack(ABBR, CHAPTER, chapter_text=CHAPTER_BODY)
    check("E disabled -> no Hermes call", len(_CALLS), 0)
    check("E disabled -> no provenance", len(RECORDED), 0)
    check("E disabled -> template copy (no agent caption)",
          AGENT_CAPTION in pack_off.get("instagram_reel_caption", ""), False)
    deep_off = app_mod.make_deep_tiktok_pack(ABBR, CHAPTER)
    check("E disabled deep -> no agent caption", AGENT_CAPTION in deep_off.get("caption", ""), False)
    check("E disabled deep -> no provenance", len(RECORDED), 0)
    _restore_deep_stubs(deep_saved3)
finally:
    apw.generate_post_result = _ORIG_GEN
    apw.agent_result_metadata = _ORIG_META
    app_mod.automation_db = _ORIG_DB
    app_mod._AGENT_COPY_MEMO.clear()
    app_mod._AGENT_RECORDED_PLATFORMS.clear()
    shutil.rmtree(TMP, ignore_errors=True)


if FAILS:
    print(f"FAILED ({len(FAILS)}):")
    for item in FAILS:
        print(" -", item)
    sys.exit(1)
print("All agent short-form call-site wiring tests passed.")
