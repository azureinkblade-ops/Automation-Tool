# -*- coding: utf-8 -*-
"""Patreon media identity hold (ENABLE_IDENTITY_PRESERVATION on).

A chapter image that the publish identity gate refuses (or whose check errors) is NOT attached and NOT replaced by another image;
the chapter text still posts; the payload/result records mediaStatus=HELD_IDENTITY; attach_held_patreon_media() re-runs the gate and
only then edits the same post.  Pure Python: no browser, no network, no live Patreon.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import identity_preservation as ip

FLAG = "ENABLE_IDENTITY_PRESERVATION"


def _png(folder: Path, name: str, tag: bytes = b"X") -> Path:
    p = folder / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + tag * 40)
    return p


def _meta(folder: Path, **kw) -> dict:
    data = {"abbr": "HP", "novel": "Hundredfold Path", "chapter": "", **kw}
    (folder / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.setenv("AIVSB_REASONING_ENABLED", "on")
    yield


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    yield


def _approve(p: Path) -> None:
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    pr = ip.build_prior_review_record(image_sha256=sha, character_id="liang", verifier_decision="PASS", human_review_status="APPROVED")
    ip.prior_review_sidecar_path(p).write_text(json.dumps(pr), encoding="utf-8")


def test_01_governed_unapproved_image_is_held(tmp_path, flag_on):
    import app
    meta = _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"GOV")
    hold = app.patreon_media_identity_hold(img, tmp_path, meta)
    assert hold["mediaStatus"] == "HELD_IDENTITY"
    assert "IDENTITY_APPROVAL" in hold["reason"]
    assert hold["imagePath"] == str(img)
    assert hold["sha256"] == hashlib.sha256(img.read_bytes()).hexdigest()
    assert hold["folder"] == str(tmp_path)


def test_02_approved_image_attaches(tmp_path, flag_on):
    import app
    meta = _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"OK")
    _approve(img)
    assert app.patreon_media_identity_hold(img, tmp_path, meta) == {}


def test_03_non_governed_image_attaches(tmp_path, flag_on):
    import app
    meta = _meta(tmp_path, abbr="ZZ", novel="Not Governed")
    img = _png(tmp_path, "banner.png", b"FREE")
    assert app.patreon_media_identity_hold(img, tmp_path, meta) == {}


def test_04_flag_off_changes_nothing(tmp_path, flag_off):
    import app
    meta = _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"GOV")
    assert app.patreon_media_identity_hold(img, tmp_path, meta) == {}


def test_05_gate_error_fails_closed(tmp_path, flag_on, monkeypatch):
    import app
    from tools import aivsb_prompt_provenance as prov
    meta = _meta(tmp_path, abbr="ZZ", novel="Not Governed")  # would pass if the gate worked
    img = _png(tmp_path, "banner.png", b"ERR")

    def boom(*a, **k):
        raise RuntimeError("gate exploded")

    monkeypatch.setattr(prov, "publish_identity_check", boom)
    hold = app.patreon_media_identity_hold(img, tmp_path, meta)
    assert hold["mediaStatus"] == "HELD_IDENTITY"
    assert hold["reason"].startswith("IDENTITY_GATE_ERROR:RuntimeError")


def test_06_no_substitution_when_refused(tmp_path, flag_on):
    import app
    meta = _meta(tmp_path)
    first = _png(tmp_path, "promo-1.png", b"GOV1")       # selected first, unapproved
    other = _png(tmp_path, "promo-2.png", b"GOV2")       # would be approved - must NOT be substituted
    _approve(other)
    media, hold = app.patreon_select_media_with_identity_gate(tmp_path, meta)
    assert media is None
    assert hold["imagePath"] == str(first.resolve()) or Path(hold["imagePath"]).name == "promo-1.png"
    assert Path(hold["imagePath"]).name != "promo-2.png"


def _payload(app, monkeypatch, folder: Path, meta: dict):
    text = folder / "patreon-inner_disciple.txt"
    text.write_text("Chapter text body. " * 20, encoding="utf-8")
    monkeypatch.setattr(app, "patreon_confirmed_existing", lambda *a, **k: (False, ""))
    monkeypatch.setattr(app, "patreon_stage_text_file", lambda *a, **k: text)
    monkeypatch.setattr(app, "ensure_schedule_file", lambda *a, **k: {"chapterReleaseTime": "09:00"})
    monkeypatch.setattr(app, "platform_folder", lambda f: Path(f))
    return app.patreon_draft_payload(str(folder), ignore_existing=True, tier_stage_override="inner_disciple")


def test_07_payload_holds_image_and_keeps_text(tmp_path, flag_on, monkeypatch):
    import app
    meta = _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"GOV")
    p = _payload(app, monkeypatch, tmp_path, meta)
    assert p["body"].startswith("Chapter text body.")          # text still posts
    assert p["media_path"] == "" and p["media_name"] == ""      # nothing attached, nothing substituted
    assert p["media_status"] == "HELD_IDENTITY"
    assert p["media_hold"]["imagePath"] == str(img.resolve()) or Path(p["media_hold"]["imagePath"]).name == "promo-1.png"
    assert p["media_hold"]["sha256"]


def test_08_payload_attaches_approved_image(tmp_path, flag_on, monkeypatch):
    import app
    meta = _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"OK")
    _approve(img)
    p = _payload(app, monkeypatch, tmp_path, meta)
    assert Path(p["media_path"]).name == "promo-1.png" and p["media_status"] == "ATTACH" and p["media_hold"] == {}


def test_09_generated_scripts_relax_media_only_when_held(tmp_path):
    import app
    f1 = tmp_path / "s1"; f1.mkdir()
    s1 = app.write_chapter_upload_tabs_playwright_script(f1, [{"id": "t", "tiers": ["Inner Disciple"], "media_status": "HELD_IDENTITY"}]).read_text(encoding="utf-8")
    # held early-return comes before the generic 'media missing' path, and nothing is clicked/uploaded in that case
    a = s1.index("async function attachMedia(page, draft)")
    assert s1.index("draft.media_status || '') === 'HELD_IDENTITY'", a) < s1.index("'media missing'", a)
    v = s1[s1.index("async function verifyPatreonDraft"):s1.index("async function verifyPersistedPatreonPost")]
    assert "checks.media = heldIdentity ? true : Boolean(row.mediaResult && row.mediaResult.attached && row.mediaReady !== false);" in v
    assert "checks.mediaRelaxed = heldIdentity ? 'HELD_IDENTITY' : '';" in v and "checks.mediaStatus" in v
    pv = s1[s1.index("async function verifyPersistedPatreonPost"):s1.index("async function submitPatreonDraft")]
    assert "checks.media = heldIdentity ? true :" in pv and "mediaStatus: checks.mediaStatus" in pv
    assert "row.mediaStatus = String(draft.media_status || '') === 'HELD_IDENTITY' ? 'HELD_IDENTITY'" in s1
    assert "row.mediaHold = row.mediaStatus === 'HELD_IDENTITY'" in s1
    # the other required checks are untouched
    assert "const required = ['canonicalPostUrl', 'title', 'body', 'paidAccess', 'tierAccess', 'tiers', 'date', 'time', 'media']" in pv
    f2 = tmp_path / "s2"; f2.mkdir()
    s2 = app.write_patreon_draft_playwright_script(f2, {"id": "t", "tiers": ["Inner Disciple"], "access_level": "paid"}).read_text(encoding="utf-8")
    assert "readback," in s2 and "paidChecked: tierState.paid.checked" in s2 and "mediaStatus," in s2
    assert s2.index("draft.media_status || '') === 'HELD_IDENTITY'") < s2.index("'media missing'")


def _job(img: Path, folder: Path, **kw):
    hold = {"mediaStatus": "HELD_IDENTITY", "reason": "x", "imagePath": str(img), "sha256": "0" * 64, "folder": str(folder)}
    return {"jobId": "job123", "stage": "inner_disciple", "status": "verified", "mediaStatus": "HELD_IDENTITY", "mediaHold": hold,
            "editUrl": "https://www.patreon.com/posts/some-title-173664094/edit", "completedAt": "c", "verifiedAt": "v", **kw}


def _guard_no_side_effects(app, monkeypatch):
    def nope(*a, **k):
        raise AssertionError("must not run")
    monkeypatch.setattr(app.subprocess, "run", nope)
    monkeypatch.setattr(app.automation_db, "update_release_job", nope)


def test_10_attach_step_stays_held_without_approval(tmp_path, flag_on, monkeypatch):
    import app
    _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"GOV")
    monkeypatch.setattr(app.automation_db, "list_release_jobs", lambda *a, **k: [_job(img, tmp_path)])
    _guard_no_side_effects(app, monkeypatch)
    out = app.attach_held_patreon_media("job123")
    assert out["ok"] is False and out["attached"] is False and out["stillHeld"] is True and out["mediaStatus"] == "HELD_IDENTITY"


def test_11_attach_step_after_approval_edits_same_post(tmp_path, flag_on, monkeypatch):
    import app
    _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"OK")
    _approve(img)
    monkeypatch.setattr(app.automation_db, "list_release_jobs", lambda *a, **k: [_job(img, tmp_path)])
    _guard_no_side_effects(app, monkeypatch)
    out = app.attach_held_patreon_media("job123", launch=False)       # dry run: script only
    assert out["ok"] is True and out["approved"] is True and out["editUrl"].endswith("173664094/edit")
    js = Path(out["script"]).read_text(encoding="utf-8")
    assert "refusing to create a new post" in js and "/posts\\/new/" in js          # never creates a post
    assert "name: 'Update', exact: true" in js and "waitForPatreonMediaReady" in js
    assert "mediaPersisted" in js and "tiersUnchanged" in js and "readPatreonTierState" in js
    assert json.loads(js[js.index("const job = ") + len("const job = "):js.index(";\nconst cdpUrl")])["mediaPath"] == str(img)


def test_12_attach_step_refuses_without_hold_or_edit_url(tmp_path, flag_on, monkeypatch):
    import app
    _meta(tmp_path)
    img = _png(tmp_path, "promo-1.png", b"OK")
    _approve(img)
    _guard_no_side_effects(app, monkeypatch)
    monkeypatch.setattr(app.automation_db, "list_release_jobs", lambda *a, **k: [_job(img, tmp_path, mediaStatus="", mediaHold={})])
    assert app.attach_held_patreon_media("job123")["reason"] == "job has no HELD_IDENTITY media"
    monkeypatch.setattr(app.automation_db, "list_release_jobs", lambda *a, **k: [_job(img, tmp_path, editUrl="https://www.patreon.com/posts/new")])
    assert "no saved Patreon edit URL" in app.attach_held_patreon_media("job123")["reason"]
    monkeypatch.setattr(app.automation_db, "list_release_jobs", lambda *a, **k: [])
    assert app.attach_held_patreon_media("nope")["reason"] == "release job not found"

