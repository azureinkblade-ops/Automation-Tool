# -*- coding: utf-8 -*-
"""Publish authorization boundary tests (18 cases across this file + test_test_isolation.py).

Cases 1-12: publish boundary. Mock all providers; REAL_PUBLISH_ACTIONS=0.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from tools import aivsb_prompt_provenance as prov
from tools import identity_preservation as ip

FLAG = "ENABLE_IDENTITY_PRESERVATION"


def _png(tmp: Path, name: str, tag: bytes = b"X") -> Path:
    p = tmp / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + tag * 40)
    return p


def _meta(folder: Path, **kw):
    data = {"abbr": "HP", "novel": "Hundredfold Path", "chapter": "7", **kw}
    (folder / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.setenv("AIVSB_REASONING_ENABLED", "on")
    yield
    monkeypatch.delenv(FLAG, raising=False)


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    yield


# --- 1-12 publish boundary ---

def test_01_flag_off_legacy_allows_missing_record(tmp_path, flag_off, monkeypatch):
    import app
    p = _png(tmp_path, "HP_7_1.png")
    _meta(tmp_path)
    assert app._identity_publish_eligible([str(p)], "TEST", folder=tmp_path) == [str(p)]


def test_02_governed_slot_missing_sidecar_rejects(tmp_path, flag_on):
    p = _png(tmp_path, "HP_7_1.png", b"LEGACY")
    _meta(tmp_path)
    ok, why = prov.publish_identity_check(p, folder=tmp_path)
    assert ok is False
    assert "MISSING_IDENTITY_APPROVAL" in why or "WITHOUT_IDENTITY_APPROVAL" in why


def test_03_quarantined_image_rejects(tmp_path, flag_on):
    p = _png(tmp_path, "HP_7_1.identity-review.png")
    _meta(tmp_path)
    ok, why = prov.publish_identity_check(p, folder=tmp_path)
    assert ok is False and why == "QUARANTINED_IDENTITY_REVIEW_IMAGE"


def test_04_identity_record_not_accepted_rejects(tmp_path, flag_on):
    p = _png(tmp_path, "HP_7_2.png", b"REJ")
    _meta(tmp_path)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    (tmp_path / (p.name + ".identity_preservation.json")).write_text(
        json.dumps({"IMAGE_SHA256": sha, "AUTO_ACCEPT_ALLOWED": "NO"}), encoding="utf-8"
    )
    ok, why = prov.publish_identity_check(p, folder=tmp_path)
    assert ok is False and "NOT_ACCEPTED" in why


def test_05_governed_aivsb_provenance_without_approval_rejects(tmp_path, flag_on):
    p = _png(tmp_path, "HP_7_3.png", b"GOV")
    _meta(tmp_path)
    rec = prov.build_record(
        "hp, expressing resolve, wide shot",
        source_prompt="Liang entered the hall",
        source_text="Liang entered the ruined sect hall",
        novel_id="hp",
        aivsb_composed=True,
        source_run_id="tpub",
        source_asset_id="hp:t:3",
        origin="test.publish",
    )
    prov.write_image_provenance(p, rec)
    ok, why = prov.publish_identity_check(p, folder=tmp_path)
    assert ok is False
    assert "WITHOUT_IDENTITY_APPROVAL" in why or "MISSING_IDENTITY_APPROVAL" in why


def test_06_tampered_provenance_fails_closed(tmp_path, flag_on):
    p = _png(tmp_path, "HP_7_4.png", b"TAMPER")
    _meta(tmp_path)
    rec = prov.build_record(
        "hp, wide shot",
        source_prompt="Liang",
        source_text="Liang entered",
        novel_id="hp",
        aivsb_composed=True,
        source_run_id="tpub",
        source_asset_id="hp:t:4",
        origin="test.publish",
    )
    prov.write_image_provenance(p, rec)
    side = prov.image_sidecar_path(p)
    raw = json.loads(side.read_text(encoding="utf-8"))
    raw["image_sha256"] = "0" * 64
    side.write_text(json.dumps(raw), encoding="utf-8")
    ok, why = prov.publish_identity_check(p, folder=tmp_path)
    assert ok is False
    assert "PROVENANCE" in why or "BINDING" in why or "STALE" in why or "MISMATCH" in why


def test_07_approved_prior_review_allows(tmp_path, flag_on):
    p = _png(tmp_path, "HP_7_5.png", b"OKREV")
    _meta(tmp_path)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    pr = ip.build_prior_review_record(
        image_sha256=sha,
        character_id="liang",
        verifier_decision="PASS",
        human_review_status="APPROVED",
    )
    ip.prior_review_sidecar_path(p).write_text(json.dumps(pr), encoding="utf-8")
    ok, why = prov.publish_identity_check(p, folder=tmp_path)
    assert ok is True and why == ""


def test_08_scenery_qualified_intent_allows(tmp_path, flag_on):
    p = _png(tmp_path, "scenery.png", b"SCENE")
    ok, why = prov.publish_identity_check(
        p, metadata={"abbr": "HP", "image_intent": "SCENERY_ONLY"}
    )
    assert ok is True and why == ""


def test_09_instagram_path_gated(tmp_path, flag_on, monkeypatch):
    import app
    folder = tmp_path / "en-7-monday"
    folder.mkdir()
    img = _png(folder, "EN_Monday.png", b"IG")
    meta = {
        "abbr": "EN",
        "novel": "Eternal Nexus",
        "chapter": "7",
        "image": str(img),
        "instagram": "Kael caption",
        "public_image_url": "https://probe.invalid/EN_Monday.png",
    }
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "t")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1")
    # Point SOCIAL_OUTPUT_DIR at tmp so folder validity check passes
    monkeypatch.setattr(app, "SOCIAL_OUTPUT_DIR", tmp_path)
    calls = []

    def fake_form(url, payload):
        calls.append(url)
        return {"id": "container-1"}

    monkeypatch.setattr(app, "form_request", fake_form)
    with pytest.raises(Exception) as ei:
        app.publish_instagram_image(str(folder))
    assert ip.is_identity_block(ei.value) or "identity" in str(ei.value).lower()
    assert calls == []  # no real/mocked Graph submit after auth failure


def test_10_buffer_path_gated(tmp_path, flag_on, monkeypatch):
    import buffer_publish as bp
    folder = tmp_path / "social_pack"
    folder.mkdir()
    img = _png(folder, "img.png", b"BUF")
    meta = {
        "abbr": "EN",
        "novel": "Eternal Nexus",
        "kind": "social_pack",
        "instagram": "caption",
        "image": str(img),
    }
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    created = []

    def fake_create(*a, **k):
        created.append(1)
        return {"id": "x"}

    collab = {
        "read_metadata": lambda f: meta,
        "normalize_chapter_id": lambda *a, **k: "7",
        "stable_chapter_folder": lambda *a, **k: folder,
        "repair_deep_tiktok_metadata": lambda f, m: m,
        "ensure_buffer_video": lambda *a, **k: None,
        "folder_quality_gate": lambda *a, **k: {"ok": True},
        "record_recovery_event": lambda *a, **k: None,
        "github_auto_publish_media": lambda: False,
        "publish_folder_media_to_github": lambda *a, **k: {},
        "create_buffer_post": fake_create,
        "buffer_queue_full_error": lambda *a, **k: False,
        "buffer_queue_full_fallback": lambda *a, **k: {},
        "video_meets_minimum_duration": lambda *a, **k: True,
        "media_duration_seconds": lambda *a, **k: 10,
        "post_record_from_folder": lambda *a, **k: {},
        "save_post_record": lambda *a, **k: None,
        "update_clickup_on_publish": lambda *a, **k: None,
        "advance_completed_chapter": lambda *a, **k: None,
        "chapter_can_advance_active_path": lambda *a, **k: False,
    }
    # Patch SOCIAL_OUTPUT_DIR used inside buffer routing via app_config / collaborators path checks
    monkeypatch.setenv("BUFFER_CHANNEL_IDS", "instagram:ig1")
    # Force social branch by making folder under a SOCIAL_OUTPUT_DIR we control
    import app as app_mod
    monkeypatch.setattr(app_mod, "SOCIAL_OUTPUT_DIR", tmp_path)
    # buffer_publish imports SOCIAL from app_config at load — patch module attrs if present
    import app_config
    monkeypatch.setattr(app_config, "SOCIAL_OUTPUT_DIR", tmp_path, raising=False)
    # Also patch buffer's resolved check: it uses SOCIAL_OUTPUT_DIR from app_config
    import buffer_publish as bpm
    if hasattr(bpm, "SOCIAL_OUTPUT_DIR"):
        monkeypatch.setattr(bpm, "SOCIAL_OUTPUT_DIR", tmp_path)
    else:
        # inject via sys.modules app_config already patched; reload path comparison uses imported name
        from buffer_publish import SOCIAL_OUTPUT_DIR as _s  # may be bound
        pass
    # Direct unit: call the gate helper
    with pytest.raises(Exception) as ei:
        bp._buffer_identity_publish_gate(folder, [str(img)], meta)
    assert "identity" in str(ei.value).lower() or ip.is_identity_block(ei.value)
    assert created == []


def test_11_x_browser_path_gated(tmp_path, flag_on, monkeypatch):
    import browser_publish as br
    folder = tmp_path / "x_pack"
    folder.mkdir()
    img = _png(folder, "img.png", b"XPOST")
    meta = {"abbr": "EN", "novel": "Eternal Nexus", "x": "hello", "image": str(img)}
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setenv("X_ACCESS_TOKEN", "tok")
    import app_config
    monkeypatch.setattr(app_config, "SOCIAL_OUTPUT_DIR", tmp_path, raising=False)
    if hasattr(br, "SOCIAL_OUTPUT_DIR"):
        monkeypatch.setattr(br, "SOCIAL_OUTPUT_DIR", tmp_path)
    uploads = []

    def fake_multi(*a, **k):
        uploads.append(1)
        return {"data": {"id": "m1"}}

    with pytest.raises(Exception) as ei:
        br.publish_x_post(
            str(folder),
            collaborators={
                "multipart_bearer_request": fake_multi,
                "bearer_json_request": lambda *a, **k: {"data": {"id": "t1"}},
            },
        )
    assert "identity" in str(ei.value).lower() or ip.is_identity_block(ei.value)
    assert uploads == []


def test_12_r2_eligible_blocks_governed_legacy(tmp_path, flag_on, monkeypatch):
    import app
    p = _png(tmp_path, "promo-1.png", b"R2")
    _meta(tmp_path, abbr="HP")
    with pytest.raises(Exception) as ei:
        app._identity_publish_eligible([str(p)], "PUBLISH:upload_folder_media_to_r2", folder=tmp_path)
    assert ip.is_identity_block(ei.value) or "identity" in str(ei.value).lower()
