# -*- coding: utf-8 -*-
"""IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929 - Part N coverage tests (32).

Drives the REAL app.py production callers / fallback call sites and the identity module.
Every generator / network / publish side effect is mocked: GPU_GENERATIONS=0.
ENABLE_IDENTITY_PRESERVATION is set only inside each test (per-process env) and restored.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import visual_director as vd  # noqa: E402
from tools import identity_preservation as ip  # noqa: E402

FLAG = "ENABLE_IDENTITY_PRESERVATION"
FAKE = b"\x89PNG\r\n\x1a\n" + b"FAKE-GENERATED-IMAGE" * 200
OLD = b"\x89PNG\r\n\x1a\n" + b"OLD-HISTORICAL-IMAGE-DEPICTS-GOVERNED-CHARACTER" * 100
STOCK = b"\x89PNG\r\n\x1a\n" + b"STOCK-PHOTO-PERSON" * 300
NAMELESS = {
    "kai": ("HA", "Heavenly Ascension System",
            "a sickly thin nineteen-year-old with short hair and brown eyes looks up at a floating status window in a rainy alley"),
    "kael_veyra": ("EN", "Eternal Nexus",
                   "a lean young gamer with dark short hair steps through a glowing portal"),
    "liang": ("HP", "Hundredfold Path", "a reborn cultivator with a dark topknot meditates on a mountain terrace at dawn"),
    "jarek": ("SF", "Soul Forge Era", "a starving scavenger with wild unkempt hair and burning gold eyes crawls through an iron undercity"),
}


# Snapshot of app's real functions at collection time (before any other test module runs).
# Some older test modules replace app functions without restoring them in single-process
# suites; each test here re-pins the real functions for its own duration (mock.patch restores).
import types as _types  # noqa: E402
_APP_FUNCS = {k: v for k, v in vars(app).items() if isinstance(v, _types.FunctionType)}


def setUpModule():
    """Single-process suites: some older test modules leave stub modules (no __file__) in
    sys.modules (e.g. tools.image_pipeline_v2_profiles). Restore the real ones so these
    production-path tests exercise real code regardless of test ordering."""
    import importlib
    import tools as tools_pkg
    tools_pkg.__path__ = [str(ROOT / "tools")]
    for name in list(sys.modules):
        mod = sys.modules.get(name)
        if (name == "app_config" or name.startswith("tools.")) and mod is not None and not getattr(mod, "__file__", None):
            del sys.modules[name]
            try:
                importlib.import_module(name)
            except Exception:  # pragma: no cover - best effort
                pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@contextlib.contextmanager
def identity_flag(on: bool, log_path: Path):
    saved = {k: os.environ.get(k) for k in (FLAG, "IDENTITY_OBSERVABILITY_LOG", "STYLE_REF_EXPERIMENTAL", "AIVSB_REASONING_ENABLED")}
    os.environ.pop(FLAG, None)
    os.environ.pop("STYLE_REF_EXPERIMENTAL", None)
    # AIVSB_DURABLE_PROVENANCE_REMEDIATION_20261004: these suites qualify the NON-AIVSB rules; keep them
    # hermetic (the user env sets AIVSB on, which now makes provenance-less governed scenery review).
    os.environ["AIVSB_REASONING_ENABLED"] = "off"
    os.environ["IDENTITY_OBSERVABILITY_LOG"] = str(log_path)
    if on:
        os.environ[FLAG] = "1"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.log = self.tmp / "identity_observability.jsonl"
        self.calls = {"generate": 0, "mark_used": 0, "archive": 0, "publish": 0}
        arch = self.tmp / "arch"
        arch.mkdir()
        self.start([mock.patch.object(app, k, v) for k, v in _APP_FUNCS.items() if vars(app).get(k) is not v])

        def _pub(*a, **k):
            self.calls["publish"] += 1
            raise RuntimeError("TEST: publish blocked")

        self.start([
            mock.patch.object(app, "mark_image_used", side_effect=self._mark),
            mock.patch.object(app, "save_promo_rotation_state", return_value=None),
            mock.patch.object(app, "archive_generated_promo_image", side_effect=self._archive),
            mock.patch.object(app, "write_image_provider_trace", return_value=None),
            mock.patch.object(app, "generated_promo_images_dir", return_value=arch),
            mock.patch.object(app, "image_feedback_prompt_guidance", return_value=""),
            mock.patch.object(app, "auto_publish_generated_media", side_effect=_pub),
            mock.patch.object(app, "start_browser_image_assist", return_value=None),
            mock.patch.object(app, "record_recovery_event", return_value=None),
            mock.patch.object(app, "agent_posts_enabled", return_value=False),
            # Safety net (GPU_GENERATIONS=0, no network): every real provider is disabled by
            # default; individual tests layer explicit mocks on top.
            mock.patch.object(app, "local_stable_diffusion_status", return_value={"ready": False, "missing": ["test"]}),
            mock.patch.object(app, "openai_request", side_effect=RuntimeError("TEST: openai disabled")),
            mock.patch.object(app, "google_ai_configured", return_value=False),
            mock.patch.object(app, "google_ai_request", side_effect=RuntimeError("TEST: google disabled")),
            mock.patch.object(app, "create_pexels_image", side_effect=RuntimeError("TEST: pexels disabled")),
            mock.patch.object(app, "create_pixabay_image", side_effect=RuntimeError("TEST: pixabay disabled")),
            mock.patch.object(app, "load_automation_strategy",
                              return_value={"imageProviderPriority": ["local_stable_diffusion", "local_fallback"]}),
        ])

    def tearDown(self):
        self._td.cleanup()

    def start(self, patches):
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _mark(self, *a, **k):
        self.calls["mark_used"] += 1
        return {}

    def _archive(self, *a, **k):
        self.calls["archive"] += 1
        return None

    def local_sd(self, fail: bool = False):
        def fake_run(cmd, **kw):
            if fail:
                return mock.Mock(returncode=1, stdout="", stderr="TEST local SD provider failure")
            self.calls["generate"] += 1
            Path(cmd[cmd.index("--output") + 1]).write_bytes(FAKE)
            return mock.Mock(returncode=0, stdout="", stderr="")
        self.start([
            mock.patch.object(app, "local_stable_diffusion_status", return_value={"ready": True, "model": "fake-sdxl"}),
            mock.patch.object(app, "lora_track_for_prompt", return_value="main-posts"),
            mock.patch.object(app, "find_lora_weights_for_track", return_value=None),
            mock.patch.object(app, "HeavyJobLimiter", side_effect=lambda *a, **k: contextlib.nullcontext()),
            mock.patch.object(app.subprocess, "run", side_effect=fake_run),
        ])

    def openai(self):
        def fake_req(endpoint, payload):
            self.calls["generate"] += 1
            return {"data": [{"b64_json": base64.b64encode(FAKE).decode()}]}
        self.start([mock.patch.object(app, "EXTERNAL_AI_ENABLED", True),
                    mock.patch.object(app, "openai_request", side_effect=fake_req)])

    def strategy(self, order):
        self.start([mock.patch.object(app, "load_automation_strategy", return_value={"imageProviderPriority": list(order)})])

    def records(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def old_image(self, name="old.png", data=OLD) -> Path:
        p = self.tmp / "reuse" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def assert_governed_block(self, recs, character, *, fallback_class=None):
        self.assertTrue(recs, "identity gate must execute and emit a record")
        bound = [r for r in recs if r.get("CHARACTER") == character]
        self.assertTrue(bound, [(r.get("PATH_ID"), r.get("CHARACTER"), r.get("VERIFIER_DECISION")) for r in recs])
        for r in bound:
            self.assertIn(r["VERIFIER_DECISION"], ("REJECT_REVIEW", "FAIL_CLOSED"))
            self.assertEqual(r["AUTO_ACCEPT_ALLOWED"], "NO")
            self.assertEqual(r["IDENTITY_GATE_EXECUTED"], "YES")
            if fallback_class:
                self.assertEqual(r["FALLBACK_IMAGE_USED"], "YES")
                self.assertEqual(r["FALLBACK_ASSET_CLASS"], fallback_class)
                self.assertEqual(r["FALLBACK_IDENTITY_VERIFIED"], "NO")
        return bound


# ---------------------------------------------------------------------------
# ATTRIBUTION (1-6)
# ---------------------------------------------------------------------------
class TestAttribution(_Base):
    def test_01_governed_kai_context_name_removed_binds_kai(self):
        self.local_sd()
        abbr, novel, nameless = NAMELESS["kai"]
        self.assertNotRegex(nameless.lower(), r"\bkai\b|heavenly ascension")
        tgt = self.tmp / "social" / "ha.png"
        tgt.parent.mkdir()
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_fresh_social_image_from_caption(tgt, abbr=abbr, novel=novel, title="Chapter 1",
                                                           caption="He looked up.", visual_brief=nameless)
        self.assertTrue(ip.is_identity_block(cm.exception))
        r = self.assert_governed_block(self.records(), "kai")[0]
        self.assertIn(r["CHARACTER_BINDING_SOURCE"], ("STRUCTURED_NOVEL_ID", "STRUCTURED_NOVEL_ALIAS"))
        self.assertEqual(r["PROMPT_FALLBACK_USED"], "NO")
        self.assertFalse(tgt.exists())
        self.assertEqual(self.calls["archive"], 0)

    def test_02_governed_kael_context_title_removed_binds_kael(self):
        self.openai()
        prompt = "Kael raises one hand as the portal opens, cinematic"  # no novel title
        self.assertNotIn("eternal nexus", prompt.lower())
        tgt = self.tmp / "k.png"
        ctx = ip.build_identity_context(character_id="kael_veyra", source="test")
        with identity_flag(True, self.log), ip.identity_production_context(ctx):
            with self.assertRaises(Exception):
                app.create_openai_image(prompt, tgt)
        r = self.assert_governed_block(self.records(), "kael_veyra")[0]
        self.assertEqual(r["CHARACTER_BINDING_SOURCE"], "STRUCTURED_CHARACTER_ID")
        self.assertEqual(r["STRUCTURED_CHARACTER_ID"], "kael_veyra")

    def test_03_governed_liang_no_name_no_title_binds_liang(self):
        self.local_sd()
        self.strategy(["local_stable_diffusion", "local_fallback"])
        abbr, _novel, nameless = NAMELESS["liang"]
        tgt = self.tmp / "l.png"
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_prompt_fallback_image(nameless, tgt, 1, abbr)
        self.assertTrue(ip.is_identity_block(cm.exception))
        r = self.assert_governed_block(self.records(), "liang")[0]
        self.assertEqual(r["STRUCTURED_NOVEL_ALIAS"], "HP")
        self.assertEqual(r["PROMPT_FALLBACK_USED"], "NO")

    def test_04_governed_jarek_via_production_alias_binds_jarek(self):
        self.assertEqual(ip.resolve_production_novel_alias("SF"), "sf")
        self.assertEqual(ip.resolve_production_novel_alias("Soulforge Era"), "sf")
        self.assertIsNone(ip.resolve_production_novel_alias("SFE"))  # not a production alias (not invented)
        self.local_sd()
        self.strategy(["local_stable_diffusion", "local_fallback"])
        tgt = self.tmp / "j.png"
        with identity_flag(True, self.log):
            with self.assertRaises(Exception):
                app.create_unique_prompt_fallback_image(NAMELESS["jarek"][2], tgt, 1, "SF")
        r = self.assert_governed_block(self.records(), "jarek")[0]
        self.assertEqual(r["CHARACTER_BINDING_SOURCE"], "STRUCTURED_NOVEL_ALIAS")

    def test_05_known_governed_context_failed_binding_fail_closed(self):
        img = self.old_image("x.png", FAKE)
        cases = [
            ip.build_identity_context(novel="Hundredfold Path", abbr="SF"),                  # conflicting novel ids
            ip.build_identity_context(abbr="HP", identity_contract_id="IDENTITY:hp:liang:19990101"),  # contract mismatch
            ip.build_identity_context(character_id="kai", novel="sf"),                        # cross-character
        ]
        with identity_flag(True, self.log):
            for ctx in cases:
                res = ip.run_identity_acceptance_gate(img, path_id="TEST:05", prompt="a quiet scene",
                                                      identity_context=ctx, quarantine=False, write_sidecar=False)
                self.assertEqual(res.decision, "FAIL_CLOSED", ctx)
                self.assertFalse(res.auto_accept_allowed)
                self.assertIn(ip.GOVERNED_CONTEXT_BINDING_FAILED, res.fail_reason)
                self.assertNotEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
                for r in res.records:
                    self.assertEqual(r["GOVERNED_CONTEXT_BINDING_RESULT"], "FAILED")
                    self.assertEqual(r["GOVERNED_CONTEXT_PRESENT"], "YES")

    def test_06_truly_unknown_no_governed_character(self):
        img = self.old_image("u.png", FAKE)
        with identity_flag(True, self.log):
            res = ip.run_identity_acceptance_gate(img, path_id="TEST:06", prompt="misty landscape, no people",
                                                  quarantine=False, write_sidecar=False)
        self.assertEqual(res.decision, ip.NOT_APPLICABLE_DECISION)
        r = res.records[0]
        self.assertEqual(r["GOVERNED_CONTEXT_PRESENT"], "NO")
        self.assertEqual(r["CHARACTER_BINDING_SOURCE"], "NONE")
        self.assertTrue(r["NO_GOVERNED_CHARACTER_REASON"])


# ---------------------------------------------------------------------------
# VISUAL DIRECTOR (7-11)
# ---------------------------------------------------------------------------
VD_SCENES = {"kai": ("ha", "Kai walks into the alley"), "kael_veyra": ("en", "Kael logs in"),
             "liang": ("hp", "Liang enters the ruined sect hall"), "jarek": ("sf", "Jarek climbs the forge")}


class TestVisualDirector(_Base):
    def prompts(self, key, on):
        nov, scene = VD_SCENES[key]
        with identity_flag(on, self.log):
            return vd.build_visual_scene_package(nov, "", scene, shots_text=[scene] * 3)["image_prompts"]

    def test_07_identity_block_identity_only_and_verifier_audits_emitted_text(self):
        for key in VD_SCENES:
            for p in self.prompts(key, True):
                block = ip.extract_emitted_identity_block(p)
                self.assertTrue(block, p)
                self.assertEqual(ip.identity_lock_denylist_hits(block), [], (key, block))
                for bad in ("shirt", "rags", "chains", "jian", "Weapon", "Appearance", "qi", "logo", "robe", "HUD"):
                    self.assertNotIn(bad, block, (key, block))
            img = self.old_image(f"vd_{key}.png", FAKE)
            with identity_flag(True, self.log):
                res = ip.run_identity_acceptance_gate(img, path_id="TEST:07", prompt=self.prompts(key, True)[0],
                                                      quarantine=False, write_sidecar=False)
            r = [x for x in res.records if x.get("CHARACTER") == key][0]
            self.assertEqual(r["IDENTITY_LOCK_TEXT_SOURCE"], "EMITTED_PROMPT_IDENTITY_BLOCK")
            self.assertNotIn(f"{key}:IDENTITY_LOCK_FORBIDDEN_TERMS_ABSENT", res.fail_reason)
        # The verifier checks the EMITTED text: a contaminated block fails the lock check.
        bad = self.old_image("vd_bad.png", FAKE)
        dirty = ("x. Character Identity: Name: Jarek; Age: 16; Appearance: scavenger rags, iron chains; "
                 "Weapon: one standard-length Chinese jian. Camera: wide.")
        with identity_flag(True, self.log):
            res = ip.run_identity_acceptance_gate(bad, path_id="TEST:07b", prompt=dirty, quarantine=False, write_sidecar=False)
        self.assertIn("IDENTITY_LOCK_FORBIDDEN_TERMS_ABSENT", res.fail_reason)
        self.assertFalse(res.auto_accept_allowed)

    def test_08_jarek_emits_age_16(self):
        block = ip.extract_emitted_identity_block(self.prompts("jarek", True)[0])
        self.assertIn("Age: 16", block)
        self.assertIn("Gender: male", block)
        self.assertNotIn("young adult", block)

    def test_09_liang_gender_unspecified(self):
        ps = self.prompts("liang", True)
        for p in ps:
            self.assertNotIn("Gender:", ip.extract_emitted_identity_block(p))
            self.assertNotRegex(p, r"\b(he|him|his|she|her)\b")

    def test_10_selected_character_replaces_hardcoded_liang_camera(self):
        for key in ("kai", "kael_veyra", "jarek"):
            name = ip.GOVERNED_IDENTITY_CONTRACTS[key].display_name
            for p in self.prompts(key, True):
                self.assertNotIn("Liang", p, key)
                cam = p.split("Camera: ", 1)[1]
                self.assertIn(name, cam)
        # flag OFF: SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R2 Part I (option A) removed the hardcoded
        # HP Liang camera cross-novel leak regardless of the identity flag (deterministic bugfix;
        # FLAG_OFF_COMPATIBILITY amended). Supported HP scenes keep the legacy HP cameras.
        for p in self.prompts("kai", False):
            self.assertNotIn("behind Liang as he climbs", p)
            self.assertNotIn("ruined sect hall", p.lower())

    def test_11_jian_not_global(self):
        for key in ("kai", "kael_veyra", "jarek"):
            for p in self.prompts(key, True):
                self.assertNotIn("jian", p.lower(), key)
                self.assertNotIn("sword hilt", p, key)
        for p in self.prompts("liang", True):
            self.assertIn("Weapon: one standard-length Chinese jian", p)
            self.assertNotIn("jian", ip.extract_emitted_identity_block(p))
            self.assertIn("sheathed at the left hip", p)


# ---------------------------------------------------------------------------
# FALLBACK (12-24)
# ---------------------------------------------------------------------------
class TestFallbackCallSites(_Base):
    def test_12_weekend_daily_promo_reuse_reverified(self):
        self.local_sd()
        daily = self.old_image("SF_Saturday.png")
        social = self.tmp / "social_out"
        social.mkdir()
        self.start([
            mock.patch.object(app, "list_daily_promo_images", return_value=[{"abbr": "SF", "day": "Saturday", "path": str(daily)}]),
            mock.patch.object(app, "SOCIAL_OUTPUT_DIR", social),
            mock.patch.object(app, "generate_promo_image_v2", return_value=None),
            mock.patch.object(app, "attach_post_audio", side_effect=lambda payload, *a, **k: payload),
        ])
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.make_weekend_social_post("SF", "Saturday", publish_generated_media=False)
        self.assertTrue(ip.is_identity_block(cm.exception))
        recs = [r for r in self.records() if r["PATH_ID"].startswith("FALLBACK:make_weekend_social_post")]
        self.assert_governed_block(recs, "jarek", fallback_class="DAILY_PROMO_IMAGE")
        self.assertEqual(recs[0]["FALLBACK_IMAGE_SHA256"], sha(OLD))
        payloads = [p for p in social.rglob("*") if p.is_file() and p.read_bytes() == OLD]
        self.assertEqual(payloads, [], "unchecked daily promo pixels must not reach the weekend payload")
        self.assertEqual(daily.read_bytes(), OLD)  # shared asset evaluated in place, never mutated

    def test_13_tiktok_rotating_promo_reverified(self):
        self.local_sd()
        daily = self.old_image("SF_Monday.png")
        tik = self.tmp / "tiktok_assets"
        tik.mkdir()
        self.start([
            mock.patch.object(app, "TIKTOK_ASSET_DIR", tik), mock.patch.object(app, "EXTERNAL_AI_ENABLED", False),
            mock.patch.object(app, "generate_promo_image_v2", return_value=None),
            mock.patch.object(app, "chapter_image_pack", return_value=[]),
            mock.patch.object(app, "choose_rotating_daily_promo_image", return_value=daily),
        ])
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.generate_tiktok_images("SF", "x", "gold-eyed scavenger in the undercity", force_new_images=False,
                                           style="main-posts")
        self.assertTrue(ip.is_identity_block(cm.exception))
        recs = [r for r in self.records() if r["PATH_ID"] == "FALLBACK:generate_tiktok_images:rotating_daily_promo"]
        self.assert_governed_block(recs, "jarek", fallback_class="DAILY_PROMO_IMAGE")
        self.assertFalse(any(p.read_bytes() == OLD for p in tik.glob("*.png")))

    def _story_hook(self, which):
        self.local_sd()
        old = self.old_image("banked.png")
        pf = self.tmp / f"sh_{which}"
        pf.mkdir()

        def pexels(prompt, target, *a, **k):
            if which != "stock":
                raise RuntimeError("pexels unavailable")
            Path(target).write_bytes(STOCK)
            return {"query": "t"}
        order = (["pexels", "pixabay", "banked", "local_fallback"] if which == "stock" else ["banked", "local_fallback"])
        self.start([
            mock.patch.object(app, "load_automation_strategy", return_value={"imageProviderPriority": order}),
            mock.patch.object(app, "create_pexels_image", side_effect=pexels),
            mock.patch.object(app, "create_pixabay_image", side_effect=RuntimeError("pixabay unavailable")),
            mock.patch.object(app, "choose_banked_image", return_value=old),
        ])
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.build_story_hook_thumbnail_base(pf, "Night", "He wakes in the undercity; his eyes burn.", "SF", force=True)
        self.assertTrue(ip.is_identity_block(cm.exception))
        t = pf / "story-hook-thumbnail-base.png"
        self.assertFalse(t.exists() and t.read_bytes() in (OLD, STOCK))
        return self.records()

    def test_14_story_hook_stock_person_cannot_bypass(self):
        recs = [r for r in self._story_hook("stock") if r["PATH_ID"] == "FALLBACK:build_story_hook_thumbnail_base:pexels"]
        bound = self.assert_governed_block(recs, "jarek", fallback_class="STOCK_IMAGE")
        self.assertIn("STOCK_IN_GOVERNED_SLOT_NOT_CANONICAL_WITHOUT_IDENTITY_REVIEW", bound[0]["FAIL_REASON"])
        self.assertEqual(self.calls["archive"], 0)
        # keyword match is never identity: STOCK is quarantined, not accepted
        self.assertTrue(list((self.tmp / "sh_stock").glob("*.identity-review*")))

    def test_14b_story_hook_banked_reverified(self):
        recs = [r for r in self._story_hook("banked") if r["PATH_ID"] == "FALLBACK:build_story_hook_thumbnail_base:banked"]
        self.assert_governed_block(recs, "jarek", fallback_class="BANKED_GENERATED_IMAGE")
        self.assertEqual(self.calls["mark_used"], 0)

    def test_15_provider_failure_banked_reverified(self):
        self.local_sd(fail=True)
        old = self.old_image("bank.png")
        self.start([mock.patch.object(app, "choose_banked_image", return_value=old),
                    mock.patch.object(app, "EXTERNAL_AI_ENABLED", False),
                    mock.patch.object(app, "ALLOW_EXTERNAL_IMAGE_FALLBACK", True),
                    mock.patch.object(app, "google_ai_configured", return_value=False)])
        self.strategy(["local_stable_diffusion", "openai", "google_ai", "banked", "pexels", "pixabay", "local_fallback"])
        tgt = self.tmp / "pf" / "promo.png"
        tgt.parent.mkdir()
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_prompt_fallback_image("a scavenger crawls through the undercity", tgt, 1, "SF", allow_banked=True)
        self.assertTrue(ip.is_identity_block(cm.exception))
        recs = [r for r in self.records() if r["PATH_ID"] == "FALLBACK:create_prompt_fallback_image:banked"]
        self.assert_governed_block(recs, "jarek", fallback_class="BANKED_GENERATED_IMAGE")
        self.assertFalse(tgt.exists())
        self.assertEqual(self.calls["mark_used"], 0)
        # flag OFF: legacy banked fallback unchanged
        with identity_flag(False, self.log):
            src = app.create_prompt_fallback_image("a scavenger crawls through the undercity", tgt, 1, "SF", allow_banked=True)
        self.assertTrue(src.startswith("bank:"))
        self.assertEqual(tgt.read_bytes(), OLD)

    def test_16_campaign_banked_and_outro_governed(self):
        src = Path(app.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "make_campaign"][0]
        seg = ast.get_source_segment(src, fn)
        self.assertIn("_reraise_identity_block(fallback_exc)", seg)
        self.assertIn('path_id="FALLBACK:make_campaign:outro_daily_promo"', seg)
        # campaign banked slots go through create_unique_prompt_fallback_image -> governed banked:
        self.local_sd(fail=True)
        old = self.old_image("bank2.png")
        self.start([mock.patch.object(app, "choose_banked_image", return_value=old),
                    mock.patch.object(app, "EXTERNAL_AI_ENABLED", False),
                    mock.patch.object(app, "ALLOW_EXTERNAL_IMAGE_FALLBACK", True),
                    mock.patch.object(app, "google_ai_configured", return_value=False)])
        self.strategy(["local_stable_diffusion", "banked", "local_fallback"])
        tgt = self.tmp / "camp" / "promo-1.png"
        tgt.parent.mkdir()
        ctx = ip.build_identity_context(abbr="HA", novel="Heavenly Ascension System", source="app.make_campaign")
        with identity_flag(True, self.log), ip.identity_production_context(ctx):
            with self.assertRaises(Exception) as cm:
                app.create_unique_prompt_fallback_image("chapter still, rain", tgt, 1, "HA", allow_banked=True)
            self.assertTrue(ip.is_identity_block(cm.exception))
            # outro daily-promo reuse check used by make_campaign
            self.assertFalse(app._identity_fallback_allowed(old, asset_class="DAILY_PROMO_IMAGE",
                                                            fallback_source="campaign_outro_daily_promo",
                                                            path_id="FALLBACK:make_campaign:outro_daily_promo"))
        recs = [r for r in self.records() if r["PATH_ID"].startswith("FALLBACK:")]
        self.assert_governed_block(recs, "kai")

    def test_17_chapter_pack_reuse_governed(self):
        self.local_sd()
        pack = [self.old_image(f"ch{i}.png") for i in range(3)]
        tik = self.tmp / "tiktok_assets"
        tik.mkdir()
        self.start([
            mock.patch.object(app, "TIKTOK_ASSET_DIR", tik),
            mock.patch.object(app, "chapter_image_pack", return_value=pack),
            mock.patch.object(app, "generate_promo_image_v2", return_value=None),
            # Offline fixture: chapter text normally comes from raw.githubusercontent.com; the
            # reuse-governance intent does not need it (app falls back on any fetch error).
            mock.patch.object(app, "docs_chapter_text", side_effect=OSError("offline test fixture: no remote chapter text")),
        ])
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.generate_tiktok_images("HP", "3", "terrace at dawn", force_new_images=False, style="main-posts")
        self.assertTrue(ip.is_identity_block(cm.exception), repr(cm.exception))  # reuse refused -> fresh generation -> gated
        recs = [r for r in self.records() if r["PATH_ID"] == "FALLBACK:generate_tiktok_images:chapter_image_pack"]
        self.assert_governed_block(recs, "liang", fallback_class="CHAPTER_PACK_IMAGE")
        self.assertFalse(any(p.read_bytes() == OLD for p in tik.glob("*.png")))
        with identity_flag(False, self.log):
            out = app.generate_tiktok_images("HP", "3", "terrace at dawn", force_new_images=False, style="main-posts")
        self.assertEqual(len(out["reused"]), 3)  # flag OFF legacy reuse unchanged

    def test_18_reusable_pack_reuse_governed(self):
        folder = self.tmp / "pack"
        folder.mkdir()
        img = folder / "promo-1.png"
        img.write_bytes(OLD)
        result = {"images": [str(img)]}
        ctx = ip.build_identity_context(abbr="EN", source="app.make_campaign")
        with identity_flag(True, self.log), ip.identity_production_context(ctx):
            self.assertFalse(app._identity_pack_reuse_allowed(result, folder, "campaign_reusable_pack",
                                                              "FALLBACK:make_campaign:reusable_pack_result"))
        with identity_flag(False, self.log):
            self.assertTrue(app._identity_pack_reuse_allowed(result, folder, "x", "y"))
        recs = self.records()
        self.assert_governed_block(recs, "kael_veyra", fallback_class="REUSABLE_PACK_IMAGE")
        src = Path(app.__file__).read_text(encoding="utf-8")
        for pid in ("FALLBACK:make_campaign:reusable_pack_result", "FALLBACK:make_deep_tiktok_pack:reusable_pack_result",
                    "FALLBACK:build_youtube_from_text:reusable_pack_result"):
            self.assertIn(pid, src)

    def test_19_browser_import_governed(self):
        sh_root = self.tmp / "story_hooks"
        folder = sh_root / "sf-night-abc"
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(json.dumps({"abbr": "SF", "title": "Night"}), encoding="utf-8")
        imp = self.old_image("browser.png")
        bank = self.tmp / "bank"
        self.start([mock.patch.object(app, "STORY_HOOK_OUTPUT_DIR", sh_root),
                    mock.patch.object(app, "MANUAL_VIDEO_IMAGE_BANK_DIR", bank),
                    mock.patch.object(app, "build_youtube_thumbnail", return_value={"thumbnail": ""}),
                    mock.patch.object(app, "record_image_feedback", return_value={})])
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.import_story_hook_thumbnail(str(folder), str(imp))
        self.assertTrue(ip.is_identity_block(cm.exception))
        recs = [r for r in self.records() if r["PATH_ID"] == "BROWSER_IMPORT:import_story_hook_thumbnail"]
        self.assert_governed_block(recs, "jarek", fallback_class="BROWSER_IMPORTED_IMAGE")
        self.assertFalse(bank.exists() and any(bank.rglob("*.png")))
        self.assertFalse(any(folder.glob("story-hook-thumbnail-base*")))
        src = Path(app.__file__).read_text(encoding="utf-8")
        self.assertIn('path_id="BROWSER_IMPORT:import_deep_tiktok_browser_images"', src)


class TestPriorReviewAndProcedural(_Base):
    def prior(self, img: Path, character="jarek", **over):
        rec = ip.build_prior_review_record(image_sha256=sha(img.read_bytes()), character_id=character,
                                           verifier_decision="PASS", human_review_status="APPROVED",
                                           reviewer="test")
        rec.update(over)
        return rec

    def evaluate(self, img, rec, abbr="SF"):
        ctx = ip.build_identity_context(abbr=abbr, source="test")
        with identity_flag(True, self.log):
            return ip.evaluate_governed_fallback(img, fallback_source="t", asset_class="BANKED_GENERATED_IMAGE",
                                                 path_id="TEST:prior", identity_context=ctx, prior_review_record=rec)

    def test_20_compatible_prior_review_permits_reuse(self):
        img = self.old_image()
        res = self.evaluate(img, self.prior(img))
        self.assertTrue(res.auto_accept_allowed, res.fail_reason)
        r = res.records[0]
        self.assertEqual((r["PRIOR_REVIEW_RECORD_USED"], r["PRIOR_REVIEW_RECORD_COMPATIBLE"], r["FALLBACK_IDENTITY_VERIFIED"]),
                         ("YES", "YES", "YES"))
        # also via the sidecar next to a reused asset, at a real call site (TikTok rotating promo)
        ip.prior_review_sidecar_path(img).write_text(json.dumps(self.prior(img)), encoding="utf-8")
        with identity_flag(True, self.log), ip.identity_production_context(ip.build_identity_context(abbr="SF")):
            self.assertTrue(app._identity_fallback_allowed(img, asset_class="DAILY_PROMO_IMAGE", fallback_source="t",
                                                           path_id="FALLBACK:generate_tiktok_images:rotating_daily_promo"))

    def test_21_wrong_character_prior_review_rejected(self):
        img = self.old_image()
        res = self.evaluate(img, self.prior(img, character="liang"))
        self.assertFalse(res.auto_accept_allowed)
        self.assertIn("CHARACTER_MISMATCH_REVERIFY", res.fail_reason)

    def test_22_changed_image_hash_requires_reverify(self):
        img = self.old_image()
        rec = self.prior(img)
        img.write_bytes(OLD + b"changed")
        res = self.evaluate(img, rec)
        self.assertFalse(res.auto_accept_allowed)
        self.assertIn("IMAGE_SHA256_MISMATCH_REVERIFY", res.fail_reason)

    def test_23_changed_contract_version_requires_reverify(self):
        img = self.old_image()
        res = self.evaluate(img, self.prior(img, IDENTITY_CONTRACT_VERSION="20250101"))
        self.assertFalse(res.auto_accept_allowed)
        self.assertIn("IDENTITY_CONTRACT_VERSION_MISMATCH_REVERIFY", res.fail_reason)
        res = self.evaluate(img, self.prior(img, HUMAN_REVIEW_STATUS=""))
        self.assertFalse(res.auto_accept_allowed)  # review missing -> reverify
        res = self.evaluate(img, None)
        self.assertFalse(res.auto_accept_allowed)

    def test_24_procedural_faceless_emergency_art_explicitly_non_canon(self):
        self.local_sd(fail=True)
        self.start([mock.patch.object(app, "EXTERNAL_AI_ENABLED", False),
                    mock.patch.object(app, "ALLOW_EXTERNAL_IMAGE_FALLBACK", False)])
        self.strategy(["local_stable_diffusion", "local_fallback"])
        tgt = self.tmp / "em" / "promo.png"
        tgt.parent.mkdir()
        with identity_flag(True, self.log):
            src = app.create_prompt_fallback_image("Jarek crawls through the undercity", tgt, 1, "SF")
        self.assertTrue(src.startswith("generic:"))
        self.assertTrue(tgt.exists())
        rec = [r for r in self.records() if r["PATH_ID"] == "PROCEDURAL:create_fallback_image"][0]
        self.assertEqual(rec["VERIFIER_DECISION"], ip.NON_CANON_DECISION)
        self.assertEqual(rec["CANON_DEPICTION_STATUS"], ip.NON_CANON_DECISION)
        self.assertEqual(rec["APPROVED_CHARACTER_PORTRAIT"], "NO")
        self.assertEqual(rec["FALLBACK_ASSET_CLASS"], "PROCEDURAL_EMERGENCY_ART")
        self.assertEqual(ip.canon_depiction_status(tgt), ip.NON_CANON_DECISION)
        self.assertFalse(ip.is_approved_character_portrait(tgt))


# ---------------------------------------------------------------------------
# OBSERVABILITY (25-27)
# ---------------------------------------------------------------------------
class TestObservability(_Base):
    def test_25_binding_fields_logged(self):
        img = self.old_image("b.png", FAKE)
        with identity_flag(True, self.log):
            ip.run_identity_acceptance_gate(img, path_id="TEST:25a", prompt="scene", quarantine=False,
                                            identity_context=ip.build_identity_context(abbr="HA"), write_sidecar=False)
            ip.run_identity_acceptance_gate(img, path_id="TEST:25b", prompt="empty street", quarantine=False,
                                            use_ambient_context=False, write_sidecar=False)
        recs = self.records()
        self.assertEqual(len(recs), 2)
        for r in recs:
            for f in list(ip.COVERAGE_LOG_FIELDS) + ["AUTO_ACCEPT_ALLOWED", "HUMAN_REVIEW_REQUIRED", "FAIL_REASON"]:
                self.assertIn(f, r)
            self.assertEqual(ip.validate_observability_record(r), [], r)
        self.assertEqual((recs[0]["CHARACTER_BINDING_SOURCE"], recs[0]["STRUCTURED_NOVEL_ALIAS"], recs[0]["STRUCTURED_NOVEL_ID"]),
                         ("STRUCTURED_NOVEL_ALIAS", "HA", "ha"))
        self.assertEqual(recs[0]["GOVERNED_CONTEXT_BINDING_RESULT"], "BOUND")
        self.assertEqual(recs[1]["GOVERNED_CONTEXT_BINDING_RESULT"], "NO_GOVERNED_CONTEXT")
        self.assertEqual(recs[1]["VERIFIER_DECISION"], ip.NOT_APPLICABLE_DECISION)

    def test_26_fallback_fields_logged(self):
        img = self.old_image()
        with identity_flag(True, self.log):
            ip.evaluate_governed_fallback(img, fallback_source="weekend_daily_promo", asset_class="DAILY_PROMO_IMAGE",
                                          path_id="TEST:26", identity_context=ip.build_identity_context(abbr="SF"))
        r = self.records()[0]
        self.assertEqual((r["FALLBACK_IMAGE_USED"], r["FALLBACK_SOURCE"], r["FALLBACK_ASSET_CLASS"], r["FALLBACK_IMAGE_SHA256"],
                          r["FALLBACK_IDENTITY_VERIFIED"], r["PRIOR_REVIEW_RECORD_USED"]),
                         ("YES", "weekend_daily_promo", "DAILY_PROMO_IMAGE", sha(OLD), "NO", "NO"))
        self.assertEqual(ip.validate_observability_record(r), [])

    def test_27_logger_failure_blocks_governed_acceptance(self):
        img = self.old_image()
        rec = ip.build_prior_review_record(image_sha256=sha(OLD), character_id="jarek", verifier_decision="PASS",
                                           human_review_status="APPROVED")

        def boom(*a, **k):
            raise OSError("disk full")
        with identity_flag(True, self.log):
            res = ip.evaluate_governed_fallback(img, fallback_source="t", asset_class="BANKED_GENERATED_IMAGE",
                                                path_id="TEST:27", identity_context=ip.build_identity_context(abbr="SF"),
                                                prior_review_record=rec, writer=boom)
            res2 = ip.run_identity_acceptance_gate(img, path_id="TEST:27b", prompt="empty street", writer=boom,
                                                   quarantine=False, use_ambient_context=False)
        for x in (res, res2):
            self.assertEqual(x.decision, "FAIL_CLOSED")
            self.assertFalse(x.auto_accept_allowed)
            self.assertIn("OBSERVABILITY_LOG_FAILURE", x.fail_reason)


# ---------------------------------------------------------------------------
# REGRESSION (28-32)
# ---------------------------------------------------------------------------
class TestRegression(_Base):
    def test_28_v2_structured_bindings_correct(self):
        for key, c in ip.GOVERNED_IDENTITY_CONTRACTS.items():
            spec = SimpleNamespace(identity=SimpleNamespace(character_id=key))
            b = ip.resolve_governed_binding(spec=spec, prompt="nameless scene", novel=c.novel_id)
            self.assertEqual(b.keys, [key])
            self.assertEqual(b.sources[key], "SPEC_IDENTITY")
            self.assertEqual(b.result, "BOUND")
            self.assertFalse(b.fail_reason)
            # structured spec dominates any ambient/novel context and prompt names
            other = [k for k in ip.GOVERNED_IDENTITY_CONTRACTS if k != key][0]
            b2 = ip.resolve_governed_binding(spec=spec, prompt=ip.GOVERNED_IDENTITY_CONTRACTS[other].display_name,
                                             novel=c.novel_id)
            self.assertEqual(b2.keys[0], key)
            self.assertEqual(b2.sources[other], "PROMPT_GOVERNED_NAME_SUPPLEMENTAL")

    def test_29_cross_character_binding_fail_closed(self):
        img = self.old_image("x.png", FAKE)
        spec_ctx = ip.build_identity_context(character_id="liang", abbr="EN")
        with identity_flag(True, self.log):
            res = ip.run_identity_acceptance_gate(img, path_id="TEST:29", prompt="scene", identity_context=spec_ctx,
                                                  quarantine=False, write_sidecar=False)
        self.assertEqual(res.decision, "FAIL_CLOSED")
        self.assertIn("CROSS_CHARACTER_NOVEL_MISMATCH", res.fail_reason)
        self.assertIn("ROUTING_NOVEL_MATCHES_CONTRACT", res.fail_reason)

    def test_30_milestone_authority_blocked(self):
        img = self.old_image("m.png", FAKE)
        with identity_flag(True, self.log):
            res = ip.run_identity_acceptance_gate(img, path_id="TEST:30", prompt="scene", quarantine=False,
                                                  identity_context=ip.build_identity_context(abbr="SF"),
                                                  milestone_conditioning_used=True, write_sidecar=False)
        self.assertFalse(res.auto_accept_allowed)
        self.assertIn("MILESTONE_CONDITIONING_NOT_USED", res.fail_reason)
        self.assertEqual(res.decision, "FAIL_CLOSED")

    def test_31_identity_verifier_behavior_unchanged(self):
        for key, c in ip.GOVERNED_IDENTITY_CONTRACTS.items():
            v = ip.verify_identity(c)
            self.assertEqual(v.decision, "REJECT_REVIEW")
            self.assertEqual(sorted(v.fail_reasons), ["HUMAN_REVIEW_OBSERVATIONS_ABSENT", "NO_QUALIFIED_AUTOMATED_FACE_IDENTITY_MODEL"])
        self.assertEqual(ip.verify_identity(None).decision, "FAIL_CLOSED")
        # flag OFF: gate is a zero-side-effect BYPASS
        img = self.old_image("o.png", FAKE)
        with identity_flag(False, self.log):
            res = ip.run_identity_acceptance_gate(img, path_id="TEST:31", prompt="Jarek")
            fb = ip.evaluate_governed_fallback(img, fallback_source="t", asset_class="STOCK_IMAGE", path_id="TEST:31b")
        self.assertEqual((res.decision, fb.decision), ("BYPASS", "BYPASS"))
        self.assertFalse(self.log.exists())

    def test_32_wardrobe_behavior_unchanged(self):
        from tools import wardrobe_preservation as wp
        out = {}
        for on in (False, True):
            with identity_flag(on, self.log):
                out[on] = {k: wp.build_wardrobe_spec_dict(wp.resolve_wardrobe_constraint(k))
                           for k in wp.list_contract_character_keys()}
        self.assertEqual(out[False], out[True])
        self.assertNotIn("identity_preservation", Path(wp.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
