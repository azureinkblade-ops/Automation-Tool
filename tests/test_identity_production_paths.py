# -*- coding: utf-8 -*-
"""IDENTITY_PRODUCTION_PLUMBING_20260929 - per-path execution proof (Part I).

Drives the REAL production functions in app.py (V2 chokepoint generate_promo_image_v2
with the real Main Posts / Realistic pipelines + real V2 resolution, the V1
generator primitives, the provider-fallback chain and higher-level callers, and the
Visual Director prompt path). All GPU / ComfyUI / HTTP / subprocess generation calls
are mocked: GPU_GENERATIONS=0. Flag ON -> identity gate executes and blocks
auto-accept (image quarantined, bytes unchanged, error raised, no archive/mark-used);
flag OFF -> legacy behavior, zero identity side effects.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from tools import identity_preservation as ip  # noqa: E402
from tools import image_pipeline_v2_activation as activation  # noqa: E402

FLAG = "ENABLE_IDENTITY_PRESERVATION"
FAKE_IMG = b"\x89PNG\r\n\x1a\n" + b"FAKE-GENERATED-IMAGE" * 200  # > 1024 bytes
JAREK_PROMPT = "Jarek dragged iron chains through the forge undercity, cinematic web novel art"
KAI_PROMPT = "Kai stands in a rain-slick alley under the System HUD, cinematic"


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


class _PathBase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.log = self.tmp / "identity_observability.jsonl"
        self.target = self.tmp / "out" / "promo.png"
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.calls = {"generate": 0, "mark_used": 0, "archive": 0, "stock": 0}
        arch = self.tmp / "arch"
        patches = [
            mock.patch.object(app, "mark_image_used", side_effect=self._mark),
            mock.patch.object(app, "save_promo_rotation_state", return_value=None),
            mock.patch.object(app, "archive_generated_promo_image", side_effect=self._archive),
            mock.patch.object(app, "write_image_provider_trace", return_value=None),
            mock.patch.object(app, "generated_promo_images_dir", side_effect=lambda: (arch.mkdir(parents=True, exist_ok=True) or arch)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self._td.cleanup()

    def _mark(self, target):
        self.calls["mark_used"] += 1
        return {}

    def _archive(self, *a, **k):
        self.calls["archive"] += 1
        return None

    def log_records(self):
        import json
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def assert_blocked(self, exc_ctx, path_prefix):
        self.assertTrue(ip.is_identity_block(exc_ctx.exception), repr(exc_ctx.exception))
        self.assertFalse(self.target.exists(), "blocked image must not remain at the publish/persist target")
        q = list(self.target.parent.glob("promo.identity-review*.png"))
        self.assertTrue(q, "quarantined review candidate must exist")
        self.assertEqual(q[0].read_bytes()[:8], FAKE_IMG[:8])
        recs = self.log_records()
        self.assertTrue(recs, "observability record must be emitted")
        self.assertTrue(any(r["PATH_ID"].startswith(path_prefix) for r in recs), [r["PATH_ID"] for r in recs])
        for r in recs:
            self.assertEqual(r["AUTO_ACCEPT_ALLOWED"], "NO")
            self.assertIn(r["VERIFIER_DECISION"], ("REJECT_REVIEW", "FAIL_CLOSED"))
        self.assertEqual(self.calls["mark_used"], 0)
        self.assertEqual(self.calls["archive"], 0)


# ---------------------------------------------------------------------------
# V1 generator primitives
# ---------------------------------------------------------------------------
class _LocalSDMocks:
    def start_local_sd(self):
        def fake_run(cmd, **kw):
            self.calls["generate"] += 1
            out = Path(cmd[cmd.index("--output") + 1])
            out.write_bytes(FAKE_IMG)
            return mock.Mock(returncode=0, stdout="", stderr="")
        ps = [
            mock.patch.object(app, "local_stable_diffusion_status", return_value={"ready": True, "model": "fake-sdxl"}),
            mock.patch.object(app, "lora_track_for_prompt", return_value="main-posts"),
            mock.patch.object(app, "find_lora_weights_for_track", return_value=None),
            mock.patch.object(app, "HeavyJobLimiter", side_effect=lambda *a, **k: contextlib.nullcontext()),
            mock.patch.object(app.subprocess, "run", side_effect=fake_run),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)


class TestV1LocalStableDiffusion(_PathBase, _LocalSDMocks):
    def setUp(self):
        super().setUp()
        self.start_local_sd()

    def test_on_blocks(self):
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_local_stable_diffusion_image(JAREK_PROMPT, self.target)
        self.assertEqual(self.calls["generate"], 1)
        self.assert_blocked(cm, "V1:local_stable_diffusion")
        self.assertEqual(self.log_records()[0]["CHARACTER"], "jarek")
        self.assertEqual(self.log_records()[0]["AGE_EXPECTED"], "16")

    def test_img2img_regeneration_on_blocks(self):
        src = self.tmp / "src.png"
        src.write_bytes(FAKE_IMG)
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_local_stable_diffusion_image(KAI_PROMPT, self.target, input_image=src, strength=0.5)
        self.assert_blocked(cm, "V1:local_stable_diffusion")

    def test_off_legacy(self):
        with identity_flag(False, self.log):
            meta = app.create_local_stable_diffusion_image(JAREK_PROMPT, self.target)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.calls["mark_used"], 1)
        self.assertEqual(meta.get("provider"), "local_stable_diffusion")
        self.assertFalse(self.log.exists())


class TestV1OpenAI(_PathBase):
    def setUp(self):
        super().setUp()
        def fake_req(endpoint, payload):
            self.calls["generate"] += 1
            return {"data": [{"b64_json": base64.b64encode(FAKE_IMG).decode()}]}
        for p in (mock.patch.object(app, "EXTERNAL_AI_ENABLED", True),
                  mock.patch.object(app, "openai_request", side_effect=fake_req)):
            p.start()
            self.addCleanup(p.stop)

    def test_on_blocks(self):
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_openai_image(KAI_PROMPT, self.target)
        self.assert_blocked(cm, "V1:openai")

    def test_off_legacy(self):
        with identity_flag(False, self.log):
            app.create_openai_image(KAI_PROMPT, self.target)
        self.assertEqual(self.target.read_bytes(), FAKE_IMG)
        self.assertFalse(self.log.exists())


class TestV1GoogleAI(_PathBase):
    def setUp(self):
        super().setUp()
        self.target = self.tmp / "out" / "promo.jpg"
        def fake_req(payload):
            self.calls["generate"] += 1
            return {}
        for p in (mock.patch.object(app, "google_ai_configured", return_value=True),
                  mock.patch.object(app, "reserve_google_ai_image_quota", return_value={}),
                  mock.patch.object(app, "google_ai_request", side_effect=fake_req),
                  mock.patch.object(app, "google_ai_extract_image_data",
                                    return_value=(base64.b64encode(FAKE_IMG).decode(), "image/jpeg"))):
            p.start()
            self.addCleanup(p.stop)

    def test_on_blocks(self):
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_google_ai_image("Kael Veyra raises the Soulblade in the Nexus", self.target)
        self.assertTrue(ip.is_identity_block(cm.exception))
        self.assertFalse(self.target.exists())
        self.assertTrue(list(self.target.parent.glob("promo.identity-review*.jpg")))
        self.assertEqual(self.calls["mark_used"], 0)
        self.assertEqual(self.log_records()[0]["CHARACTER"], "kael_veyra")

    def test_off_legacy(self):
        with identity_flag(False, self.log):
            info = app.create_google_ai_image("Kael Veyra raises the Soulblade", self.target)
        self.assertEqual(info["provider"], "google_ai")
        self.assertTrue(self.target.exists())
        self.assertEqual(self.calls["mark_used"], 1)


# ---------------------------------------------------------------------------
# Provider-fallback chain + higher-level callers (manual / bulk / retry / regeneration)
# ---------------------------------------------------------------------------
class TestFallbackChainAndCallers(_PathBase, _LocalSDMocks):
    def setUp(self):
        super().setUp()
        self.start_local_sd()
        stock = mock.Mock(side_effect=lambda *a, **k: self.calls.__setitem__("stock", self.calls["stock"] + 1))
        ps = [
            mock.patch.object(app, "load_automation_strategy",
                              return_value={"imageProviderPriority": ["local_stable_diffusion", "openai", "google_ai",
                                                                      "banked", "pexels", "pixabay", "local_fallback"]}),
            mock.patch.object(app, "image_feedback_prompt_guidance", return_value=""),
            mock.patch.object(app, "EXTERNAL_AI_ENABLED", False),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)

    def test_create_prompt_fallback_image_on_blocks_no_provider_fallthrough(self):
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_prompt_fallback_image(JAREK_PROMPT, self.target, 1, "SF", allow_banked=True)
        self.assert_blocked(cm, "V1:local_stable_diffusion")
        self.assertEqual(self.calls["generate"], 1)  # did not regenerate / substitute after the block

    def test_create_prompt_fallback_image_off_legacy(self):
        with identity_flag(False, self.log):
            src = app.create_prompt_fallback_image(JAREK_PROMPT, self.target, 1, "SF")
        self.assertTrue(src.startswith("local_stable_diffusion:"), src)
        self.assertTrue(self.target.exists())
        self.assertFalse(self.log.exists())

    def test_create_unique_prompt_fallback_image_on_blocks(self):
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_unique_prompt_fallback_image(KAI_PROMPT, self.target, 1, "HA")
        self.assert_blocked(cm, "V1:local_stable_diffusion")

    def test_regenerate_image_with_local_reference_on_blocks(self):
        self.target.write_bytes(FAKE_IMG)  # rejected image being rebuilt (retry / weak-image path)
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.regenerate_image_with_local_reference(JAREK_PROMPT, self.target, index=1, abbr="SF")
        self.assertTrue(ip.is_identity_block(cm.exception))
        self.assertFalse(self.target.exists())
        self.assertGreaterEqual(len(list(self.target.parent.glob("promo.identity-review*.png"))), 1)
        self.assertEqual(self.calls["archive"], 0)

    def test_create_fresh_social_image_from_caption_on_blocks(self):
        with identity_flag(True, self.log):
            with self.assertRaises(Exception) as cm:
                app.create_fresh_social_image_from_caption(
                    self.target, abbr="HA", novel="Heavenly Ascension System", title="Ch 1",
                    caption="Kai finally looks up at the System.", visual_brief=KAI_PROMPT)
        self.assert_blocked(cm, "V1:local_stable_diffusion")

    def test_non_governed_prompt_on_is_not_blocked_but_logged(self):
        with identity_flag(True, self.log):
            # IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929 (Part D): a truly contextless
            # call (no abbr) is NO_GOVERNED_CHARACTER.
            # IDENTITY_FINAL_COVERAGE_HARDENING_20260930 (Part N): the old premise "abbr HP binds
            # Liang for a scenery image" is superseded. Governed-novel membership alone no longer
            # implies a depicted character: HP + NO structured intent keeps the safe default
            # (potentially governed -> Liang review), but HP + STRUCTURED scenery intent is a
            # scenery bypass (no identity visual review, no Liang binding), asserted below.
            src = app.create_prompt_fallback_image("misty mountain landscape at dawn, no people", self.target, 1, "")
        self.assertTrue(src.startswith("local_stable_diffusion:"))
        self.assertTrue(self.target.exists())
        self.assertEqual(self.log_records()[0]["VERIFIER_DECISION"], ip.NOT_APPLICABLE_DECISION)
        scenery = self.tmp / "out" / "scenery.png"
        with identity_flag(True, self.log), ip.image_intent_scope(
                ip.ImageIntentRequest(scene_subject="scenery", origin="test.structured_scene_request")):
            src2 = app.create_prompt_fallback_image("misty mountain landscape at dawn, no people", scenery, 1, "HP")
        self.assertTrue(src2.startswith("local_stable_diffusion:"))
        self.assertTrue(scenery.exists())
        rec = self.log_records()[-1]
        self.assertEqual(rec["VERIFIER_DECISION"], ip.NOT_APPLICABLE_DECISION)
        self.assertEqual(rec["IMAGE_INTENT_CLASS"], "SCENERY_ONLY")
        self.assertEqual(rec["SCENERY_BYPASS_APPLIED"], "YES")
        self.assertEqual(rec["IDENTITY_GATE_REQUIRED"], "NO")
        self.assertEqual(rec["CHARACTER"], "")
        self.assertEqual(rec["GOVERNED_CONTEXT_PRESENT"], "YES")


# ---------------------------------------------------------------------------
# V2 chokepoint: app.generate_promo_image_v2 (real pipeline build_spec + real resolution)
# ---------------------------------------------------------------------------
class _V2Base(_PathBase):
    profile = "main_posts"
    style = "main-posts"

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "activation.json"
        cm = activation.using_state_file(self.state)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        activation.clear_v2_activation_overrides()
        self.addCleanup(activation.clear_v2_activation_overrides)
        ov = activation.v2_activation_override(self.profile, True)
        ov.__enter__()
        self.addCleanup(ov.__exit__, None, None, None)
        self.resolutions = []

    def materialize(self, resolution):
        self.calls["generate"] += 1
        self.resolutions.append(resolution)
        return FAKE_IMG

    def run_v2(self, novel, scene):
        return app.generate_promo_image_v2(self.style, scene, self.target, abbr="T", index=1,
                                           materialize=self.materialize, novel=novel, chapter="1",
                                           scene_text=scene, promo_master_enabled=False)


class TestV2MainPosts(_V2Base):
    def test_on_blocks_with_governed_spec(self):
        scene = "Jarek dragged iron chains through the forge undercity; his gold eyes burned."
        with identity_flag(True, self.log):
            with self.assertRaises(app.V2ImageGenerationError) as cm:
                self.run_v2("Soul Forge Era", scene)
        self.assertIsInstance(cm.exception, app.V2IdentityReviewRequired)
        self.assert_blocked(cm, "V2:main_posts")
        rec = self.log_records()[0]
        self.assertEqual(rec["CHARACTER"], "jarek")
        self.assertEqual(rec["AUTHORITY_SOURCE"], "TEXT_CANON")
        self.assertEqual(rec["AGE_EXPECTED"], "16")
        self.assertEqual(rec["MILESTONE_CONDITIONING_USED"], "NO")
        wf_text = str(getattr(self.resolutions[0], "workflow", ""))
        self.assertIn("age 16", wf_text)

    def test_off_legacy(self):
        scene = "Jarek dragged iron chains through the forge undercity; his gold eyes burned."
        with identity_flag(False, self.log):
            src = self.run_v2("Soul Forge Era", scene)
        self.assertEqual(src, "v2:main_posts")
        self.assertTrue(self.target.exists())
        self.assertFalse(self.log.exists())


class TestV2Realistic(_V2Base):
    profile = "realistic"
    style = "realistic-posts"

    def test_on_blocks_and_no_milestone_conditioning_even_with_style_ref_experimental(self):
        scene = "Kai stands in a rain-slick convenience-store alley. Holding the blade."
        with identity_flag(True, self.log):
            os.environ["STYLE_REF_EXPERIMENTAL"] = "1"
            with self.assertRaises(app.V2IdentityReviewRequired) as cm:
                self.run_v2("Heavenly Ascension System", scene)
        self.assert_blocked(cm, "V2:realistic")
        res = self.resolutions[0]
        self.assertNotIn("IPAdapter", str(getattr(res, "workflow", "")))
        self.assertNotEqual(str((res.provenance or {}).get("STYLE_REF_CONDITIONING_ACTIVE", "NO")).upper(), "YES")
        self.assertEqual(self.log_records()[0]["CHARACTER"], "kai")

    def test_off_legacy(self):
        scene = "Kai stands in a rain-slick convenience-store alley. Holding the blade."
        with identity_flag(False, self.log):
            src = self.run_v2("Heavenly Ascension System", scene)
        self.assertEqual(src, "v2:realistic")
        self.assertFalse(self.log.exists())


class TestV2Photorealistic(unittest.TestCase):
    def test_photoreal_never_generates(self):
        # Production-reachable, but always raises before any materializer/KSampler (CPU bind only).
        src = Path(app.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate_promo_image_v2")
        seg = ast.get_source_segment(src, fn)
        photo = seg.split("profile = v2_profile_for_style(style)")[0]
        self.assertIn("raise V2ImageGenerationError(str(PhotorealisticGpuQualificationRequired", photo)
        self.assertNotIn("_invoke_v2_materializer", photo)


# ---------------------------------------------------------------------------
# Visual Director path (app.make_chapter_image_prompts with VISUAL_DIRECTOR_ENABLED)
# ---------------------------------------------------------------------------
class TestVisualDirectorPath(unittest.TestCase):
    def _prompts(self, on):
        saved = {k: os.environ.get(k) for k in (FLAG, "VISUAL_DIRECTOR_ENABLED")}
        try:
            os.environ["VISUAL_DIRECTOR_ENABLED"] = "1"
            os.environ.pop(FLAG, None)
            if on:
                os.environ[FLAG] = "1"
            return app.make_chapter_image_prompts(
                "Soul Forge Era", "Jarek dragged iron chains through the forge undercity.",
                ["Jarek dragged iron chains; his gold eyes burned.", "Jarek looked up; he froze.", "Jarek ran."],
                novel="sf")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_vd_on_age_16_no_pronoun_gender(self):
        on = "\n".join(self._prompts(True))
        self.assertIn("Age: 16", on)
        self.assertNotIn("young adult", on)
        off = "\n".join(self._prompts(False))
        self.assertIn("young adult", off)  # legacy VD behavior preserved under OFF


# ---------------------------------------------------------------------------
# Static coverage: every generation primitive in production code carries the gate
# ---------------------------------------------------------------------------
class TestStaticGateCoverage(unittest.TestCase):
    GATED = {
        "generate_promo_image_v2": "_enforce_identity(",
        "create_local_stable_diffusion_image": "_v1_identity_acceptance_gate(",
        "create_openai_image": "_v1_identity_acceptance_gate(",
        "create_google_ai_image": "_v1_identity_acceptance_gate(",
    }

    def _functions(self):
        src = Path(app.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        return src, {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_primitives_gated(self):
        src, fns = self._functions()
        for name, marker in self.GATED.items():
            self.assertIn(marker, ast.get_source_segment(src, fns[name]), name)
        seg = ast.get_source_segment(src, fns["create_openai_image"])
        self.assertEqual(seg.count("_v1_identity_acceptance_gate("), 2)  # b64 + url returns

    def test_no_other_generator_in_app(self):
        src, fns = self._functions()
        found = set()
        for name, fn in fns.items():
            seg = ast.get_source_segment(src, fn) or ""
            if ('"images/generations"' in seg and "openai_request(" in seg) \
                    or ("google_ai_request(" in seg and name != "google_ai_request"
                        and ('"type": "image"' in seg or "google_ai_extract_image_data(" in seg)) \
                    or ("LOCAL_IMAGE_GENERATOR_SCRIPT" in seg and "subprocess.run(" in seg) \
                    or ("_invoke_v2_materializer(" in seg and name != "_invoke_v2_materializer"):
                found.add(name)
        self.assertEqual(found, set(self.GATED), found)
        # google_ai_generate_text calls google_ai_request for TEXT only (no image response).
        self.assertNotIn("google_ai_generate_text", found)

    def test_fallback_chain_reraises_identity_blocks(self):
        src, fns = self._functions()
        seg = ast.get_source_segment(src, fns["create_prompt_fallback_image"])
        # 3 generator providers + (IDENTITY_PRODUCTION_COVERAGE_REMEDIATION_20260929) banked,
        # pexels and pixabay governed-fallback blocks are also re-raised, never swallowed.
        self.assertEqual(seg.count("_reraise_identity_block(exc)"), 6)

    def test_no_other_generation_endpoint_modules(self):
        hits = []
        for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
            try:
                t = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "images/generations" in t and p.name != "app.py":
                hits.append(p.name)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
