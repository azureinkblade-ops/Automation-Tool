"""CPU-only proof of the live V2 promo seam in canonical app.py.

No GPU, no ComfyUI, no network. Mocks the pipeline build_spec / materializer.
"""
from __future__ import annotations

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
from tools import image_pipeline_v2_activation as activation  # noqa: E402

# Deterministic test fixture mirroring the production activation state (main_posts/realistic ON).
# Tests read it via activation.using_state_file; the live STATE_ROOT file is never read or written.
ACTIVATION_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "image_pipeline_v2_activation.json"


def _write_png(path, payload=b"PNGDATA"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class _RecordingPipeline:
    calls = []

    def build_spec(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(prompt=kwargs.get("prompt"), kwargs=dict(kwargs))

    def resolve(self, spec, *, replica=0, read_bytes=None):
        return SimpleNamespace(
            spec=spec,
            workflow={},
            provenance={"profile": "recorded"},
            pipeline_implementation="RecordingPipeline",
            routing_provenance={"router_active": False},
        )


def _materialize_bytes(resolution):
    return b"FAKEV2BYTES"


class _SeamHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pipeline = _RecordingPipeline()
        self.pipeline.calls = []
        self.addCleanup(self._stop)
        self._patches = []

        def start(name, **kw):
            p = mock.patch.object(app, name, **kw)
            started = p.start()
            self._patches.append(p)
            return started

        self.arch = self.tmp / "arch"
        start("generated_promo_images_dir", return_value=self.arch)
        start("mark_image_used", return_value={})
        start("save_promo_rotation_state")
        start("_v2_pipeline_class", return_value=lambda: self.pipeline)
        # Keep resolution on the recording pipeline; do not import the router.
        start("_resolve_v2_request", side_effect=lambda profile, pipeline, spec, **kw: pipeline.resolve(spec))
        app.V2_PROMO_MATERIALIZER = _materialize_bytes
        self.addCleanup(self._clear_materializer)

    def _stop(self):
        for p in reversed(self._patches):
            p.stop()

    def _clear_materializer(self):
        app.V2_PROMO_MATERIALIZER = None

    def _assert_context(self, novel, chapter, scene_text):
        self.assertTrue(self.pipeline.calls, "build_spec was not called")
        last = self.pipeline.calls[-1]
        self.assertEqual(last.get("novel"), novel)
        self.assertEqual(last.get("chapter"), chapter)
        self.assertEqual(last.get("scene_text"), scene_text)
        self.assertIn("prompt", last)


class TestStyleGate(unittest.TestCase):
    def test_style_mapping_and_comic_off(self):
        self.assertEqual(app.v2_profile_for_style("main-posts"), "main_posts")
        self.assertEqual(app.v2_profile_for_style("realistic-posts"), "realistic")
        self.assertIsNone(app.v2_profile_for_style("comic-style"))
        self.assertIsNone(app.v2_profile_for_style("comic"))
        self.assertIsNone(app.v2_profile_for_style("azink_real"))
        self.assertIn("realistic-posts", app._V2_STYLE_TO_PROFILE)
        self.assertNotIn("comic-style", app._V2_STYLE_TO_PROFILE)

    def test_live_json_enables_main_posts_and_realistic_not_comic(self):
        with activation.using_state_file(ACTIVATION_FIXTURE):
            flags = activation.load_v2_activation_state()
        self.assertTrue(flags["main_posts"])
        self.assertTrue(flags["realistic"])
        self.assertNotIn("comic", flags)
        with activation.using_state_file(ACTIVATION_FIXTURE):
            self.assertFalse(activation.is_v2_profile_enabled("comic"))

    def test_comic_and_unknown_return_none_even_if_override_true(self):
        target = Path(tempfile.mkdtemp()) / "x.png"
        pipeline = mock.Mock()
        with mock.patch.object(app, "_v2_pipeline_class", return_value=pipeline):
            self.assertIsNone(app.generate_promo_image_v2("comic-style", "p", target, enabled_override=True))
            self.assertIsNone(app.generate_promo_image_v2("azink_real", "p", target, enabled_override=True))
        pipeline.assert_not_called()


class TestSeamForwardsContext(_SeamHarness):
    def test_build_spec_receives_novel_chapter_scene_text(self):
        target = self.tmp / "promo.png"
        src = app.generate_promo_image_v2(
            "main-posts",
            "a prompt",
            target,
            abbr="EN",
            index=4,
            novel="Eternal Nexus",
            chapter=12,
            scene_text="the valley gate",
        )
        self.assertEqual(src, "v2:main_posts")
        self._assert_context("Eternal Nexus", 12, "the valley gate")
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), b"FAKEV2BYTES")

    def test_disabled_profile_returns_none_without_pipeline(self):
        target = self.tmp / "promo.png"
        with activation.v2_activation_override("realistic", False):
            src = app.generate_promo_image_v2(
                "realistic-posts", "p", target, novel="N", chapter=None, scene_text=None,
            )
        self.assertIsNone(src)
        self.assertFalse(self.pipeline.calls)

    def test_enabled_materializer_error_raises_and_writes_no_image(self):
        target = self.tmp / "promo.png"

        def boom(resolution):
            raise RuntimeError("materializer failed")

        app.V2_PROMO_MATERIALIZER = boom
        with activation.using_state_file(ACTIVATION_FIXTURE), self.assertRaises(RuntimeError):
            app.generate_promo_image_v2(
                "main-posts", "p", target, novel="N", chapter="1", scene_text="s",
            )
        self.assertFalse(target.exists())


def _patch_archive(testcase, tmp: Path):
    arch = tmp / "arch"
    mock.patch.object(app, "generated_promo_images_dir", return_value=arch).start()
    mock.patch.object(app, "mark_image_used", return_value={}).start()
    mock.patch.object(app, "save_promo_rotation_state").start()
    testcase.addCleanup(mock.patch.stopall)


class TestCallersReachBuildSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pipeline = _RecordingPipeline()
        self.pipeline.calls = []
        _patch_archive(self, self.tmp)
        mock.patch.object(app, "_v2_pipeline_class", return_value=lambda: self.pipeline).start()
        mock.patch.object(
            app, "_resolve_v2_request",
            side_effect=lambda profile, pipeline, spec, **kw: pipeline.resolve(spec),
        ).start()
        app.V2_PROMO_MATERIALIZER = _materialize_bytes
        self.addCleanup(lambda: setattr(app, "V2_PROMO_MATERIALIZER", None))
        self.addCleanup(mock.patch.stopall)

    def test_prepare_tiktok_outro_main_posts_reaches_build_spec(self):
        folder = self.tmp / "pack"
        folder.mkdir()
        mock.patch.object(app, "choose_rotating_daily_promo_image", return_value=None).start()
        out = app.prepare_tiktok_outro_image(folder, "EN", "Eternal Nexus", 12, style="main-posts")
        self.assertTrue(Path(out).exists())
        last = self.pipeline.calls[-1]
        self.assertEqual(last.get("novel"), "Eternal Nexus")
        self.assertEqual(last.get("chapter"), 12)
        self.assertIsNone(last.get("scene_text"))

    def test_generate_tiktok_images_realistic_reaches_build_spec(self):
        mock.patch.object(app, "TIKTOK_ASSET_DIR", new=self.tmp / "tiktok").start()
        mock.patch.object(
            app, "short_chapter_visual_moments",
            return_value=["rain on the gate", "second moment", "third moment"],
        ).start()
        novel = app.NOVEL_NAMES.get("EN", "EN")
        result = app.generate_tiktok_images(
            "EN", "7", "base visual",
            force_new_images=True,
            chapter_text="chapter body",
            style="realistic-posts",
        )
        self.assertEqual(len(self.pipeline.calls), 3)
        self.assertEqual(self.pipeline.calls[0].get("novel"), novel)
        self.assertEqual(self.pipeline.calls[0].get("chapter"), "7")
        self.assertEqual(self.pipeline.calls[0].get("scene_text"), "rain on the gate")
        self.assertTrue(all(src.startswith("v2:realistic") for src in result["image_sources"]))

    def test_weekend_realistic_reaches_build_spec(self):
        stock = self.tmp / "stock.png"
        _write_png(stock)
        mock.patch.object(app, "list_daily_promo_images", return_value=[
            {"abbr": "EN", "day": "Saturday", "path": str(stock)}
        ]).start()
        mock.patch.object(app, "reset_generated_folder", side_effect=lambda f: Path(f).mkdir(parents=True, exist_ok=True)).start()
        mock.patch.object(app, "weekend_social_copy", return_value={
            "instagram": "ig", "x": "x", "facebook": "fb", "alt_text": "alt",
        }).start()
        mock.patch.object(app, "agent_posts_enabled", return_value=False).start()
        mock.patch.object(app, "attach_post_audio", side_effect=lambda payload, *a, **k: payload).start()
        mock.patch.object(app, "auto_publish_generated_media", side_effect=lambda folder, payload: payload).start()
        mock.patch.object(app, "SOCIAL_OUTPUT_DIR", new=self.tmp / "social").start()
        novel = app.NOVEL_NAMES.get("EN", "EN")
        result = app.make_weekend_social_post("EN", "Saturday")
        self.assertEqual(len(self.pipeline.calls), 1)
        self.assertEqual(self.pipeline.calls[0].get("novel"), novel)
        self.assertIsNone(self.pipeline.calls[0].get("chapter"))
        self.assertIsNone(self.pipeline.calls[0].get("scene_text"))
        self.assertTrue(str(result["image"]).endswith("EN_Saturday.png"))


class TestEnabledFailureDoesNotFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.v1 = mock.patch.object(app, "create_prompt_fallback_image").start()
        self.openai = mock.patch.object(app, "create_openai_image").start()
        self.sd = mock.patch.object(app, "create_local_stable_diffusion_image").start()
        self.unique = mock.patch.object(app, "create_unique_prompt_fallback_image").start()
        self.copy = mock.patch.object(app.shutil, "copy2").start()
        mock.patch.object(app, "generate_promo_image_v2", side_effect=RuntimeError("V2 materializer failed")).start()
        self.addCleanup(mock.patch.stopall)

    def test_outro_failure_does_not_use_fallback(self):
        folder = self.tmp / "pack"
        folder.mkdir()
        mock.patch.object(app, "choose_rotating_daily_promo_image", return_value=None).start()
        with self.assertRaises(RuntimeError):
            app.prepare_tiktok_outro_image(folder, "EN", "Eternal Nexus", 1, style="main-posts")
        self.v1.assert_not_called()
        self.openai.assert_not_called()
        self.sd.assert_not_called()
        self.copy.assert_not_called()

    def test_tiktok_images_failure_does_not_use_openai_or_stock(self):
        mock.patch.object(app, "TIKTOK_ASSET_DIR", new=self.tmp / "tiktok").start()
        mock.patch.object(app, "short_chapter_visual_moments", return_value=["only scene"]).start()
        with self.assertRaises(RuntimeError):
            app.generate_tiktok_images(
                "EN", "7", "base", force_new_images=True, chapter_text="body", style="main-posts",
            )
        self.openai.assert_not_called()
        self.unique.assert_not_called()
        self.sd.assert_not_called()
        self.copy.assert_not_called()

    def test_weekend_failure_is_not_hidden_by_stock(self):
        stock = self.tmp / "stock.png"
        _write_png(stock)
        mock.patch.object(app, "list_daily_promo_images", return_value=[
            {"abbr": "EN", "day": "Saturday", "path": str(stock)}
        ]).start()
        mock.patch.object(app, "reset_generated_folder", side_effect=lambda f: Path(f).mkdir(parents=True, exist_ok=True)).start()
        with self.assertRaises(RuntimeError):
            app.make_weekend_social_post("EN", "Saturday")
        self.sd.assert_not_called()
        self.openai.assert_not_called()
        self.copy.assert_not_called()


class TestComicAndDisabledUseLegacy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(mock.patch.stopall)

    def test_comic_outro_uses_legacy_fallback(self):
        folder = self.tmp / "pack"
        folder.mkdir()
        mock.patch.object(app, "choose_rotating_daily_promo_image", return_value=None).start()
        fallback = mock.patch.object(app, "create_prompt_fallback_image", return_value="legacy").start()
        pipeline = mock.Mock()
        mock.patch.object(app, "_v2_pipeline_class", return_value=pipeline).start()
        out = app.prepare_tiktok_outro_image(folder, "EN", "Eternal Nexus", 3, style="comic-style")
        self.assertTrue(str(out).endswith("novel-promo-card.png"))
        fallback.assert_called_once()
        pipeline.assert_not_called()

    def test_comic_tiktok_images_use_openai_legacy(self):
        mock.patch.object(app, "TIKTOK_ASSET_DIR", new=self.tmp / "tiktok").start()
        mock.patch.object(app, "short_chapter_visual_moments", return_value=["panel one"]).start()
        mock.patch.object(app, "archive_generated_promo_image", return_value="").start()
        mock.patch.object(app, "mark_image_used", return_value={}).start()
        mock.patch.object(app, "save_promo_rotation_state").start()

        def _openai(prompt, target, **kw):
            _write_png(target)

        openai = mock.patch.object(app, "create_openai_image", side_effect=_openai).start()
        pipeline = mock.Mock()
        mock.patch.object(app, "_v2_pipeline_class", return_value=pipeline).start()
        result = app.generate_tiktok_images(
            "EN", "scene", "base", force_new_images=True, chapter_text="body", style="comic-style",
        )
        self.assertEqual(openai.call_count, 3)
        pipeline.assert_not_called()
        self.assertTrue(result["created"])

    def test_disabled_main_posts_outro_uses_legacy(self):
        folder = self.tmp / "pack"
        folder.mkdir()
        mock.patch.object(app, "choose_rotating_daily_promo_image", return_value=None).start()
        mock.patch.object(
            activation, "is_v2_profile_enabled",
            side_effect=lambda profile, override=None: False,
        ).start()
        fallback = mock.patch.object(app, "create_prompt_fallback_image", return_value="legacy").start()
        pipeline = mock.Mock()
        mock.patch.object(app, "_v2_pipeline_class", return_value=pipeline).start()
        app.prepare_tiktok_outro_image(folder, "EN", "Eternal Nexus", 1, style="main-posts")
        fallback.assert_called_once()
        pipeline.assert_not_called()

    def test_disabled_weekend_uses_local_sd_not_v2_pipeline(self):
        stock = self.tmp / "stock.png"
        _write_png(stock)
        mock.patch.object(app, "list_daily_promo_images", return_value=[
            {"abbr": "EN", "day": "Saturday", "path": str(stock)}
        ]).start()
        mock.patch.object(app, "reset_generated_folder", side_effect=lambda f: Path(f).mkdir(parents=True, exist_ok=True)).start()
        mock.patch.object(app, "weekend_social_copy", return_value={
            "instagram": "ig", "x": "x", "facebook": "fb", "alt_text": "alt",
        }).start()
        mock.patch.object(app, "agent_posts_enabled", return_value=False).start()
        mock.patch.object(app, "attach_post_audio", side_effect=lambda payload, *a, **k: payload).start()
        mock.patch.object(app, "auto_publish_generated_media", side_effect=lambda folder, payload: payload).start()
        mock.patch.object(app, "SOCIAL_OUTPUT_DIR", new=self.tmp / "social").start()
        mock.patch.object(
            activation, "is_v2_profile_enabled",
            side_effect=lambda profile, override=None: False,
        ).start()

        def _sd(prompt, target, **kw):
            _write_png(target)
            return {"model": "sdxl"}

        sd = mock.patch.object(app, "create_local_stable_diffusion_image", side_effect=_sd).start()
        pipeline = mock.Mock()
        mock.patch.object(app, "_v2_pipeline_class", return_value=pipeline).start()
        copy = mock.patch.object(app.shutil, "copy2").start()
        app.make_weekend_social_post("EN", "Saturday")
        sd.assert_called_once()
        pipeline.assert_not_called()
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
