"""Unit tests for ledger status split + controller reconcile preference."""
from __future__ import annotations

from tools.ledger_status import (
    compute_ledger_status_from_structured,
    preflight_chapter_gate,
    select_next_missing_chapter,
)
from tools.production_orchestration_live_wiring import (
    next_inventory_from_ledger_status,
    report_ledger_status,
)


def _ha_112_113_stub():
    return compute_ledger_status_from_structured(
        novel_id="HA",
        abbr="HA",
        materialized_chapters=[110, 111, 112],
        ledger_entries=[
            {"chapter": 112, "written": True, "writePending": False},
            {
                "chapter": 113,
                "written": False,
                "writePending": True,
                "writeMode": "codex_session",
            },
        ],
        published_chapters=[],
    )


def test_split_reports_materialized_reserved_published_none():
    status = _ha_112_113_stub()
    assert status.latest_materialized_chapter == 112
    assert status.latest_reserved_chapter == 113
    assert status.latest_published_chapter is None
    assert status.write_pending_without_materialization == [113]
    packet = report_ledger_status(status)
    assert packet["LATEST_MATERIALIZED_CHAPTER"] == 112
    assert packet["LATEST_RESERVED_CHAPTER"] == 113
    assert packet["LATEST_PUBLISHED_CHAPTER"] == 0
    assert packet["ledger_max_collapsed"] is False
    # Must expose all three keys — never a lone ledger_max
    assert "LATEST_MATERIALIZED_CHAPTER" in packet
    assert "LATEST_RESERVED_CHAPTER" in packet
    assert "LATEST_PUBLISHED_CHAPTER" in packet


def test_controller_prefers_reconcile_write_pending_stub():
    status = _ha_112_113_stub()
    sel = select_next_missing_chapter(status)
    assert sel.mode == "RECONCILE"
    assert sel.chapter_number == 113
    assert sel.chapter_id == "HA-113"
    assert sel.availability == "RESERVED_WRITE_PENDING"
    item = next_inventory_from_ledger_status(status, novel_id="HA")
    assert item is not None
    assert item.chapter_id == "HA-113"


def test_allocate_preflight_rejects_reservation_as_not_clean():
    status = _ha_112_113_stub()
    gate = preflight_chapter_gate(status, candidate_chapter=113, mode="ALLOCATE")
    assert gate["LEDGER_CLEAN_FOR_ALLOCATE"] == "NO"
    assert gate["CHAPTER_ALREADY_EXISTS"] == "YES"
    assert gate["CHAPTER_AVAILABILITY"] == "RESERVED_WRITE_PENDING"
    assert gate["OK"] is False


def test_reconcile_preflight_allows_reservation_without_claiming_clean_allocate():
    status = _ha_112_113_stub()
    gate = preflight_chapter_gate(status, candidate_chapter=113, mode="RECONCILE")
    assert gate["OK"] is True
    assert gate["CHAPTER_ALREADY_EXISTS"] == "NO"
    assert gate["LEDGER_CLEAN_FOR_ALLOCATE"] == "NO"  # still not free for allocate
    assert gate["CHAPTER_AVAILABILITY"] == "RESERVED_WRITE_PENDING"


def test_allocate_after_no_pending_goes_to_max_plus_one():
    status = compute_ledger_status_from_structured(
        novel_id="HA",
        abbr="HA",
        materialized_chapters=[112],
        ledger_entries=[{"chapter": 112, "written": True, "writePending": False}],
        published_chapters=[],
    )
    sel = select_next_missing_chapter(status)
    assert sel.mode == "ALLOCATE"
    assert sel.chapter_number == 113
    gate = preflight_chapter_gate(status, candidate_chapter=113, mode="ALLOCATE")
    assert gate["LEDGER_CLEAN_FOR_ALLOCATE"] == "YES"
    assert gate["CHAPTER_ALREADY_EXISTS"] == "NO"


def test_written_wins_over_stale_write_pending_stub():
    """Manual/written canon beats stale writePending — fail closed vs promote."""
    status = compute_ledger_status_from_structured(
        novel_id="HA",
        abbr="HA",
        materialized_chapters=[110, 111, 112, 113],  # novel_chapters written row
        ledger_entries=[
            {"chapter": 112, "written": True, "writePending": False},
            {
                "chapter": 113,
                "written": False,
                "writePending": True,
                "writeMode": "codex_session",
            },
        ],
        published_chapters=[],
    )
    assert status.latest_materialized_chapter == 113
    assert status.write_pending_without_materialization == []
    assert status.chapter_availability(113) == "MATERIALIZED"
    sel = select_next_missing_chapter(status, novel_id="HA")
    assert sel.mode == "ALLOCATE"
    assert sel.chapter_number == 114
    gate = preflight_chapter_gate(status, candidate_chapter=113, mode="RECONCILE")
    assert gate["OK"] is False
    assert gate["CHAPTER_ALREADY_EXISTS"] == "YES"
    assert gate["CHAPTER_AVAILABILITY"] == "MATERIALIZED"


def test_ledger_written_true_clears_same_row_write_pending():
    status = compute_ledger_status_from_structured(
        novel_id="HA",
        abbr="HA",
        materialized_chapters=[112],
        ledger_entries=[
            {
                "chapter": 113,
                "written": True,
                "writePending": True,  # stale flag left behind
                "writeMode": "manual_chatgpt",
            },
        ],
        published_chapters=[],
    )
    assert status.latest_materialized_chapter == 113
    assert status.write_pending_without_materialization == []
    assert status.chapter_availability(113) == "MATERIALIZED"


def test_flag_true_rejects_string_false():
    from tools.ledger_status import _flag_true

    assert _flag_true(True) is True
    assert _flag_true("true") is True
    assert _flag_true("false") is False
    assert _flag_true("0") is False
    assert _flag_true(0) is False
    assert _flag_true(1) is True


def test_db_nc_written_wins_over_ledger_pending_stub(tmp_path):
    import json
    import sqlite3
    from tools.ledger_status import compute_ledger_status_from_db

    db = tmp_path / "t.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        """
        CREATE TABLE novel_chapters (
          chapter_id TEXT, novel_id TEXT, chapter_number INTEGER,
          payload_json TEXT,
          patreon_inner_exists INTEGER DEFAULT 0,
          patreon_path_exists INTEGER DEFAULT 0,
          royal_road_exists INTEGER DEFAULT 0
        );
        CREATE TABLE chapter_ledger (
          ledger_key TEXT, abbr TEXT, chapter INTEGER, payload_json TEXT
        );
        """
    )
    nc_payload = {
        "written": True,
        "writePending": False,
        "writeMode": "manual_chatgpt",
    }
    # Stale ledger stub still claims writePending
    ledger_stub = {
        "written": False,
        "writePending": True,
        "writeMode": "codex_session",
    }
    con.execute(
        "INSERT INTO novel_chapters VALUES (?,?,?,?,0,0,0)",
        ("HA-113", "HA", 113, json.dumps(nc_payload)),
    )
    con.execute(
        "INSERT INTO novel_chapters VALUES (?,?,?,?,0,0,0)",
        ("HA-112", "HA", 112, json.dumps({"written": True, "writePending": False})),
    )
    con.execute(
        "INSERT INTO chapter_ledger VALUES (?,?,?,?)",
        ("HA-113", "HA", 113, json.dumps(ledger_stub)),
    )
    con.execute(
        "INSERT INTO chapter_ledger VALUES (?,?,?,?)",
        ("HA-112", "HA", 112, json.dumps({"written": True, "writePending": False})),
    )
    con.commit()
    con.close()

    status = compute_ledger_status_from_db(db, novel_id="HA", abbr="HA")
    assert status.latest_materialized_chapter == 113
    assert status.write_pending_without_materialization == []
    assert status.chapter_availability(113) == "MATERIALIZED"


def test_db_nc_pending_stub_without_written_is_reserved(tmp_path):
    import json
    import sqlite3
    from tools.ledger_status import compute_ledger_status_from_db

    db = tmp_path / "t2.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        """
        CREATE TABLE novel_chapters (
          chapter_id TEXT, novel_id TEXT, chapter_number INTEGER,
          payload_json TEXT,
          patreon_inner_exists INTEGER DEFAULT 0,
          patreon_path_exists INTEGER DEFAULT 0,
          royal_road_exists INTEGER DEFAULT 0
        );
        CREATE TABLE chapter_ledger (
          ledger_key TEXT, abbr TEXT, chapter INTEGER, payload_json TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO novel_chapters VALUES (?,?,?,?,0,0,0)",
        ("HA-112", "HA", 112, json.dumps({"written": True, "writePending": False})),
    )
    con.execute(
        "INSERT INTO novel_chapters VALUES (?,?,?,?,0,0,0)",
        (
            "HA-113",
            "HA",
            113,
            json.dumps({"written": False, "writePending": True, "writeMode": "codex_session"}),
        ),
    )
    con.execute(
        "INSERT INTO chapter_ledger VALUES (?,?,?,?)",
        ("HA-112", "HA", 112, json.dumps({"written": True, "writePending": False})),
    )
    con.execute(
        "INSERT INTO chapter_ledger VALUES (?,?,?,?)",
        (
            "HA-113",
            "HA",
            113,
            json.dumps({"written": False, "writePending": True, "writeMode": "codex_session"}),
        ),
    )
    con.commit()
    con.close()

    status = compute_ledger_status_from_db(db, novel_id="HA", abbr="HA")
    assert status.latest_materialized_chapter == 112
    assert status.latest_reserved_chapter == 113
    assert status.write_pending_without_materialization == [113]
    assert status.chapter_availability(113) == "RESERVED_WRITE_PENDING"

