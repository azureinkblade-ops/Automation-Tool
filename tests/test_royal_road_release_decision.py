from __future__ import annotations

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
