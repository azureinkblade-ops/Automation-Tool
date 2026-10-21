# -*- coding: utf-8 -*-
"""AIVSB_IDENTITY_PATH_REMEDIATION_20261004: AIVSB reasoning ON + identity preservation ON.

Drives the real production chain app.generate_tiktok_images -> make_chapter_image_prompts ->
compose_aivsb_scene_prompt (real Inkblade AIVSB reasoning package) -> V2 generate_promo_image_v2 /
V1 create_openai_image -> tools.identity_preservation.enforce_identity_acceptance, with
ENABLE_IDENTITY_PRESERVATION=1 and AIVSB_REASONING_ENABLED=on set per-test via monkeypatch only.

Every provider is mocked (V2 materializer, openai_request; local SD / google / stock / browser /
banked raise), archive / provenance / rotation / trace / promo-master sinks are stubbed, AIVSB
semantic retrieval (embedding boundary) returns [], asset + observability output live in tmp_path,
and socket connect + subprocess spawning are blocked and asserted to be 0 for every test.

Naming forms: FULL (production NOVEL_NAMES, e.g. "Hundredfold Path") and SHORT (NOVEL_NAMES mapped
abbr->abbr, e.g. "HP"). SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 (Part A) added one canonical
novel-id seam (tools.novel_id) in make_chapter_image_prompts, so FULL now composes through AIVSB
exactly like SHORT (previously the composer rejected the full name and the legacy prompt was used).
Both must be safe; the identity gate outcome for FULL is now the same (stricter) one as SHORT.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from tools import identity_preservation as ip  # noqa: E402

AIVSB_REASONING = ROOT.parent / "Inkblade Author Studio" / "scripts" / "aivsb" / "reasoning"
pytestmark = pytest.mark.skipif(not AIVSB_REASONING.exists(),
                                reason=f"AIVSB reasoning package not present at {AIVSB_REASONING}")

NOVELS = ("EN", "HA", "HP", "SF")
EXPECTED_KEY = {"EN": "kael_veyra", "HA": "kai", "HP": "liang", "SF": "jarek"}
TEXTS = {
    "EN": ("Kael Veyra raised his Soulblade in the neon city.", "Kael Veyra logged in; he raised his Soulblade as glyphs flared."),
    "HA": ("Kai stood in the rain alley.", "Kai stood in the rain alley; he looked up at the System HUD."),
    "HP": ("Liang entered the ruined sect hall.", "Liang entered the ruined sect hall and sensed qi in the morning mist."),
    "SF": ("Jarek dragged iron chains through the forge.", "Jarek dragged iron chains through the forge undercity; his gold eyes burned."),
}
SCENERY_TEXT = ("An empty misty mountain valley at dawn.", "An empty misty mountain valley at dawn, no people, pines and a river.")
MALFORMED = {"EN": "kaael", "HA": "kia", "HP": "liagn", "SF": "jarekk"}
FAKE = b"\x89PNG\r\n\x1a\n" + b"AIVSB-IDENTITY-PATH-TEST" * 64


class _Blocked(RuntimeError):
    pass


@pytest.fixture
def env(monkeypatch, tmp_path):
    calls = {"net": 0, "subprocess": 0, "materializer": 0, "openai": 0, "compose": 0, "composed": 0, "sinks": {}}
    log = tmp_path / "identity_observability.jsonl"
    for k in ("VISUAL_DIRECTOR_ENABLED", "STYLE_REF_EXPERIMENTAL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ENABLE_IDENTITY_PRESERVATION", "1")
    monkeypatch.setenv("AIVSB_REASONING_ENABLED", "on")
    monkeypatch.setenv("AIVSB_SEMANTIC_RETRIEVAL_ENABLED", "on")
    monkeypatch.setenv("AIVSB_TELEMETRY_ENABLED", "false")
    monkeypatch.setenv("AIVSB_TELEMETRY_PATH", str(tmp_path / "aivsb_telemetry.jsonl"))
    monkeypatch.setenv("IDENTITY_OBSERVABILITY_LOG", str(log))
    monkeypatch.setenv("TIKTOK_ASSET_DIR", str(tmp_path / "tiktok"))

    def _net(*a, **k):
        calls["net"] += 1
        raise _Blocked("network blocked in test")

    def _popen(self, *a, **k):
        calls["subprocess"] += 1
        raise _Blocked("subprocess blocked in test")

    monkeypatch.setattr(socket.socket, "connect", _net)
    monkeypatch.setattr(socket.socket, "connect_ex", _net)
    monkeypatch.setattr(socket, "create_connection", _net)
    monkeypatch.setattr(subprocess.Popen, "__init__", _popen)

    seq = [0]

    def fake_bytes():
        seq[0] += 1
        return FAKE + str(seq[0]).encode()

    def materializer(profile, resolution, target):
        calls["materializer"] += 1
        return fake_bytes()

    def openai_request(path, payload):
        calls["openai"] += 1
        return {"data": [{"b64_json": base64.b64encode(fake_bytes()).decode()}]}

    def provider_stub(name):
        def f(*a, **k):
            raise RuntimeError(f"provider {name} stubbed in test")
        return f

    def sink(name, ret=None):
        def f(*a, **k):
            calls["sinks"][name] = calls["sinks"].get(name, 0) + 1
            return ret() if callable(ret) else ret
        return f

    monkeypatch.setattr(app, "TIKTOK_ASSET_DIR", tmp_path / "tiktok")
    monkeypatch.setattr(app, "V2_PROMO_MATERIALIZER", materializer)
    monkeypatch.setattr(app, "openai_request", openai_request)
    for n in ("create_google_ai_image", "create_local_stable_diffusion_image", "create_pexels_image",
              "create_pixabay_image", "start_browser_image_assist", "choose_banked_image"):
        monkeypatch.setattr(app, n, provider_stub(n))
    monkeypatch.setattr(app, "archive_generated_promo_image", sink("archive", ""))
    monkeypatch.setattr(app, "mark_image_used", sink("mark_image_used", dict))
    monkeypatch.setattr(app, "save_promo_rotation_state", sink("save_promo_rotation_state"))
    monkeypatch.setattr(app, "write_image_provider_trace", sink("write_image_provider_trace"))
    monkeypatch.setattr(app, "image_feedback_prompt_guidance", lambda *a, **k: "")
    monkeypatch.setattr(app, "load_automation_strategy", lambda *a, **k: {})
    monkeypatch.setattr(app, "choose_rotating_daily_promo_image", sink("choose_rotating_daily_promo_image", None))
    monkeypatch.setattr(app, "short_chapter_visual_moments", lambda *a, **k: [])
    monkeypatch.setattr(app, "EXTERNAL_AI_ENABLED", False)
    import tools.image_pipeline_v2_provenance as prov
    import tools.promo_master_production as pmp
    monkeypatch.setattr(prov, "persist_v2_provenance", sink("persist_v2_provenance"))
    monkeypatch.setattr(prov, "persist_v2_failure_provenance", sink("persist_v2_failure_provenance"))

    class _PM:
        status = "test_stub"; enabled = False; activation_source = None; base_path = ""; base_sha256 = ""
        master_path = ""; master_sha256 = ""; error = ""

    monkeypatch.setattr(pmp, "apply_promo_master", sink("apply_promo_master", _PM))
    for p in (AIVSB_REASONING, AIVSB_REASONING.parent / "retrieval", AIVSB_REASONING.parent):
        monkeypatch.syspath_prepend(str(p))
    import bible_context
    monkeypatch.setattr(bible_context.BibleContext, "semantic_passages", lambda self, *a, **k: [])
    v2 = {"on": True}
    monkeypatch.setattr(app, "_v2_profile_enabled",
                        lambda profile, enabled_override=None: (profile == "main_posts") if v2["on"] else False)
    orig_compose = app.compose_aivsb_scene_prompt

    def spy_compose(*a, **k):
        calls["compose"] += 1
        r = orig_compose(*a, **k)
        if r:
            calls["composed"] += 1
        return r

    monkeypatch.setattr(app, "compose_aivsb_scene_prompt", spy_compose)
    # fresh, per-test AIVSB evidence registry (in-process only)
    monkeypatch.setattr(ip, "_AIVSB_COMPOSED_REGISTRY", {})
    monkeypatch.setattr(ip, "_AIVSB_COMPOSED_ORDER", [])

    class E:
        pass

    e = E()
    e.calls, e.log, e.v2, e.monkeypatch = calls, log, v2, monkeypatch

    def naming(form):
        if form == "SHORT":
            for ab in NOVELS:
                monkeypatch.setitem(app.NOVEL_NAMES, ab, ab)
    e.naming = naming

    def records():
        if not log.exists():
            return []
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    e.records = records
    yield e
    assert calls["net"] == 0, "network connect attempted"
    assert calls["subprocess"] == 0, "subprocess spawn attempted"


def _variant(ab, form):
    # SF: the composed prompt hits the pre-existing V2 Studio Bible canon error
    # (UNKNOWN_CHARACTER, also with the flag OFF) before generation, so the identity gate is
    # exercised through the V1 external primitive (openai_request mocked). R2 Part A: SF FULL now
    # composes like SF SHORT, so both forms use the V1 external primitive.
    return "V1EXT" if ab == "SF" else "V2"


def _run(e, ab, text, *, variant="V2", ctx=None, intent=None):
    e.v2["on"] = variant == "V2"
    e.monkeypatch.setattr(app, "EXTERNAL_AI_ENABLED", variant == "V1EXT")
    out = {"raised": None}
    import contextlib
    with contextlib.ExitStack() as st:
        if ctx is not None:
            st.enter_context(ip.identity_production_context(ctx))
        if intent is not None:
            st.enter_context(ip.image_intent_scope(intent))
        try:
            out["result"] = app.generate_tiktok_images(ab, "1", "", force_new_images=True, chapter_text=text[1],
                                                       chapter_title=text[0], style="main-posts")
        except Exception as exc:  # noqa: BLE001
            out["raised"] = exc
    return out


def _assert_no_unsafe_accept(recs):
    for r in recs:
        if r.get("AUTO_ACCEPT_ALLOWED") == "YES":
            # Only the documented procedural emergency art (non-canon silhouette) may auto-accept.
            assert r.get("IMAGE_INTENT_CLASS") == "NON_CANON_SILHOUETTE", r
            assert str(r.get("PATH_ID", "")).startswith("PROCEDURAL"), r
        assert r.get("SCENERY_BYPASS_APPLIED") != "YES", r
        assert ip.validate_observability_record(r) == [], r


def _gate_records(recs):
    return [r for r in recs if not str(r.get("PATH_ID", "")).startswith("PROCEDURAL")]


# ---------------------------------------------------------------------------------------------
# (a) governed binding, every novel, both naming forms
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("form", ["FULL", "SHORT"])
@pytest.mark.parametrize("ab", NOVELS)
def test_aivsb_governed_binding(env, ab, form):
    env.naming(form)
    out = _run(env, ab, TEXTS[ab], variant=_variant(ab, form))
    recs = env.records()
    gate = _gate_records(recs)
    assert gate, (out["raised"], recs)
    _assert_no_unsafe_accept(recs)
    for r in gate:
        assert r["IMAGE_INTENT_CLASS"] == "GOVERNED_CHARACTER_DEPICTION"
        assert r["CHARACTER"] == EXPECTED_KEY[ab]
        assert r["GOVERNED_CONTEXT_BINDING_RESULT"] == "BOUND"
        assert r["VERIFIER_DECISION"] == "REJECT_REVIEW"
        assert r["IDENTITY_GATE_REQUIRED"] == "YES" and r["HUMAN_REVIEW_REQUIRED"] == "YES"
        assert r["AUTO_ACCEPT_ALLOWED"] == "NO"
    if form == "SHORT":
        assert env.calls["composed"] >= 1, "AIVSB did not compose for the short code"
        ev = gate[0]["IMAGE_INTENT_EVIDENCE"]
        assert "AIVSB_COMPOSED_PROMPT=REGISTRY" in ev
        assert f"AIVSB_SOURCE_CHAPTER_GOVERNED_NAME={EXPECTED_KEY[ab]}" in ev
    if _variant(ab, form) == "V2":
        assert ip.is_identity_block(out["raised"]), out["raised"]
        assert "persist_v2_provenance" not in env.calls["sinks"]


# ---------------------------------------------------------------------------------------------
# (b) scenery: caller labels never bypass governed chapter evidence on the AIVSB path
# ---------------------------------------------------------------------------------------------
SCENERY_LABELS = {
    "scene_subject_scenery": dict(scene_subject="scenery"),
    "background_only": dict(background_only=True),
    "asset_role_scenery": dict(asset_role="scenery"),
}


@pytest.mark.parametrize("label", sorted(SCENERY_LABELS))
@pytest.mark.parametrize("form", ["FULL", "SHORT"])
@pytest.mark.parametrize("ab", NOVELS)
def test_aivsb_scenery_label_cannot_override_governed_text(env, ab, form, label):
    env.naming(form)
    intent = ip.ImageIntentRequest(origin="test.upstream", **SCENERY_LABELS[label])
    out = _run(env, ab, TEXTS[ab], variant=_variant(ab, form), intent=intent)
    recs = env.records()
    gate = _gate_records(recs)
    assert gate, (out["raised"], recs)
    _assert_no_unsafe_accept(recs)
    for r in gate:
        assert r["IMAGE_INTENT_CLASS"] == "GOVERNED_CHARACTER_DEPICTION", r["IMAGE_INTENT_EVIDENCE"]
        assert r["GOVERNED_CHARACTER_DEPICTION"] == "YES"
        assert r["VERIFIER_DECISION"] == "REJECT_REVIEW"
        assert r["HUMAN_REVIEW_REQUIRED"] == "YES" and r["AUTO_ACCEPT_ALLOWED"] == "NO"
        assert r["CHARACTER"] == EXPECTED_KEY[ab]


@pytest.mark.parametrize("form", ["FULL", "SHORT"])
def test_aivsb_liang_spoof_routes_to_review(env, form):
    """Rerun-3 probe B3: upstream scenery label + Hundredfold Path chapter text naming Liang."""
    env.naming(form)
    intent = ip.ImageIntentRequest(scene_subject="scenery", origin="probe.upstream")
    out = _run(env, "HP", TEXTS["HP"], variant="V2", intent=intent)
    assert ip.is_identity_block(out["raised"]), out["raised"]
    recs = env.records()
    assert len(recs) == 1
    r = recs[0]
    assert r["IMAGE_INTENT_CLASS"] == "GOVERNED_CHARACTER_DEPICTION"
    assert r["VERIFIER_DECISION"] == "REJECT_REVIEW"
    assert r["CHARACTER"] == "liang"
    assert r["SCENERY_BYPASS_APPLIED"] == "NO"
    assert r["IDENTITY_GATE_REQUIRED"] == "YES" and r["AUTO_ACCEPT_ALLOWED"] == "NO"
    assert env.calls["sinks"].get("archive", 0) == 0
    if form == "SHORT":
        assert env.calls["composed"] >= 1
        assert "AIVSB_SOURCE_CHAPTER_GOVERNED_NAME=liang" in r["IMAGE_INTENT_EVIDENCE"]


@pytest.mark.parametrize("ab", ("EN", "HA", "HP"))
def test_aivsb_composed_scenery_is_potentially_governed(env, ab):
    """Documented choice: structured scenery is not expressible on the AIVSB path, so even genuine
    scenery text with an upstream scenery label routes to review once AIVSB composed the prompt."""
    env.naming("SHORT")
    intent = ip.ImageIntentRequest(scene_subject="scenery", origin="test.upstream")
    out = _run(env, ab, SCENERY_TEXT, variant="V2", intent=intent)
    assert env.calls["composed"] >= 1
    assert ip.is_identity_block(out["raised"]), out["raised"]
    recs = env.records()
    assert recs
    _assert_no_unsafe_accept(recs)
    r = recs[0]
    assert r["IMAGE_INTENT_CLASS"] == "GOVERNED_CHARACTER_DEPICTION"
    assert r["IMAGE_INTENT_SOURCE"] == "FORCED_GOVERNED_SIGNAL"
    assert "AIVSB_COMPOSED_PROMPT_POTENTIALLY_GOVERNED=REGISTRY" in r["IMAGE_INTENT_EVIDENCE"]
    assert r["HUMAN_REVIEW_REQUIRED"] == "YES" and r["AUTO_ACCEPT_ALLOWED"] == "NO"


@pytest.mark.parametrize("ab", ("EN", "HA", "HP"))
def test_full_name_scenery_composes_and_routes_to_review_r2(env, ab):
    """R2 Part A (replaces test_full_name_legacy_scenery_bypass_unchanged): full novel names are
    normalized by the canonical novel-id seam, AIVSB composes, and -- per the documented choice in
    test_aivsb_composed_scenery_is_potentially_governed -- AIVSB-composed scenery is potentially
    governed and routes to review. The old FULL-only scenery bypass no longer applies (stricter)."""
    env.naming("FULL")
    intent = ip.ImageIntentRequest(scene_subject="scenery", origin="test.upstream")
    out = _run(env, ab, SCENERY_TEXT, variant="V2", intent=intent)
    assert env.calls["composed"] >= 1
    assert ip.is_identity_block(out["raised"]), out["raised"]
    recs = env.records()
    assert recs
    _assert_no_unsafe_accept(recs)
    r = recs[0]
    assert r["IMAGE_INTENT_CLASS"] == "GOVERNED_CHARACTER_DEPICTION"
    assert r["IMAGE_INTENT_SOURCE"] == "FORCED_GOVERNED_SIGNAL"
    assert "AIVSB_COMPOSED_PROMPT_POTENTIALLY_GOVERNED=REGISTRY" in r["IMAGE_INTENT_EVIDENCE"]
    assert r["SCENERY_BYPASS_APPLIED"] != "YES"
    assert r["HUMAN_REVIEW_REQUIRED"] == "YES" and r["AUTO_ACCEPT_ALLOWED"] == "NO"


@pytest.mark.parametrize("form", ["FULL", "SHORT"])
@pytest.mark.parametrize("ab", NOVELS)
def test_aivsb_scenery_text_without_structure_reviews(env, ab, form):
    env.naming(form)
    out = _run(env, ab, SCENERY_TEXT, variant=_variant(ab, form))
    recs = env.records()
    # R2 Part A: SF FULL now composes like SF SHORT and runs through the V1 external primitive
    # (see _variant); the former SF-FULL V2 canon-error early return no longer applies.
    gate = _gate_records(recs)
    assert gate
    _assert_no_unsafe_accept(recs)
    for r in gate:
        assert r["IMAGE_INTENT_CLASS"] == "GOVERNED_CHARACTER_DEPICTION"
        assert r["AUTO_ACCEPT_ALLOWED"] == "NO"


# ---------------------------------------------------------------------------------------------
# (c) malformed / sentinel / cross-novel IDs fail closed, both naming forms
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("carrier", ["context_character_id", "intent_depicted"])
@pytest.mark.parametrize("form", ["FULL", "SHORT"])
@pytest.mark.parametrize("ab", NOVELS)
def test_aivsb_malformed_id_fail_closed(env, ab, form, carrier):
    env.naming(form)
    bad = MALFORMED[ab]
    kw = {}
    if carrier == "context_character_id":
        kw["ctx"] = ip.build_identity_context(abbr=ab, character_id=bad, source="test.upstream")
    else:
        kw["intent"] = ip.ImageIntentRequest(depicted_characters=(bad,), origin="test.upstream")
    out = _run(env, ab, TEXTS[ab], variant=_variant(ab, form), **kw)
    recs = env.records()
    gate = _gate_records(recs)
    assert gate, (out["raised"], recs)
    _assert_no_unsafe_accept(recs)
    for r in gate:
        assert r["VERIFIER_DECISION"] == "FAIL_CLOSED", r
        assert r["GOVERNED_CONTEXT_BINDING_RESULT"] == "FAILED"
        assert str(r["BINDING_FAILURE_REASON"]).startswith("GOVERNED_CONTEXT_BINDING_FAILED")
        assert r["AUTO_ACCEPT_ALLOWED"] == "NO"
        assert r["CHARACTER"] == ""  # no fuzzy correction


@pytest.mark.parametrize("form", ["FULL", "SHORT"])
@pytest.mark.parametrize("case", ["sentinel_scenery_HP", "sentinel_none_EN", "cross_novel_EN_jarek", "cross_novel_HP_kai"])
def test_aivsb_sentinel_and_cross_novel_fail_closed(env, form, case):
    env.naming(form)
    ab, cid = {"sentinel_scenery_HP": ("HP", "scenery"), "sentinel_none_EN": ("EN", "none"),
               "cross_novel_EN_jarek": ("EN", "jarek"), "cross_novel_HP_kai": ("HP", "kai")}[case]
    ctx = ip.build_identity_context(abbr=ab, character_id=cid, source="test.upstream")
    out = _run(env, ab, TEXTS[ab], variant="V2", ctx=ctx)
    assert ip.is_identity_block(out["raised"]), out["raised"]
    recs = env.records()
    assert recs
    for r in recs:
        assert r["VERIFIER_DECISION"] == "FAIL_CLOSED" and r["AUTO_ACCEPT_ALLOWED"] == "NO"
        assert r["GOVERNED_CONTEXT_BINDING_RESULT"] == "FAILED"


# ---------------------------------------------------------------------------------------------
# carrier / gate unit behaviour
# ---------------------------------------------------------------------------------------------
def test_flag_off_registers_nothing_and_gate_bypasses(env, tmp_path):
    env.monkeypatch.delenv("ENABLE_IDENTITY_PRESERVATION", raising=False)
    env.naming("SHORT")
    prompts = app.make_chapter_image_prompts(TEXTS["HP"][0], TEXTS["HP"][1], [TEXTS["HP"][0]], "HP")
    assert env.calls["composed"] == 3
    assert "Liang" not in " ".join(prompts)
    assert ip._AIVSB_COMPOSED_REGISTRY == {}
    img = tmp_path / "x.png"
    img.write_bytes(FAKE)
    res = ip.enforce_identity_acceptance(img, path_id="test", prompt=prompts[0])
    assert res.decision == "BYPASS"
    assert not env.log.exists()


def test_flag_on_registers_source_names_before_strip(env):
    env.naming("SHORT")
    prompts = app.make_chapter_image_prompts(TEXTS["HP"][0], TEXTS["HP"][1], [TEXTS["HP"][0]], "HP")
    assert env.calls["composed"] == 3 and "Liang" not in " ".join(prompts)
    ev = ip.lookup_aivsb_composed_evidence("Vertical TikTok promo image 1 for HP chapter 1. " + prompts[0] + ". Cinematic")
    assert ev is not None and ev.matched_by == "REGISTRY"
    assert ev.source_governed_names == ("liang",) and ev.novel_id == "hp"


def test_registration_failure_falls_back_to_legacy_prompt(env):
    env.naming("SHORT")

    def boom(*a, **k):
        raise RuntimeError("registry unavailable")
    env.monkeypatch.setattr(ip, "register_aivsb_composed_prompt", boom)
    prompts = app.make_chapter_image_prompts(TEXTS["HP"][0], TEXTS["HP"][1], [TEXTS["HP"][0]], "HP")
    assert len(prompts) == 3
    assert all("Story context:" in p and "Liang" in p for p in prompts)


def test_signature_backstop_for_unregistered_composed_prompt():
    composed = ("hp, expressing unspecified, medium shot with 35mm lens, center_grid, "
                "soft_daylight lighting (calm), world: fixture grey teal")
    ev = ip.lookup_aivsb_composed_evidence("Vertical TikTok promo image 1 for HP chapter 1. " + composed)
    assert ev is not None and ev.matched_by == "SIGNATURE"
    legacy = ("Vertical 9:16 cinematic fantasy web novel cover art, no text or typography. Story context: "
              "Hundredfold Path, Liang entered the ruined sect hall. Dramatic lighting, wide shot.")
    assert ip.lookup_aivsb_composed_evidence(legacy) is None
    assert ip.lookup_aivsb_composed_evidence("") is None


def test_resolve_intent_aivsb_evidence_is_upgrade_only():
    ev = ip.AivsbComposedEvidence("hp", ("liang",), "test", "REGISTRY")
    scen = ip.ImageIntentRequest(scene_subject="scenery", origin="test")
    base = ip.resolve_image_intent(scen)
    assert base.intent_class == "SCENERY_ONLY"
    forced = ip.resolve_image_intent(scen, aivsb_evidence=ev)
    assert forced.intent_class == "GOVERNED_CHARACTER_DEPICTION" and forced.forced
    assert "AIVSB_SOURCE_CHAPTER_GOVERNED_NAME=liang" in forced.evidence
    no_names = ip.resolve_image_intent(ip.ImageIntentRequest(background_only=True),
                                       aivsb_evidence=ip.AivsbComposedEvidence("", (), "sig", "SIGNATURE"))
    assert no_names.intent_class == "GOVERNED_CHARACTER_DEPICTION"
    assert "AIVSB_COMPOSED_PROMPT_POTENTIALLY_GOVERNED=SIGNATURE" in no_names.evidence
    gov = ip.resolve_image_intent(ip.ImageIntentRequest(depicted_characters=("liang",)), aivsb_evidence=ev)
    assert gov.intent_class == "GOVERNED_CHARACTER_DEPICTION"
