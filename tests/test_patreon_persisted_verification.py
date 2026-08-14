from __future__ import annotations

import tempfile
from pathlib import Path

import app


def test_generated_patreon_helper_requires_persisted_content() -> None:
    root = Path(tempfile.mkdtemp())
    script = app.write_chapter_upload_tabs_playwright_script(
        root,
        [
            {
                "tier_stage": "inner_disciple",
                "title": "Heavenly Ascension System Chapter 84: The Eighth Construct",
                "body": "Expected chapter body",
                "publish_date": "2026-08-20",
                "publish_time": "09:00",
                "tiers": ["Inner Disciple"],
                "media_path": "C:/tmp/ha-84.png",
                "edit_url": "",
                "auto_submit": True,
            }
        ],
    )
    source = script.read_text(encoding="utf-8")

    assert "verifyPersistedPatreonPost" in source
    assert "await page.reload" in source
    assert "checks.title" in source
    assert "checks.body" in source
    assert "checks.tiers" in source
    assert "checks.date" in source
    assert "checks.time" in source
    assert "Chromium date inputs are segmented" in source
    assert "await page.keyboard.press('ArrowLeft')" in source
    assert "failed to set date" in source
    assert "persistedVerification" in source
    assert "verified: Boolean(persistedVerification && persistedVerification.ok)" in source
    assert "page.locator('[role=\"alert\"], [role=\"status\"]')" in source
    assert "page.locator('body').innerText" not in source
