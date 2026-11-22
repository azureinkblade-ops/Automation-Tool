"""Step 2: chapter picker uses verified-live records; Patreon default; overrides."""

from __future__ import annotations

import json
from pathlib import Path

from tools.weekday_cadence import newest_verified_chapter, pick_chapters
from tools.weekday_cadence_config import WeekdayCadenceConfig
from tools.weekday_cadence_overrides import (
    empty_override_document,
    load_patreon_live_overrides,
    parse_override_entry,
)


def records(*rows: tuple[str, int, dict]) -> dict:
    chapters = {}
    for abbr, chapter, flags in rows:
        chapters[f"{abbr}-{chapter}"] = {"abbr": abbr, "chapter": chapter, **flags}
    return {"chapters": chapters}


def test_default_source_is_patreon():
    assert WeekdayCadenceConfig().chapter_source == "patreon"


def test_newest_patreon_exists_wins():
    payload = records(
        ("EN", 137, {"patreonExists": True}),
        ("EN", 138, {"patreonExists": True}),
        ("EN", 140, {"patreonExists": False}),
        ("HA", 93, {"patreonExists": True}),
    )
    pick = newest_verified_chapter("EN", payload, source="patreon")
    assert pick.verified is True
    assert pick.chapter == 138
    assert pick.source_platform == "patreon"


def test_unverified_patreon_holds_instead_of_guessing():
    payload = records(
        ("EN", 140, {"patreonExists": False, "postedToPatreon": True}),
        ("EN", 139, {"royalRoadExists": True}),
    )
    pick = newest_verified_chapter("EN", payload, source="patreon")
    assert pick.verified is False
    assert pick.chapter is None
    assert pick.hold_reason == "CHAPTER_SOURCE_UNVERIFIED:patreon"


def test_royal_road_option_requires_explicit_flag():
    payload = records(
        ("HP", 148, {"royalRoadExists": True, "patreonExists": False}),
        ("HP", 150, {"patreonExists": True}),
    )
    pick = newest_verified_chapter("HP", payload, source="royal_road")
    assert pick.verified is True
    assert pick.chapter == 148
    # Does not infer from a schedule cap or from a higher Patreon-only chapter.
    cfg = WeekdayCadenceConfig(chapter_source="royal_road")
    picks = pick_chapters(payload, cfg)
    assert picks["HP"].chapter == 148


def test_override_beats_ledger_not_posted(tmp_path: Path):
    payload = records(
        ("EN", 138, {"patreonExists": True}),
        ("EN", 140, {"patreonExists": False}),
    )
    override_file = tmp_path / "patreon_live_overrides.json"
    override_file.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "entries": [
                    {
                        "chapter_id": "EN-140",
                        "post_url": "https://www.patreon.com/posts/173664094",
                        "verified_at": "2026-11-21T18:00:00-07:00",
                        "verified_by": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    overrides = load_patreon_live_overrides(override_file)
    pick = newest_verified_chapter("EN", payload, source="patreon", overrides=overrides)
    assert pick.verified is True
    assert pick.chapter == 140


def test_empty_or_incomplete_override_keeps_ledger(tmp_path: Path):
    payload = records(("HA", 93, {"patreonExists": True}), ("HA", 99, {"patreonExists": False}))
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps(empty_override_document()), encoding="utf-8")
    assert load_patreon_live_overrides(empty) == []
    pick = newest_verified_chapter(
        "HA", payload, source="patreon", overrides=load_patreon_live_overrides(empty)
    )
    assert pick.chapter == 93

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "entries": [
                    {"chapter_id": "HA-99", "post_url": "", "verified_at": "", "verified_by": ""}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert parse_override_entry({"chapter_id": "HA-99"}) is None
    pick2 = newest_verified_chapter(
        "HA", payload, source="patreon", overrides=load_patreon_live_overrides(incomplete)
    )
    assert pick2.chapter == 93


def test_missing_records_hold_all_novels():
    cfg = WeekdayCadenceConfig()
    picks = pick_chapters(None, cfg)
    assert set(picks) == {"EN", "HP", "HA", "SF"}
    assert all(not pick.verified and pick.chapter is None for pick in picks.values())
