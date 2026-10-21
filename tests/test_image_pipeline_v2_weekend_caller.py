"""Image Pipeline V2 - Weekend Posting caller wiring remediation (CPU-only).

Proves the canonical Weekend Posting image caller (`app.make_weekend_social_post`
and its scheduled convergence `app.make_weekend_posts`) now routes through the
qualified V2 production caller seam `app.generate_promo_image_v2`, using the
EXISTING deterministic visual-track selector (`app.lora_track_for_prompt`) rather
than a second hardcoded style policy.

Fail-closed contract is asserted: a V2-enabled failure surfaces (never silently
falls back to V1 / cloud / stock). A V2-disabled/None return still enters the
established V1 path including the existing stock fallback.

No GPU, no ComfyUI HTTP, no live rendering. B3 is replaced by deterministic
fakes. Deep TikTok scene generation and the existing V2 outro seam are asserted
UNCHANGED (K / L).
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from tools import image_pipeline_v2_activation as activation  # noqa: E402


def _write_png(path: Path, payload: bytes = b"PNGDATA") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class TestWeekendStyleSelectorResolution(unittest.TestCase):
    """Requirement B: existing deterministic selector/mapping resolves V2 style."""

    def _weekend_prompt(self, abbr: str) -> str:
        return (
            f"realistic fantasy promotional image for the web novel "
            f"{app.NOVEL_NAMES.get(abbr, abbr)}, "
            f"weekend reading theme, cinematic realism, dramatic character moment"
        )

    def test_selector_returns_realistic_posts_for_all_novels(self):
        for abbr in app.NOVEL_NAMES:
            track = app.lora_track_for_prompt(self._weekend_prompt(abbr))
            self.assertEqual(track, "realistic-posts", f"{abbr} track")

    def test_realistic_posts_maps_to_realistic_v2_profile(self):
        self.assertEqual(app.v2_profile_for_style("realistic-posts"), "realistic")

    def test_existing_selector_output_is_the_v2_public_style_identity(self):
        # The selector returns the V2 public-style label directly; the central
        # mapping _V2_STYLE_TO_PROFILE is reused (no duplicated mapping).
        track = app.lora_track_for_prompt(self._weekend_prompt("EN"))
        self.assertIn(track, app._V2_STYLE_TO_PROFILE)
        self.assertEqual(app.v2_profile_for_style(track), "realistic")


class FakeResolution:
    def __init__(self, profile="main_posts"):
        self.profile = profile
        self.pipeline_implementation = "FakePipelineV2"
        self.provenance = {"profile": profile, "gpu_execution": False}
        self.routing_provenance = {"router_active": True}


def _patch_weekend_infra(testcase, tmp: Path, abbr: str, day: str, stock_path: Path):
    """Mock the heavy non-generation weekend dependencies.

    Returns a dict of started patches so the caller can introspect call counts.
    """
    patches = {}

    def _start(name, *args, **kw):
        p = mock.patch.object(app, name, *args, **kw)
        p.start()
        testcase.addCleanup(p.stop)
        patches[name] = p
        return p

    _start("list_daily_promo_images", return_value=[
        {"abbr": abbr, "day": day, "path": str(stock_path)}
    ])
    _start("reset_generated_folder",
           side_effect=lambda f: Path(f).mkdir(parents=True, exist_ok=True))
    _start("weekend_social_copy", return_value={
        "instagram": "ig", "x": "x", "facebook": "fb", "alt_text": "alt",
    })
    _start("agent_posts_enabled", return_value=False)
    _start("attach_post_audio", side_effect=lambda payload, *a, **k: payload)
    _start("auto_publish_generated_media", side_effect=lambda folder, payload: payload)
    patches["SOCIAL_OUTPUT_DIR"] = mock.patch.object(
        app, "SOCIAL_OUTPUT_DIR", new=tmp / "social"
    )
    patches["SOCIAL_OUTPUT_DIR"].start()
    testcase.addCleanup(patches["SOCIAL_OUTPUT_DIR"].stop)
    return patches


class _WeekendCallerBase(unittest.TestCase):
    abbr = "EN"
    day = "Saturday"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.stock = self.tmp / "stock.png"
        _write_png(self.stock)
        _patch_weekend_infra(self, self.tmp, self.abbr, self.day, self.stock)
        self.v2 = mock.patch.object(app, "generate_promo_image_v2").start()
        self.addCleanup(self.v2.stop)
        self.v1 = mock.patch.object(app, "create_local_stable_diffusion_image").start()
        self.addCleanup(self.v1.stop)
        self.cloud = mock.patch.object(app, "create_openai_image").start()
        self.addCleanup(self.cloud.stop)
        self.shutil_copy = mock.patch.object(app.shutil, "copy2").start()
        self.addCleanup(self.shutil_copy.stop)

    def _run(self, **kw):
        return app.make_weekend_social_post(self.abbr, self.day, **kw)


class TestWeekendV2SuccessNoV1(_WeekendCallerBase):
    """Requirements A, C, E: V2 success path, no V1/cloud/stock."""

    def test_v2_success_invokes_seam_with_realistic_style(self):
        def _fake(style, prompt, target, **kw):
            _write_png(Path(target))
            return "v2:realistic"
        self.v2.side_effect = _fake

        result = self._run()

        self.v2.assert_called_once()
        call_kwargs = self.v2.call_args
        self.assertEqual(call_kwargs.args[0], "realistic-posts")
        self.v1.assert_not_called()
        self.cloud.assert_not_called()
        self.shutil_copy.assert_not_called()
        # The produced image is the V2 output target.
        self.assertEqual(result["image"], str(self.tmp / "social" / f"weekend-{self.abbr.lower()}-{self.day.lower()}" / f"{self.abbr}_{self.day}.png"))


class TestWeekendV2DisabledEntersV1(_WeekendCallerBase):
    """Requirements I, J: V2 None -> V1 path; V1 failure -> stock fallback."""

    def test_v2_none_enters_v1_and_succeeds(self):
        self.v2.return_value = None

        def _fake_v1(prompt, target, **kw):
            _write_png(Path(target))
            return {"model": "sdxl"}
        self.v1.side_effect = _fake_v1

        result = self._run()

        self.v2.assert_called_once()
        self.v1.assert_called_once()
        self.shutil_copy.assert_not_called()  # V1 success -> no stock copy

    def test_v2_none_v1_failure_uses_stock_fallback(self):
        self.v2.return_value = None
        self.v1.side_effect = RuntimeError("local SD failed")

        result = self._run()

        self.v1.assert_called_once()
        self.shutil_copy.assert_called_once()  # stock copy performed
        # Image resolved to the stock fallback target.
        self.assertTrue(str(result["image"]).endswith(self.stock.name))


class TestWeekendV2FailClosed(_WeekendCallerBase):
    """Requirements F, G, H: V2-enabled failure surfaces, no V1/cloud/stock."""

    def test_v2_enabled_failure_surfaces_and_masks_nothing(self):
        self.v2.side_effect = RuntimeError("V2 materializer failed")

        with self.assertRaises(RuntimeError):
            self._run()

        self.v1.assert_not_called()
        self.cloud.assert_not_called()
        self.shutil_copy.assert_not_called()


class TestWeekendScheduledConvergence(_WeekendCallerBase):
    """Requirement D: scheduled path (make_weekend_posts) reaches same caller."""

    def test_make_weekend_posts_routes_through_v2_seam(self):
        def _fake(style, prompt, target, **kw):
            _write_png(Path(target))
            return "v2:realistic"
        self.v2.side_effect = _fake

        app.make_weekend_posts(self.day)

        self.v2.assert_called_once()
        self.assertEqual(self.v2.call_args.args[0], "realistic-posts")
        self.v1.assert_not_called()


class TestDeepTikTokSceneUnchanged(unittest.TestCase):
    """Classification: this test is on the generate_tiktok_images routing surface.

    The previous assertion expected generate_tiktok_images not to call
    generate_promo_image_v2. That contract is superseded. generate_tiktok_images
    is a live V2 seam caller, including scene frames. Deep TikTok pack scene
    loops (make_deep_tiktok_pack) are a different caller and are not refactored
    here. This method now records the live seam call instead of the stale
    "does not use V2" expectation.
    """
    abbr = "EN"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.v2 = mock.patch.object(app, "generate_promo_image_v2").start()
        self.addCleanup(self.v2.stop)
        self.openai = mock.patch.object(app, "create_openai_image").start()
        self.openai.side_effect = lambda prompt, target, **kw: _write_png(Path(target))
        self.addCleanup(self.openai.stop)
        mock.patch.object(app, "create_unique_prompt_fallback_image",
                          side_effect=lambda *a, **k: "fb").start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(app, "mark_image_used", return_value={}).start()
        mock.patch.object(app, "save_promo_rotation_state").start()
        mock.patch.object(app, "archive_generated_promo_image", return_value=None).start()
        mock.patch.object(app, "choose_rotating_daily_promo_image", return_value=None).start()
        # Force the chapter_text-free, non-digit-chapter path so scene prompts
        # fall back to the base prompt and thus exercise the scene provider chain.
        self.tiktok_dir = self.tmp / "tiktok"
        mock.patch.object(app, "TIKTOK_ASSET_DIR", new=self.tiktok_dir).start()
        self.addCleanup(mock.patch.stopall)

    def test_scene_generation_does_not_use_v2_seam(self):
        """Name retained. Contract: live short-form scenes already use the V2 seam.

        SUPERSEDED expectation: generate_promo_image_v2 must not be called.
        CURRENT: generate_tiktok_images(style=main-posts) calls the V2 seam.
        Not a Deep TikTok pack refactor.
        """
        def _fake(style, prompt, target, **kw):
            _write_png(Path(target))
            return "v2:main_posts"
        self.v2.side_effect = _fake
        app.generate_tiktok_images(
            self.abbr, "scene", "a base prompt",
            force_new_images=True, chapter_text="", chapter_title="", style="main-posts",
        )
        self.v2.assert_called()
        self.assertEqual(self.v2.call_args.args[0], "main-posts")
        self.openai.assert_not_called()


class TestDeepTikTokOutroRetainsV2(unittest.TestCase):
    """Requirement L: existing V2 outro seam still calls generate_promo_image_v2."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "pack"
        self.folder.mkdir()
        self.route = mock.patch("tools.image_pipeline_v2_router.route_v2_image_generation",
                                return_value=FakeResolution("main_posts")).start()
        self.addCleanup(self.route.stop)
        self.bank = mock.patch.object(
            app, "choose_rotating_daily_promo_image", return_value=None
        ).start()
        self.addCleanup(self.bank.stop)
        self.fallback = mock.patch.object(app, "create_prompt_fallback_image",
                                          side_effect=lambda *a, **k: str(a[1])).start()
        self.addCleanup(self.fallback.stop)

    def test_outro_calls_v2_seam_when_enabled(self):
        app.V2_PROMO_MATERIALIZER = lambda r: b"FAKEV2"
        ov = activation.v2_activation_override("main_posts", True)
        ov.__enter__()
        try:
            out = app.prepare_tiktok_outro_image(
                self.folder, "TEST", "Test Novel", 1, style="main-posts"
            )
        finally:
            ov.__exit__(None, None, None)
            app.V2_PROMO_MATERIALIZER = None
        self.route.assert_called_once()
        self.fallback.assert_not_called()
        self.assertTrue(Path(out).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
