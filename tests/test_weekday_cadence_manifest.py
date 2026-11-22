"""Step 1: daily-social manifest schema, relative media, posted field preservation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.weekday_cadence_config import WeekdayCadenceConfig
from tools.weekday_cadence_manifest import (
    CadenceItem,
    ManifestError,
    assert_relative_media,
    build_manifest,
    copy_media_file,
    item_id,
    load_manifest,
    merge_posted_fields,
    save_day_bundle,
    unique_media_name,
)


def _item(**overrides) -> CadenceItem:
    data = dict(
        id="EN-facebook",
        platform="facebook",
        novel="EN",
        source_chapter=142,
        source_platform="patreon",
        caption="A hook.",
        media=["media/EN-still.png"],
        status="ready",
        hold_reason=None,
        posted_url="",
        posted_at="",
    )
    data.update(overrides)
    return CadenceItem(**data)


def test_item_id_format():
    assert item_id("en", "Facebook") == "EN-facebook"


def test_rejects_absolute_media_paths():
    with pytest.raises(ManifestError):
        assert_relative_media([r"C:\Users\David\Documents\still.png"])
    with pytest.raises(ManifestError):
        assert_relative_media(["/tmp/still.png"])
    with pytest.raises(ManifestError):
        assert_relative_media(["../secret.png"])
    assert assert_relative_media(["media/EN-still.png"]) == ["media/EN-still.png"]


def test_build_manifest_schema_and_x_status(tmp_path: Path):
    cfg = WeekdayCadenceConfig()
    items = [
        _item(id="EN-facebook", platform="facebook", status="ready"),
        _item(id="EN-instagram", platform="instagram", status="ready"),
        _item(id="EN-x", platform="x", status="awaiting_david_post", caption="X copy"),
        _item(id="EN-tiktok", platform="tiktok", status="held", hold_reason="DRY_RUN:CLIP_STUBBED", media=[]),
    ]
    payload = build_manifest(
        target_date="2026-11-23",
        target_weekday="Monday",
        items=items,
        config=cfg,
        generated_at="2026-11-21T20:00:00-07:00",
        approval_deadline="2026-11-22T18:00:00-07:00",
        source_commit="603cbeb",
    )
    assert payload["schemaVersion"] == 1
    assert payload["manifestId"] == "cadence-2026-11-23"
    assert payload["timezone"] == "America/Phoenix"
    assert payload["config"]["publish_generated_media"] is False
    assert payload["config"]["chapter_source"] == "patreon"
    assert payload["summary"]["awaiting_david_post"] == 1
    assert payload["summary"]["held"] == 1
    assert payload["status"] == "partial"
    x_item = next(row for row in payload["items"] if row["id"] == "EN-x")
    assert x_item["status"] == "awaiting_david_post"
    assert x_item["posted_url"] == ""
    assert x_item["posted_at"] == ""
    for row in payload["items"]:
        for name in row["media"]:
            assert not Path(name).is_absolute()


def test_rerun_preserves_filled_posted_fields(tmp_path: Path):
    cfg = WeekdayCadenceConfig()
    first = [
        _item(id="EN-facebook", platform="facebook", status="ready", posted_url="https://facebook.example/p/1", posted_at="2026-11-23T09:15:00-07:00"),
        _item(id="EN-x", platform="x", status="awaiting_david_post"),
    ]
    payload = build_manifest(
        target_date="2026-11-23",
        target_weekday="Monday",
        items=first,
        config=cfg,
        generated_at="2026-11-22T22:00:00-07:00",
        approval_deadline="2026-11-22T18:00:00-07:00",
    )
    saved = save_day_bundle(tmp_path, payload)
    rebuilt = [
        _item(id="EN-facebook", platform="facebook", status="ready", caption="New copy", posted_url="", posted_at=""),
        _item(id="EN-x", platform="x", status="awaiting_david_post", caption="New x"),
    ]
    incoming = build_manifest(
        target_date="2026-11-23",
        target_weekday="Monday",
        items=rebuilt,
        config=cfg,
        generated_at="2026-11-22T23:00:00-07:00",
        approval_deadline="2026-11-22T18:00:00-07:00",
    )
    merged = save_day_bundle(tmp_path, incoming, existing=saved)
    fb = next(row for row in merged["items"] if row["id"] == "EN-facebook")
    x_item = next(row for row in merged["items"] if row["id"] == "EN-x")
    assert fb["caption"] == "New copy"
    assert fb["posted_url"] == "https://facebook.example/p/1"
    assert fb["posted_at"] == "2026-11-23T09:15:00-07:00"
    assert x_item["posted_url"] == ""
    assert x_item["posted_at"] == ""
    reloaded = load_manifest(tmp_path / "manifest.json")
    assert reloaded["items"][0]["posted_url"] == "https://facebook.example/p/1"
    assert (tmp_path / "manifest.md").is_file()
    assert (tmp_path / "manifest.csv").is_file()


def test_copy_media_uses_relative_names(tmp_path: Path):
    source = tmp_path / "src.png"
    source.write_bytes(b"png")
    day = tmp_path / "day"
    used: set[str] = set()
    name = unique_media_name(source, novel="EN", role="still", used=used)
    copied = copy_media_file(source, day, name)
    assert copied == "media/EN-still.png"
    assert (day / "media" / "EN-still.png").is_file()
    assert not Path(copied).is_absolute()
