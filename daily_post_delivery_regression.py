from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import app


INSTAGRAM_CHANNEL = "instagram-regression-channel"


def _service(channel_id: str) -> str:
    return "instagram" if channel_id == INSTAGRAM_CHANNEL else "tiktok"


def test_regular_instagram_post_gets_required_type() -> None:
    assets = [{"image": {"url": "https://example.invalid/post.png"}}]
    with patch.object(app, "buffer_channel_service", side_effect=_service):
        metadata = app.buffer_metadata_for_channel(INSTAGRAM_CHANNEL, assets, {})
    assert metadata == {"instagram": {"type": "post", "shouldShareToFeed": True}}


def test_instagram_video_gets_reel_type() -> None:
    assets = [{"video": {"url": "https://example.invalid/reel.mp4"}}]
    with patch.object(app, "buffer_channel_service", side_effect=_service):
        metadata = app.buffer_metadata_for_channel(INSTAGRAM_CHANNEL, assets, {})
    assert metadata["instagram"]["type"] == "reel"


def test_explicit_instagram_story_is_preserved() -> None:
    assets = [{"image": {"url": "https://example.invalid/story.png"}}]
    with patch.object(app, "buffer_channel_service", side_effect=_service):
        metadata = app.buffer_metadata_for_channel(
            INSTAGRAM_CHANNEL,
            assets,
            {"instagram": {"type": "STORY", "shouldShareToFeed": "false"}},
        )
    assert metadata["instagram"] == {"type": "story", "shouldShareToFeed": False}


def test_non_instagram_metadata_is_unchanged() -> None:
    with patch.object(app, "buffer_channel_service", side_effect=_service):
        metadata = app.buffer_metadata_for_channel(
            "tiktok-regression-channel",
            [{"video": {"url": "https://example.invalid/video.mp4"}}],
            {"tiktok": {"privacy": "public"}},
        )
    assert metadata == {"tiktok": {"privacy": "public"}}


def test_daily_manual_social_uses_one_combined_browser_preview() -> None:
    preview = {
        "playwright_launched": True,
        "playwright_returncode": 0,
        "platforms": [
            {"key": "x", "label": "X", "text": "X draft", "media_path": "x.png"},
            {"key": "facebook", "label": "Facebook", "text": "Facebook draft", "media_path": "facebook.png"},
        ],
    }
    # The one-click flow must use the combined browser helper, not the legacy
    # clipboard-only X/Facebook functions. This source-level contract keeps the
    # regression test side-effect free.
    source = app.one_click_daily_upload.__code__
    assert "social_post_preview" in source.co_names
    assert "manual_x_assist" not in source.co_names
    assert "manual_facebook_assist" not in source.co_names
    assert {item["key"] for item in preview["platforms"]} == {"x", "facebook"}


def test_final_buffer_payload_includes_instagram_post_type() -> None:
    captured = {}

    def fake_graphql(_query, variables):
        captured.update(variables)
        return {"data": {"createPost": {"post": {"id": "dry-run"}}}}

    with (
        patch.object(app, "buffer_asset_for_file", return_value={"image": {"url": "https://example.invalid/post.png"}}),
        patch.object(app, "verify_public_media_url", return_value=None),
        patch.object(app, "buffer_channel_service", return_value="instagram"),
        patch.object(app, "buffer_graphql", side_effect=fake_graphql),
    ):
        app.create_buffer_post("instagram-channel", "Test", ["post.png"], metadata={})

    instagram = captured["input"]["metadata"]["instagram"]
    assert instagram["type"] == "post"
    assert instagram["shouldShareToFeed"] is True


def test_buffer_dry_run_route_is_allowed() -> None:
    source = app.Handler.do_POST.__code__
    constants = set()

    def collect(value):
        if isinstance(value, str):
            constants.add(value)
        elif isinstance(value, tuple):
            for item in value:
                collect(item)

    for constant in source.co_consts:
        collect(constant)
    assert "/api/buffer-dry-run" in constants


def test_x_preview_verifies_composer_text() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = app.write_manual_posts_playwright_script(
            Path(temp_dir),
            [
                {
                    "key": "x",
                    "label": "X",
                    "url": "https://x.com/compose/post",
                    "text": "Verified X preview",
                    "media_path": "",
                }
            ],
        )
        source = script_path.read_text(encoding="utf-8")
    assert "await target.fill(text" in source
    assert "X composer verification failed" in source
    assert "verified: true" in source
    assert "X composer opened, but the post text could not be populated and verified" in source


def main() -> None:
    tests = [
        test_regular_instagram_post_gets_required_type,
        test_instagram_video_gets_reel_type,
        test_explicit_instagram_story_is_preserved,
        test_non_instagram_metadata_is_unchanged,
        test_daily_manual_social_uses_one_combined_browser_preview,
        test_final_buffer_payload_includes_instagram_post_type,
        test_buffer_dry_run_route_is_allowed,
        test_x_preview_verifies_composer_text,
    ]
    for test in tests:
        test()
    print(f"daily post delivery regression: {len(tests)} passed")


if __name__ == "__main__":
    main()
