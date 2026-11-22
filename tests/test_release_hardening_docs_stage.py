"""Release hardening (CPU only: no Docs, no DB, no Patreon/Royal Road, no subprocess).

1. make_royal_road_chapter_pack: a failed Docs read no longer falls back to an existing royal-road.txt.
   It raises RoyalRoadDocsReadFailed("DOCS_READ_FAILED: ..."), and release_automation_worker turns that into
   a blocked job with that reason (no retry loop, nothing posted).
2. patreon_stage_text_file: the tier stage file is always rebuilt from patreon.txt (else patreon-note.txt)
   instead of reusing an older copy. Stage files carry no tier-specific text (tier/title/dates live in the
   draft payload), so a plain copy is the faithful rebuild.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

app = pytest.importorskip("app")


# ---------- 1. Royal Road: failed Docs read holds, never reuses the old body ----------

def _old_rr_pack(tmp_path: Path) -> Path:
    folder = tmp_path / "royal-road-en-141"
    folder.mkdir(parents=True)
    (folder / "royal-road.txt").write_text('OLD BODY Grip. " He', encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps({"kind": "royal-road", "revision": {"contentHash": "old"}}), encoding="utf-8")
    return folder


def _docs_down(*_a, **_k):
    raise RuntimeError("GitHub API timed out")


def test_failed_docs_read_raises_hold_and_leaves_old_file_unused(tmp_path, monkeypatch):
    folder = _old_rr_pack(tmp_path)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    monkeypatch.setattr(app, "SOCIAL_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(app, "docs_chapter_text", _docs_down)
    with pytest.raises(app.RoyalRoadDocsReadFailed) as info:
        app.make_royal_road_chapter_pack("EN", 141)
    assert str(info.value).startswith("DOCS_READ_FAILED: ")
    assert "GitHub API timed out" in str(info.value)
    # Old pack is neither returned nor rewritten (no "applied" result built from it).
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


def test_docs_read_failed_reason_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SOCIAL_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(app, "docs_chapter_text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x" * 5000)))
    with pytest.raises(app.RoyalRoadDocsReadFailed) as info:
        app.make_royal_road_chapter_pack("EN", 141)
    assert len(str(info.value)) <= len("DOCS_READ_FAILED: ") + 300


def test_release_job_does_not_reach_posting_when_docs_fail(tmp_path, monkeypatch):
    _old_rr_pack(tmp_path)
    monkeypatch.setattr(app, "SOCIAL_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(app, "docs_chapter_text", _docs_down)
    monkeypatch.setattr(app, "_release_job_already_complete", lambda job: False)
    touched = []
    monkeypatch.setattr(app, "royal_road_release_spec", lambda *a, **k: touched.append("spec"))
    monkeypatch.setattr(app, "write_manual_posts_playwright_script", lambda *a, **k: touched.append("script"))
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: touched.append("subprocess"))
    monkeypatch.setattr(app.automation_db, "update_release_job", lambda *a, **k: touched.append("db"))
    job = {"jobId": "j1", "abbr": "EN", "chapter": 141, "stage": "royal_road", "assignmentKey": "EN-141", "scheduledFor": "2026-12-01"}
    with pytest.raises(app.RoyalRoadDocsReadFailed):
        app.run_release_automation_job(job)
    assert touched == []


def _run_worker_once(monkeypatch, tmp_path, exc: Exception, attempt_count: int = 0):
    job = {"jobId": "j1", "abbr": "EN", "chapter": 141, "stage": "royal_road", "attemptCount": attempt_count, "maxAttempts": 3}
    queue = [job]
    updates = []
    monkeypatch.setattr(app, "ROOT", tmp_path)
    monkeypatch.setattr(app, "_save_release_automation_runtime", lambda **k: None)
    monkeypatch.setattr(app.automation_db, "recover_stale_release_jobs", lambda *a, **k: None)
    monkeypatch.setattr(app.automation_db, "claim_next_release_job", lambda *a, **k: queue.pop() if queue else None)
    monkeypatch.setattr(app.automation_db, "update_release_job", lambda root, job_id, status, **f: updates.append((job_id, status, f)))
    def boom(_job):
        raise exc
    monkeypatch.setattr(app, "run_release_automation_job", boom)
    app.RELEASE_AUTOMATION_STOP.clear()
    app.RELEASE_AUTOMATION_PAUSE.clear()
    app.release_automation_worker("test-worker", max_jobs=1)
    return updates


def test_worker_blocks_docs_read_failed_without_retry(tmp_path, monkeypatch):
    updates = _run_worker_once(monkeypatch, tmp_path, app.RoyalRoadDocsReadFailed("DOCS_READ_FAILED: GitHub API timed out"))
    assert len(updates) == 1
    job_id, status, fields = updates[0]
    assert (job_id, status) == ("j1", "blocked")
    assert fields["nextAttemptAt"] == ""
    assert fields["lastError"].startswith("DOCS_READ_FAILED: ")


def test_worker_still_retries_ordinary_errors(tmp_path, monkeypatch):
    updates = _run_worker_once(monkeypatch, tmp_path, RuntimeError("Royal Road page did not load"))
    assert [u[1] for u in updates] == ["retrying"]
    assert updates[0][2]["nextAttemptAt"]


# ---------- 2. Patreon stage file is always rebuilt from its source ----------

@pytest.mark.parametrize("stage, name", [("inner_disciple", "patreon-inner-disciple.txt"), ("path_initiate", "patreon-path-initiate.txt")])
def test_stale_stage_file_is_overwritten_from_patreon_txt(tmp_path, stage, name):
    (tmp_path / "patreon.txt").write_text('\nNEW body Grip." He\n\n', encoding="utf-8")
    (tmp_path / name).write_text('OLD body Grip. " He\n', encoding="utf-8")
    path = app.patreon_stage_text_file(tmp_path, stage)
    assert path == tmp_path / name
    assert path.read_text(encoding="utf-8") == 'NEW body Grip." He\n'


def test_missing_stage_file_is_created(tmp_path):
    (tmp_path / "patreon.txt").write_text("Body", encoding="utf-8")
    assert app.patreon_stage_text_file(tmp_path, "inner_disciple").read_text(encoding="utf-8") == "Body\n"


def test_patreon_txt_wins_over_note_and_note_is_fallback(tmp_path):
    (tmp_path / "patreon-note.txt").write_text("Note teaser", encoding="utf-8")
    (tmp_path / "patreon-inner-disciple.txt").write_text("stale", encoding="utf-8")
    assert app.patreon_stage_text_file(tmp_path, "inner_disciple").read_text(encoding="utf-8") == "Note teaser\n"
    (tmp_path / "patreon.txt").write_text("Chapter body", encoding="utf-8")
    assert app.patreon_stage_text_file(tmp_path, "inner_disciple").read_text(encoding="utf-8") == "Chapter body\n"


def test_no_source_keeps_existing_stage_file(tmp_path):
    (tmp_path / "patreon-path-initiate.txt").write_text("only copy", encoding="utf-8")
    path = app.patreon_stage_text_file(tmp_path, "path_initiate")
    assert path.read_text(encoding="utf-8") == "only copy"


def test_stage_files_carry_no_tier_specific_text(tmp_path):
    """Tier, title and dates are added by patreon_draft_payload, not stored in the stage file, so both tiers'
    stage files are the same plain copy of patreon.txt."""
    (tmp_path / "patreon.txt").write_text("Same chapter body", encoding="utf-8")
    inner = app.patreon_stage_text_file(tmp_path, "inner_disciple").read_text(encoding="utf-8")
    path = app.patreon_stage_text_file(tmp_path, "path_initiate").read_text(encoding="utf-8")
    assert inner == path == "Same chapter body\n"
