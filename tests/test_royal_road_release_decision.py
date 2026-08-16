from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

import app


def test_changed_patreon_only_chapter_uses_create_new_royal_road_path() -> None:
    decision, _ = app.decision_from_status(
        {"patreonExists": True, "royalRoadExists": False, "royalRoadDue": True},
        {"changed": True},
    )

    assert decision == "royal_road_ready"


def test_changed_existing_royal_road_chapter_uses_update_path() -> None:
    decision, _ = app.decision_from_status(
        {"patreonExists": True, "royalRoadExists": True, "royalRoadDue": True},
        {"changed": True},
    )

    assert decision == "update_existing"


def test_overdue_new_chapter_uses_publish_now_path() -> None:
    folder = Path(tempfile.mkdtemp())
    (folder / "metadata.json").write_text(
        json.dumps({"abbr": "HA", "chapter": 66, "title": "Chapter 66"}),
        encoding="utf-8",
    )
    (folder / "royal-road.txt").write_text("Chapter 66\n\nBody", encoding="utf-8")
    (folder / "royal-road-post-note.txt").write_text("Note", encoding="utf-8")

    spec = app.royal_road_release_spec(folder, scheduled_release="2000-01-01")

    assert spec["scheduled_release"] == ""
    assert spec["edit_existing"] is False
    assert app.actionable_royal_road_release_date("2000-01-01") == ""
    assert app.actionable_royal_road_release_date("2999-01-01") == "2999-01-01"


def test_royal_road_verifier_accepts_publish_now_without_schedule_date() -> None:
    source = inspect.getsource(app.write_manual_posts_playwright_script)

    assert "date: editExisting || !expectedDate || scheduleValue.includes(expectedDate)" in source


def test_missing_live_chapter_opens_royal_road_editor() -> None:
    source = inspect.getsource(app.royal_road_diff_and_edit)

    assert '"not_found"' in source
