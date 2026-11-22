"""Step 6: dry-run runner writes a self-contained daily-social folder without GPU work."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from tools.weekday_cadence import next_weekday
from tools.weekday_cadence_config import WeekdayCadenceConfig
from tools.weekday_cadence_runner import main, run_cadence


def test_next_weekday_from_saturday_is_monday():
    assert next_weekday(date(2026, 11, 21)).isoformat() == "2026-11-23"


def test_dry_run_writes_relative_manifest_and_stubs_clips(tmp_path: Path):
    still = tmp_path / "en.png"
    still.write_bytes(b"png")
    records = {
        "chapters": {
            "EN-138": {"abbr": "EN", "chapter": 138, "patreonExists": True},
            "HP-148": {"abbr": "HP", "chapter": 148, "patreonExists": True},
        }
    }
    from tools.weekday_cadence_captions import parse_copy_bank

    cfg = WeekdayCadenceConfig(novels=("EN", "HP"), chapter_pick="newest_live")
    bank = parse_copy_bank("""# Weekday copy bank
- Items tagged **[APPROVAL: needs David's approval for media]** show Kai, Kael, Liang or Jarek on screen.

## Day 1 (Week 1, Monday)
**FB/IG post** [source EN-138]
- Text: A street after rain. Eternal Nexus chapter 138 is live now on Patreon. Link in bio.

**TikTok** [source EN-138]
- Caption: A street after rain. Chapter 138 of Eternal Nexus is live now on Patreon. Link in bio.

**X post** [source EN-138]
a street after rain. Eternal Nexus ch 138 is up on Patreon, link in bio #webnovel #cultivation

**FB/IG post** [source HP-148]
- Text: A lamp still burns. Chapter 148 of The Hundredfold Path is live now on Patreon. Link in bio.

**TikTok** [source HP-148]
- Caption: A lamp still burns. Chapter 148 of The Hundredfold Path is live now on Patreon. Link in bio.

**X post** [source HP-148]
a lamp still burns. Hundredfold Path ch 148 is up on Patreon, link in bio #webnovel #cultivation
""")
    payload = run_cadence(
        target=date(2026, 11, 23),
        stage="pack",
        dry_run=True,
        config=cfg,
        out_root=tmp_path,
        records=records,
        source_commit="testsha",
        stills={"EN": still},
        copy_bank=bank,
    )
    day = tmp_path / "daily-social" / "2026-11-23"
    assert (day / "manifest.json").is_file()
    assert (day / "manifest.md").is_file()
    assert (day / "manifest.csv").is_file()
    data = json.loads((day / "manifest.json").read_text(encoding="utf-8"))
    assert data["targetDate"] == "2026-11-23"
    assert data["config"]["publish_generated_media"] is False
    assert data["config"]["chapter_source"] == "patreon"
    ids = {item["id"]: item for item in data["items"]}
    assert ids["EN-x"]["status"] == "awaiting_david_post"
    assert ids["EN-x"]["hold_reason"] == "AWAITING_DAVID_POST"
    assert ids["EN-x"]["media"] == []
    assert ids["EN-tiktok"]["status"] == "held"
    assert ids["EN-tiktok"]["hold_reason"] == "DRY_RUN:CLIP_STUBBED"
    assert ids["EN-facebook"]["source_chapter"] == 138
    assert ids["EN-facebook"]["source_platform"] == "patreon"
    assert ids["EN-facebook"]["status"] == "ready"
    assert ids["EN-instagram"]["status"] == "ready"
    assert ids["HP-facebook"]["source_chapter"] == 148
    assert ids["HP-facebook"]["status"] == "held"
    assert ids["HP-facebook"]["hold_reason"] == "MEDIA_REQUIRED_MISSING"
    assert ids["HP-instagram"]["status"] == "held"
    assert ids["HP-instagram"]["hold_reason"] == "MEDIA_REQUIRED_MISSING"
    media = ids["EN-facebook"]["media"]
    assert media == ids["EN-instagram"]["media"]
    assert media == ["media/EN-still.png"]
    for item in data["items"]:
        if item["status"] != "ready":
            assert str(item.get("hold_reason") or "").strip(), item
    assert not any(p.startswith("/") or (len(p) > 1 and p[1] == ":") for item in data["items"] for p in item["media"])
    assert (day / "media" / "EN-still.png").is_file()
    # HA and SF were not in this config; EN/HP only -> 8 items
    assert data["summary"]["expected"] == 8
    # CLI smoke (also dry-run, no GPU)
    exit_code = main(
        [
            "--date",
            "2026-11-24",
            "--dry-run",
            "--root",
            str(tmp_path),
            "--app-root",
            str(tmp_path),
            "--source-commit",
            "cli",
        ]
    )
    assert exit_code == 0
    # 2026-11-24 is Tuesday; no records under tmp app-root -> items held unverified
    tuesday = json.loads((tmp_path / "daily-social" / "2026-11-24" / "manifest.json").read_text(encoding="utf-8"))
    assert tuesday["targetWeekday"] == "Tuesday"
    assert all(item["status"] == "held" for item in tuesday["items"])
