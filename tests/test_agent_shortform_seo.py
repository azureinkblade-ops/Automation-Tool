"""Acceptance tests: agent-aware Reels/Shorts + 60s TikTok with deterministic SEO adaptation.

Plan: .kilo/plans/1786139344585-agent-aware-shortform-seo.md

Verifies the ten acceptance criteria:
 1. Reel/Short consumes agent copy (SHORT_HOOK_TEMPLATES displaced).
 2. 60s TikTok consumes agent copy.
 3. Reel != TikTok, and the TikTok is materially longer (separate adaptations).
 4. Fallback parity: no agent copy -> current generic output.
 5. Reused-pack branch still serves agent copy.
 6. A single Hermes run is reused across Instagram + Reel + Short + TikTok.
 7. Provenance rows for instagram_reel / youtube_short / tiktok_long under one run_id.
 8. Boundary: promo_builder imports neither app nor tools.agent_post_writer.
 9. Deterministic SEO keywords (pure, total, order-stable).
10. Release state derives from Python state, never from agent copy.

Run: python tests/test_agent_shortform_seo.py   (from repo root)
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

FAILS: list[str] = []


def check(name, got, want):
    if got != want:
        FAILS.append(f"{name}\n   got : {got!r}\n   want: {want!r}")


# The exact acceptance copy from the plan.
AGENT_CAPTION = (
    "When the neon rain stops screaming, Kael's system finally accepts his offer as its own\u2026"
)
AGENT_HOOK = "When the neon rain stops screaming, Kael listens."
GENERIC_HOOK = app_mod.SHORT_HOOK_TEMPLATES["EN"]

AGENT_COPY = {
    "hook": AGENT_HOOK,
    "caption": AGENT_CAPTION,
    "content_angle": "system betrayal",
    "intended_audience": "progression fantasy readers",
    "_source": "hermes_agent",
}

NOVEL = "Eternal Nexus"
ABBR = "EN"
CHAPTER = "12"
TITLE = "Chapter 12: Neon Rain"


# --- Test 1: Reel/Short consumes agent copy -------------------------------------
reel = app_mod.build_reel_short_copy(AGENT_COPY, NOVEL, CHAPTER, None, platform="instagram_reel")
short = app_mod.build_reel_short_copy(AGENT_COPY, NOVEL, CHAPTER, None, platform="youtube_short")

check("T1 reel contains agent caption", AGENT_CAPTION in reel["caption"], True)
check("T1 short contains agent caption", AGENT_CAPTION in short["caption"], True)
check("T1 reel has no SHORT_HOOK_TEMPLATES", GENERIC_HOOK in reel["caption"], False)
check("T1 short has no SHORT_HOOK_TEMPLATES", GENERIC_HOOK in short["caption"], False)
# Shorts title derives from the agent hook, capped by Python at 90 chars.
check("T1 shorts title from agent hook", short["title"].startswith("When the neon rain"), True)
check("T1 shorts title <= 90", len(short["title"]) <= 90, True)
check("T1 shorts title not generic", short["title"].endswith("Promo #Shorts"), False)


# --- Test 2: 60s TikTok consumes agent copy -------------------------------------
tiktok = app_mod.build_long_tiktok_copy(
    AGENT_COPY, NOVEL, CHAPTER, None, title=TITLE, hook="overlay hook"
)
check("T2 tiktok contains agent caption", AGENT_CAPTION in tiktok, True)
check("T2 tiktok has no SHORT_HOOK_TEMPLATES", GENERIC_HOOK in tiktok, False)


# --- Test 3: Reel != TikTok, TikTok materially longer ---------------------------
check("T3 reel != tiktok", reel["caption"] == tiktok, False)
check("T3 short != tiktok", short["caption"] == tiktok, False)
check("T3 tiktok materially longer", len(tiktok) > len(reel["caption"]) * 1.2, True)
# The long form must add real narrative structure, not just reframe the caption.
check("T3 tiktok has stakes framing", "cost stops being theoretical" in tiktok, True)


# --- Test 4: Fallback parity (no agent copy -> current generic output) ----------
fb_short = app_mod.build_reel_short_copy(None, NOVEL, CHAPTER, None, platform="youtube_short")
gen_short = app_mod.youtube_shorts_metadata(NOVEL, CHAPTER)
check("T4 shorts description parity", fb_short["caption"], gen_short["description"])
check("T4 shorts title parity", fb_short["title"], gen_short["title"])
check("T4 shorts fallback keeps SHORT_HOOK_TEMPLATES", GENERIC_HOOK in fb_short["caption"], True)

fb_tiktok = app_mod.build_long_tiktok_copy(None, NOVEL, CHAPTER, None, title=TITLE, hook="overlay hook")
check(
    "T4 deep tiktok caption parity",
    fb_tiktok,
    app_mod.deep_tiktok_caption(ABBR, CHAPTER, TITLE, "overlay hook"),
)

# instagram_reel_caption rotates its intro line per call, so byte-equality across two
# separate calls is impossible by design. Assert the builder DELEGATES to it: every
# line except the rotating intro must match.
fb_reel = app_mod.build_reel_short_copy(None, NOVEL, CHAPTER, None, platform="instagram_reel")["caption"]
gen_reel = app_mod.instagram_reel_caption(NOVEL, CHAPTER)
check("T4 reel fallback delegates to generic", fb_reel.split("\n")[1:], gen_reel.split("\n")[1:])

# Empty/whitespace caption must be treated as "no agent copy".
blank = app_mod.build_reel_short_copy({"caption": "   "}, NOVEL, CHAPTER, None, platform="youtube_short")
check("T4 blank agent caption -> fallback", GENERIC_HOOK in blank["caption"], True)


# --- promo_builder pack harness (stubbed side-effects) --------------------------
TMP = Path(tempfile.mkdtemp(prefix="shortform_pack_test_"))
ASSET_DIR = TMP / "assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

_image_paths = []
for _i in range(3):
    _p = ASSET_DIR / f"EN_12_{_i}.png"
    _p.write_text("img", encoding="utf-8")
    _p.with_name(f"{_p.name}.track").write_text("main-posts", encoding="utf-8")
    _image_paths.append(str(_p))
_sound = ASSET_DIR / "sound.mp3"
_sound.write_text("snd", encoding="utf-8")


def _fake_assets():
    return {
        "imageGroups": [
            {
                "abbr": ABBR,
                "chapter": CHAPTER,
                "files": list(_image_paths),
                "tracks": ["main-posts"] * 3,
                "count": 3,
            }
        ],
        "sounds": [{"path": str(_sound)}],
    }


PACK_FOLDER = TMP / "pack"


def _fake_folder(*a, **k):
    PACK_FOLDER.mkdir(parents=True, exist_ok=True)
    return PACK_FOLDER


def _fake_outro(folder, *a, **k):
    target = Path(folder) / "novel-promo-card.png"
    target.write_text("outro", encoding="utf-8")
    return str(target)


def _noop(*a, **k):
    return None


def _fake_overlays(*a, **k):
    return ["OVERLAY ONE", "OVERLAY TWO", "OVERLAY THREE", "READ ON ROYAL ROAD"]


COLLAB = {name: getattr(app_mod, name) for name in pb.REQUIRED_COLLABORATORS}
COLLAB.update(
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


# --- Test 5: reused-pack branch still serves agent copy -------------------------
meta_fresh: dict = {"_agent_run_id": "run-shortform-1"}
pack1 = pb.make_tiktok_pack(
    ABBR, CHAPTER, force_new_images=True, chapter_text="body text",
    agent_copy=AGENT_COPY, agent_meta=meta_fresh, collaborators=COLLAB,
)
check("T5 fresh pack reel has agent copy", AGENT_CAPTION in pack1["instagram_reel_caption"], True)
check("T5 fresh pack shorts has agent copy", AGENT_CAPTION in pack1["youtube_shorts_description"], True)
check("T5 fresh pack no generic hook", GENERIC_HOOK in pack1["youtube_shorts_description"], False)
check("T5 fresh pack _agent_used", meta_fresh.get("_agent_used"), True)

# Second build with force_new_images=False must hit the reuse branch and still be agent-aware.
meta_reuse: dict = {"_agent_run_id": "run-shortform-1"}
pack2 = pb.make_tiktok_pack(
    ABBR, CHAPTER, force_new_images=False, chapter_text="body text",
    agent_copy=AGENT_COPY, agent_meta=meta_reuse, collaborators=COLLAB,
)
check("T5 reuse branch was taken", bool(pack2.get("reused_existing_pack")), True)
check("T5 reused pack reel has agent copy", AGENT_CAPTION in pack2["instagram_reel_caption"], True)
check("T5 reused pack shorts has agent copy", AGENT_CAPTION in pack2["youtube_shorts_description"], True)
check("T5 reused pack no generic hook", GENERIC_HOOK in pack2["youtube_shorts_description"], False)
check("T5 reused pack _agent_used", meta_reuse.get("_agent_used"), True)

# Sidecar files must keep their names and carry the agent copy.
check("T5 reel sidecar exists", (PACK_FOLDER / "instagram-reel-caption.txt").exists(), True)
check("T5 shorts title sidecar exists", (PACK_FOLDER / "youtube-shorts-title.txt").exists(), True)
check("T5 shorts desc sidecar exists", (PACK_FOLDER / "youtube-shorts-description.txt").exists(), True)
check(
    "T5 reel sidecar has agent copy",
    AGENT_CAPTION in (PACK_FOLDER / "instagram-reel-caption.txt").read_text(encoding="utf-8"),
    True,
)

# Provenance keys land in metadata.json but never in public post text.
_meta_json = json.loads((PACK_FOLDER / "metadata.json").read_text(encoding="utf-8"))
check("T5 metadata has _agent_run_id", _meta_json.get("_agent_run_id"), "run-shortform-1")
check("T5 metadata has _agent_used", _meta_json.get("_agent_used"), True)
check("T5 provenance absent from reel text", "_agent_run_id" in pack2["instagram_reel_caption"], False)
check("T5 provenance absent from shorts text", "_agent_run_id" in pack2["youtube_shorts_description"], False)

# Fallback through the pack (no agent copy) must restore the generic hook.
meta_none: dict = {}
pack_generic = pb.make_tiktok_pack(
    ABBR, CHAPTER, force_new_images=True, chapter_text="body text",
    agent_copy=None, agent_meta=meta_none, collaborators=COLLAB,
)
check("T5 generic pack keeps SHORT_HOOK", GENERIC_HOOK in pack_generic["youtube_shorts_description"], True)
check("T5 generic pack _agent_used False", meta_none.get("_agent_used"), False)


# --- Test 6: a single Hermes run is reused across all products ------------------
CALLS: list[tuple] = []


class _FakeResult:
    def __init__(self):
        self.copy = dict(AGENT_COPY)
        self.run_id = "run-memo-1"


def _fake_generate_post_result(abbr, title, chapter, hook, material, **kw):
    CALLS.append((abbr, chapter))
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


import tools.agent_post_writer as apw

_orig_generate = apw.generate_post_result
_orig_metadata = apw.agent_result_metadata
apw.generate_post_result = _fake_generate_post_result
apw.agent_result_metadata = _fake_agent_result_metadata
app_mod._AGENT_COPY_MEMO.clear()

try:
    # Four independent acquisitions for the same chapter (Instagram, Reel, Short, TikTok).
    run_ids = set()
    for _ in range(4):
        _copy, _meta = app_mod.resolve_agent_post_copy_cached(
            ABBR, TITLE, CHAPTER, "hook", {"abbr": ABBR}
        )
        run_ids.add(_meta.get("_agent_run_id"))
    check("T6 exactly one Hermes call", len(CALLS), 1)
    check("T6 one shared run_id", run_ids, {"run-memo-1"})

    # Metadata must be a per-caller copy: mutating one must not poison the memo.
    _c1, _m1 = app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, CHAPTER, "hook", {})
    _m1["_agent_used"] = True
    _c2, _m2 = app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, CHAPTER, "hook", {})
    check("T6 memo returns metadata copies", _m2.get("_agent_used"), False)

    # A different chapter must not reuse the memo.
    app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, "13", "hook", {})
    check("T6 different chapter re-runs", len(CALLS), 2)

    # Chapterless (novel-highlight) runs must never be cached.
    CALLS.clear()
    app_mod.resolve_agent_post_copy_cached(ABBR, NOVEL, "", "hook", {})
    app_mod.resolve_agent_post_copy_cached(ABBR, NOVEL, "", "hook", {})
    check("T6 chapterless runs not memoized", len(CALLS), 2)

    # Failures must stay retryable (only successes are memoized).
    def _failing(abbr, title, chapter, hook, material, **kw):
        CALLS.append((abbr, chapter))
        class _R:
            copy = None
            run_id = "run-fail"
        return _R()

    apw.generate_post_result = _failing
    app_mod._AGENT_COPY_MEMO.clear()
    CALLS.clear()
    app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, "77", "hook", {})
    app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, "77", "hook", {})
    check("T6 failures stay retryable", len(CALLS), 2)
finally:
    apw.generate_post_result = _orig_generate
    apw.agent_result_metadata = _orig_metadata
    app_mod._AGENT_COPY_MEMO.clear()


# --- Test 7: provenance rows under one run_id -----------------------------------
RECORDED: list = []


class _FakeDB:
    @staticmethod
    def insert_generated_social_posts(root, run_id, rows):
        RECORDED.append((run_id, list(rows)))


_orig_db = app_mod.automation_db
app_mod.automation_db = _FakeDB
try:
    app_mod.record_generated_shortform_posts(
        {"_agent_run_id": "run-prov-1", "_agent_fallback_reason": None},
        [
            ("instagram_reel", reel["caption"], True),
            ("youtube_short", short["caption"], True),
            ("tiktok_long", tiktok, True),
        ],
    )
    check("T7 one insert call", len(RECORDED), 1)
    _run_id, _rows = RECORDED[0]
    check("T7 shared run_id", _run_id, "run-prov-1")
    check("T7 platforms", [r[0] for r in _rows], ["instagram_reel", "youtube_short", "tiktok_long"])
    check("T7 agent_used flags", [r[2] for r in _rows], [True, True, True])

    # No run_id -> no write at all.
    RECORDED.clear()
    app_mod.record_generated_shortform_posts({}, [("instagram_reel", "x", True)])
    check("T7 no run_id -> no write", len(RECORDED), 0)

    # A DB failure must never propagate.
    class _Boom:
        @staticmethod
        def insert_generated_social_posts(*a, **k):
            raise RuntimeError("db down")

    app_mod.automation_db = _Boom
    try:
        app_mod.record_generated_shortform_posts(
            {"_agent_run_id": "run-prov-2"}, [("tiktok_long", "x", True)]
        )
        check("T7 diagnostics never raise", True, True)
    except Exception as exc:
        check("T7 diagnostics never raise", f"raised {exc}", True)
finally:
    app_mod.automation_db = _orig_db


# --- Test 8: boundary (promo_builder stays Hermes-unaware) ----------------------
_pb_src = Path(REPO, "promo_builder.py").read_text(encoding="utf-8")
check("T8 no 'import app'", "import app\n" in _pb_src, False)
check("T8 no agent_post_writer import", "agent_post_writer" in _pb_src, False)
check("T8 no ENABLE_AGENT_POSTS read", "ENABLE_AGENT_POSTS" in _pb_src, False)
check("T8 promo_builder module has no app attr", hasattr(pb, "app"), False)


# --- Test 9: deterministic SEO keywords -----------------------------------------
kw_none = app_mod.shortform_seo_keywords(ABBR, CHAPTER, None)
check("T9 pure/total without agent copy", len(kw_none) > 0, True)
check("T9 order-stable", app_mod.shortform_seo_keywords(ABBR, CHAPTER, None), kw_none)
check("T9 includes novel", any("Eternal Nexus" == k for k in kw_none), True)
check("T9 respects limit", len(app_mod.shortform_seo_keywords(ABBR, CHAPTER, None, limit=4)), 4)

kw_agent = app_mod.shortform_seo_keywords(ABBR, CHAPTER, AGENT_COPY, limit=40)
check("T9 agent content_angle merged", "system betrayal" in kw_agent, True)
check("T9 agent audience merged", "progression fantasy readers" in kw_agent, True)
# Novel/chapter keywords must come first: the agent only appends.
check("T9 novel keyword precedes agent signal",
      kw_agent.index("Eternal Nexus") < kw_agent.index("system betrayal"), True)
# Case-insensitive dedupe.
dupe = app_mod.shortform_seo_keywords(
    ABBR, CHAPTER, {"content_angle": "ETERNAL NEXUS", "intended_audience": ""}, limit=40
)
check("T9 dedupes case-insensitively",
      sum(1 for k in dupe if k.lower() == "eternal nexus"), 1)


# --- Test 10: release state derives from Python state, never agent copy ---------
# An agent that lies about release state must not change the destination copy.
LYING_COPY = dict(AGENT_COPY)
LYING_COPY["caption"] = "This chapter is live on Royal Road right now, go read it!"
LYING_COPY["hook"] = "Live on Royal Road!"

for _plat in ("instagram_reel", "youtube_short"):
    _built = app_mod.build_reel_short_copy(LYING_COPY, NOVEL, "999", None, platform=_plat)
    _source = "youtube-shorts" if _plat == "youtube_short" else "instagram-reel"
    _expected = app_mod.short_destination_copy(ABBR, "999", source=_source)
    # The release/destination line is Python-owned: it must be one of the state-derived
    # options, independent of what the agent claimed.
    check(
        f"T10 {_plat} destination hook is python-owned",
        any(opt in _built["caption"] for opt in (
            "This chapter is live now, with more waiting when you are ready.",
            "Read the public chapter, then jump ahead if the cliffhanger catches you.",
            "The chapter is public now. Follow the trail before the next update lands.",
            "Get the next chapters first on Patreon, or catch up free on the public chapters.",
            "Read ahead now or start from the public chapters when you are ready.",
            "The next turn is already waiting for early readers.",
        )),
        True,
    )

# The Python-owned hashtags/CTA block must survive regardless of agent content.
_lie_reel = app_mod.build_reel_short_copy(LYING_COPY, NOVEL, CHAPTER, None, platform="instagram_reel")
check("T10 python hashtags present", "#AzureInkblade" in _lie_reel["caption"], True)
check("T10 python link-in-bio CTA present", "link in bio" in _lie_reel["caption"].lower(), True)


# --- Test 11: Shorts title from LLM hook is URL-sanitized (W4) --------------------
_LIE_TITLE_COPY = dict(AGENT_COPY)
_LIE_TITLE_COPY["hook"] = "Patreon early access at patreon.com/foo"
_short_title = app_mod.build_reel_short_copy(_LIE_TITLE_COPY, NOVEL, CHAPTER, None, platform="youtube_short")
check("T11 shorts title has no leaked URL", "patreon.com/foo" in _short_title["title"], False)
check("T11 shorts title still derived", "Patreon early access" in _short_title["title"], True)
check("T11 shorts title no link-in-bio CTA", "link in bio" in _short_title["title"].lower(), False)
check("T11 shorts title within 90 chars", len(_short_title["title"]) <= 90, True)


# --- Test 12: Reel uses the shared SEO merge (S5/S6) -----------------------------
# EN's 12-keyword cap is already full of novel/chapter tags, so the agent's
# angle/audience signal is only merged when there is room; assert the shared merge ran
# (Reel caption carries a SEO-derived tag via _merge_seo_hashtags) and the profile
# hashtags are preserved. The merge mechanism itself is asserted directly in T16.
_reel_seo = app_mod.build_reel_short_copy(AGENT_COPY, NOVEL, CHAPTER, None, platform="instagram_reel")
check("T12 reel keeps profile hashtags", "#AzureInkblade" in _reel_seo["caption"], True)
check("T12 reel merges SEO tags (novel tag present)", "#EternalNexus" in _reel_seo["caption"], True)
# When no seo_context is passed, the builder computes keywords from agent_copy too,
# so the agent's content_angle/intended_audience signal merges in (proving the shared
# merge includes the creative signal, not just the novel/chapter set).
_reel_seo2 = app_mod.build_reel_short_copy(
    {"caption": "c", "content_angle": "soul forging", "intended_audience": "progression fans"},
    "Hundredfold Path", "3", None, platform="instagram_reel",
)
check("T12 reel merges agent signal from copy", "SoulForging" in _reel_seo2["caption"], True)


# --- Test 13: memo revision keying + memo-hit flag (W2/W3) -----------------------
import tools.agent_post_writer as _apw13

_run13 = {"id": None}
_CALLS13 = []


class _Res13:
    def __init__(self, rid):
        self.copy = dict(AGENT_COPY)
        self.run_id = rid


def _gen13(abbr, title, chapter, hook, material, **kw):
    _CALLS13.append((abbr, chapter, str((material or {}).get("text") or "")[:8]))
    _run13["id"] = f"run-rev-{len(_CALLS13)}"
    return _Res13(_run13["id"])


_orig_gen13 = _apw13.generate_post_result
_orig_meta13 = _apw13.agent_result_metadata
_apw13.generate_post_result = _gen13
_apw13.agent_result_metadata = lambda r: {"_agent_run_id": r.run_id, "_agent_source": "hermes_agent", "_agent_used": False}
app_mod._AGENT_COPY_MEMO.clear()
try:
    # Same chapter, different body -> different memo key, must re-run Hermes.
    c1_m, c1_meta = app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, CHAPTER, "h", {"text": "alpha body"})
    c2_m, c2_meta = app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, CHAPTER, "h", {"text": "beta body completely different"})
    check("T13 revision change re-invokes agent", len(_CALLS13), 2)
    check("T13 first call not a memo hit", c1_meta.get("_agent_memo_hit"), False)
    check("T13 second call not a memo hit", c2_meta.get("_agent_memo_hit"), False)
    # Same chapter + same body -> memo hit on the second call.
    c3_m, c3_meta = app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, CHAPTER, "h", {"text": "alpha body"})
    check("T13 same revision is a memo hit", c3_meta.get("_agent_memo_hit"), True)
    check("T13 memo hit shares first run_id", c3_meta.get("_agent_run_id"), "run-rev-1")
finally:
    _apw13.generate_post_result = _orig_gen13
    _apw13.agent_result_metadata = _orig_meta13
    app_mod._AGENT_COPY_MEMO.clear()


# --- Test 14: memo-hit skips provenance write (W3) -------------------------------
_RECORDED14 = []


class _FakeDB14:
    @staticmethod
    def insert_generated_social_posts(root, run_id, rows):
        _RECORDED14.append((run_id, list(rows)))


_orig_db14 = app_mod.automation_db
app_mod.automation_db = _FakeDB14
import tools.agent_post_writer as _apw14

_CALLS14 = []


class _Res14:
    copy = dict(AGENT_COPY)
    run_id = "run-14"


def _gen14(abbr, title, chapter, hook, material, **kw):
    _CALLS14.append(1)
    return _Res14()


_orig_gen14 = _apw14.generate_post_result
_orig_meta14 = _apw14.agent_result_metadata
_apw14.generate_post_result = _gen14
_apw14.agent_result_metadata = lambda r: {"_agent_run_id": r.run_id, "_agent_source": "hermes_agent", "_agent_used": False}
app_mod._AGENT_COPY_MEMO.clear()
try:
    # First build records provenance; second build in the TTL hits the memo and must NOT
    # (the guard at the call site skips the write on a memo hit, preserving the audit trail).
    for _ in range(2):
        _m = app_mod.resolve_agent_post_copy_cached(ABBR, TITLE, CHAPTER, "h", {"text": "x"})[1]
        if not _m.get("_agent_memo_hit"):
            app_mod.record_generated_shortform_posts(_m, [("instagram_reel", "cap", True)])
    check("T14 only first build records provenance", len(_RECORDED14), 1)
finally:
    _apw14.generate_post_result = _orig_gen14
    _apw14.agent_result_metadata = _orig_meta14
    app_mod.automation_db = _orig_db14
    app_mod._AGENT_COPY_MEMO.clear()


# --- Test 15: reuse branch clears stale provenance + seo_keywords (W1) -----------
_meta15: dict = {"_agent_run_id": "run-15", "_agent_used": True, "_agent_source": "hermes_agent"}
# Seed a reused metadata.json simulating a prior agent-enabled build that is now stale.
_PACK15 = TMP / "pack15"
_PACK15.mkdir(parents=True, exist_ok=True)
(_PACK15 / "caption.txt").write_text("c\n", encoding="utf-8")
(_PACK15 / "instagram-reel-caption.txt").write_text("r\n", encoding="utf-8")
(_PACK15 / "youtube-shorts-description.txt").write_text("s\n", encoding="utf-8")
(_PACK15 / "metadata.json").write_text(
    json.dumps({
        "abbr": ABBR, "chapter": CHAPTER, "novel": NOVEL,
        "_agent_run_id": "old-run", "_agent_used": True, "_agent_source": "hermes_agent",
        "seo_keywords": ["stale", "keywords"],
    }), encoding="utf-8",
)

_COLLAB15 = dict(COLLAB)
# Point stable_chapter_folder at our seeded reuse folder.
def _folder15(*a, **k):
    return _PACK15
_COLLAB15["stable_chapter_folder"] = _folder15
# reusable_pack_result loads metadata.json when sidecar files exist.
_meta15b: dict = {}

# Flag-off rebuild: agent_meta {} -> no agent copy -> clean metadata, no _agent_*.
pack15 = pb.make_tiktok_pack(ABBR, CHAPTER, force_new_images=False, chapter_text="body",
                             agent_copy=None, agent_meta=_meta15b, collaborators=_COLLAB15)
_m15 = json.loads((_PACK15 / "metadata.json").read_text(encoding="utf-8"))
check("T15 reuse drops stale _agent_run_id", "_agent_run_id" in _m15, False)
check("T15 reuse drops stale _agent_source", "_agent_source" in _m15, False)
check("T15 reuse clears stale seo_keywords", _m15.get("seo_keywords"), [])
check("T15 reuse writes generic copy", GENERIC_HOOK in pack15["youtube_shorts_description"], True)
check("T15 reuse _agent_used truthful False", _m15.get("_agent_used"), False)


# --- Test 16: SEO merge helper is shared and dedupes (S6) ------------------------
_base = "#EternalNexus #BookTok"
_merged = app_mod._merge_seo_hashtags(_base, ["system betrayal", "Eternal Nexus", "progression fantasy readers"], limit=6)
check("T16 merged keeps base tags", "#EternalNexus" in _merged and "#BookTok" in _merged, True)
check("T16 merged dedupes novel already present", "EternalNexus #EternalNexus" in _merged, False)
check("T16 merged adds new seo tag", "SystemBetrayal" in _merged, True)


# --- cleanup / report ------------------------------------------------------------
shutil.rmtree(TMP, ignore_errors=True)

if FAILS:
    print(f"FAILED ({len(FAILS)}):")
    for item in FAILS:
        print(" -", item)
    sys.exit(1)
print("All agent-aware short-form SEO acceptance tests passed.")
