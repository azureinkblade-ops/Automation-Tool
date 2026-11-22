"""Step 2: chapter picker uses verified-live records; Patreon default; overrides."""

from __future__ import annotations

import json
from pathlib import Path

from tools.weekday_cadence import (
    is_verified_live,
    load_live_chapter_records,
    newest_verified_chapter,
    pick_chapters,
)
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

def test_ledger_posted_to_patreon_with_post_ids_counts():
    payload = records(
        ("EN", 132, {"patreonExists": True}),
        (
            "EN",
            138,
            {
                "postedToPatreon": True,
                "patreonInnerDisciplePosted": True,
                "patreonPathInitiatePosted": True,
                "patreonInnerDisciplePostId": "170900005",
                "patreonPathInitiatePostId": "170900071",
            },
        ),
        ("EN", 140, {"postedToPatreon": False, "innerDiscipleDate": "2026-10-20"}),
    )
    pick = newest_verified_chapter("EN", payload, source="patreon")
    assert pick.chapter == 138
    assert pick.verified is True
    assert "Inner Disciple" in pick.live_tiers
    assert "Path Initiate" in pick.live_tiers


def test_schedule_dates_alone_are_not_live_evidence():
    payload = records(
        ("EN", 132, {"patreonExists": True}),
        (
            "EN",
            138,
            {
                "innerDiscipleDate": "2026-10-19",
                "pathInitiateDate": "2026-10-26",
                "royalRoadDate": "2026-11-03",
            },
        ),
    )
    pick = newest_verified_chapter("EN", payload, source="patreon")
    assert pick.chapter == 132


def test_posted_flag_without_post_records_is_not_enough():
    payload = records(("EN", 140, {"postedToPatreon": True}))
    pick = newest_verified_chapter("EN", payload, source="patreon")
    assert pick.verified is False
    assert pick.chapter is None


def test_override_supplies_partial_live_tiers():
    payload = records(("EN", 138, {"patreonExists": True}))
    from tools.weekday_cadence_overrides import parse_override_entry

    override = parse_override_entry(
        {
            "chapter_id": "EN-140",
            "verified_at": "2026-11-21T20:45:00-07:00",
            "verified_by": "Product Performance",
            "post_ids": [
                {
                    "id": "173664094",
                    "tier": "Inner Disciple",
                    "post_url": "https://www.patreon.com/posts/173664094",
                }
            ],
            "tiers_live": ["Inner Disciple"],
        }
    )
    assert override is not None
    pick = newest_verified_chapter("EN", payload, source="patreon", overrides=[override])
    assert pick.chapter == 140
    assert list(pick.live_tiers) == ["Inner Disciple"]


def test_load_live_chapter_records_reads_ledger_not_release_status(tmp_path: Path):
    import json
    import sqlite3

    db = tmp_path / "automation_state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE chapter_ledger (ledger_key TEXT, abbr TEXT, chapter INTEGER, payload_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE post_records (automation_record_id TEXT, novel TEXT, chapter TEXT, platform TEXT, live_url TEXT, payload_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE release_status (status_key TEXT, abbr TEXT, chapter INTEGER, payload_json TEXT)"
    )
    conn.execute(
        "INSERT INTO release_status VALUES (?,?,?,?)",
        (
            "GLOBAL",
            "",
            None,
            json.dumps({"chapters": {"EN-132": {"abbr": "EN", "chapter": 132, "patreonExists": True}}}),
        ),
    )
    conn.execute(
        "INSERT INTO chapter_ledger VALUES (?,?,?,?)",
        (
            "EN-138",
            "EN",
            138,
            json.dumps(
                {
                    "abbr": "EN",
                    "chapter": 138,
                    "postedToPatreon": True,
                    "patreonInnerDisciplePosted": True,
                    "patreonPathInitiatePosted": True,
                    "patreonInnerDisciplePostId": "170900005",
                    "patreonPathInitiatePostId": "170900071",
                }
            ),
        ),
    )
    conn.commit()
    conn.close()
    payload = load_live_chapter_records(tmp_path)
    assert payload is not None
    assert payload["source"] == "chapter_ledger"
    pick = newest_verified_chapter("EN", payload, source="patreon")
    assert pick.chapter == 138
    # release_status would have stopped at 132; the loader must not use it.
    assert "EN-132" not in payload["chapters"]

