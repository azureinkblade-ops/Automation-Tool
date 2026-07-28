"""Phase 3 non-executing harness contract tests.

These tests use disposable files only. They never import promo_copy, build an
AIVSB index, enable retrieval, or execute an OFF/ON evaluation attempt.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


NOVELS = ("en", "ha", "hp", "sf")
FOCUSES = (
    "royal_road_live",
    "patreon_early",
    "youtube_release",
    "weekly_general_promo",
    "catch_up_archive",
    "generic",
)


def _candidate_inventory():
    fixtures = []
    for novel in NOVELS:
        for index, focus in enumerate(FOCUSES, start=1):
            fixtures.append({
                "fixture_id": f"FX-{novel.upper()}-{index:03d}",
                "novel_id": novel,
                "chapter_id": str(index),
                "requested_focus": focus,
                "composer_inputs": {
                    "abbr": novel,
                    "novel": novel.upper(),
                    "chapter": str(index),
                    "title": f"Chapter {index}",
                    "phrases": ["A frozen phrase."],
                    "characters": ["Fixture Character"],
                },
                "rotation_stub": {"version": "phase3-rotation-stub-v1", "return_index": 0},
                "ledger_state": {"last_chapter": index - 1, "rotation_index": 0},
                "release_status": {"is_live": focus == "royal_road_live"},
                "canon_reference": {
                    "source_files": [f"style_guides/{novel}.yaml"],
                    "source_hashes": ["a" * 64],
                    "relevant_facts": ["Product-reviewed fact"],
                    "prohibited_claims": ["Product-reviewed prohibited claim"],
                },
                "expected_contract": {
                    "public_keys": [
                        "caption", "patreon_note", "facebook_post", "x_post",
                        "x_thread_links", "post_focus", "caption_style",
                        "tracking_campaign", "_agent_source",
                    ],
                    "scored_text_fields": [
                        "caption", "patreon_note", "facebook_post", "x_post",
                    ],
                    "leak_checked_fields": "ALL_RECURSIVE",
                },
                "qualification": {
                    "product_reviewed": True,
                    "selected_without_observing_on_output": True,
                    "status": "qualified",
                },
            })
    return {"schema_version": "phase3-fixture-v2-slice2r", "fixtures": fixtures}


def _freeze_proposal():
    return {
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "harness_commit": "1" * 40,
        "source_commit": "2" * 40,
        "source_clean": True,
        "model": {
            "model_id": "sentence-transformers/all-MiniLM-L6-v2",
            "revision": "3" * 40,
            "manifest_sha256": "4" * 64,
            "hashes_verified": True,
            "offline_verified": True,
        },
        "versions": {
            "fixture_schema": "phase3-fixture-v2-slice2r",
            "attempt_schema": "phase3-attempt-v2-slice2r",
            "automated_scorer": "phase3-eval-v1",
            "quality_rubric": "phase3-quality-rubric-v2",
            "safety_rubric": "phase3-safety-rubric-v2",
            "threshold_policy": "phase3-thresholds-v2",
        },
        "governance_hashes": {"rubric": "5" * 64, "thresholds": "6" * 64},
    }


def _write_subject_with_off_default(path: Path) -> Path:
    path.write_text(
        'ENABLE_AIVSB_RETRIEVAL = str(__import__("os").environ.get('
        '"ENABLE_AIVSB_RETRIEVAL", "false")).strip().lower() in '
        '("1", "true", "yes", "on")\n',
        encoding="utf-8",
    )
    return path


def test_canonical_json_bytes_are_stable_and_newline_terminated():
    from scripts.aivsb.phase3_eval import canonical_json_bytes

    left = canonical_json_bytes({"z": 1, "a": [3, 2]})
    right = canonical_json_bytes({"a": [3, 2], "z": 1})

    assert left == right == b'{"a":[3,2],"z":1}\n'
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_candidate_validator_accepts_exact_balanced_reviewed_inventory():
    from scripts.aivsb.phase3_eval import validate_candidate_inventory

    report = validate_candidate_inventory(_candidate_inventory())

    assert report == {
        "fixture_count": 24,
        "novel_allocation": {"en": 6, "ha": 6, "hp": 6, "sf": 6},
        "valid": True,
    }


def test_candidate_validator_rejects_missing_composer_inputs():
    from scripts.aivsb.phase3_eval import Phase3ValidationError, validate_candidate_inventory

    inventory = _candidate_inventory()
    del inventory["fixtures"][0]["composer_inputs"]

    with pytest.raises(Phase3ValidationError) as caught:
        validate_candidate_inventory(inventory)

    assert "composer_inputs" in str(caught.value)


def test_candidate_validator_rejects_missing_chapter_id():
    from scripts.aivsb.phase3_eval import Phase3ValidationError, validate_candidate_inventory

    inventory = _candidate_inventory()
    del inventory["fixtures"][0]["chapter_id"]

    with pytest.raises(Phase3ValidationError, match="chapter_id"):
        validate_candidate_inventory(inventory)


def test_freeze_preflight_accepts_pinned_clean_nonexecuting_proposal():
    from scripts.aivsb.phase3_eval import validate_freeze_preflight

    report = validate_freeze_preflight(_freeze_proposal())

    assert report == {
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "source_clean": True,
        "valid": True,
    }


def test_subject_default_is_read_from_source_without_importing_module(tmp_path):
    from scripts.aivsb.phase3_eval import inspect_aivsb_default

    subject = _write_subject_with_off_default(tmp_path / "promo_copy.py")

    assert inspect_aivsb_default(subject) is False


def test_execution_preflight_accepts_exact_manifest_bound_approval(tmp_path):
    from scripts.aivsb.phase3_eval import (
        canonical_json_bytes,
        validate_execution_preflight,
    )

    manifest = {
        "schema_version": "phase3-frozen-manifest-v2-slice2r",
        "finalized": True,
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "fixture_count": 24,
        "scoring": {
            "quality_rubric_sha256": "7" * 64,
            "safety_rubric_sha256": "8" * 64,
            "threshold_policy_sha256": "9" * 64,
        },
    }
    manifest_path = tmp_path / "frozen-manifest.json"
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    approval = {
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "frozen_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "controlled_on_flag_allowed": True,
        "normal_runtime_default_must_remain_off": True,
        "quality_rubric_sha256": "7" * 64,
        "safety_rubric_sha256": "8" * 64,
        "threshold_policy_sha256": "9" * 64,
        "approved": True,
        "approved_by": "David",
        "approved_at_utc": "2026-07-28T19:00:00Z",
    }

    report = validate_execution_preflight(
        manifest_path,
        approval,
        subject_file=_write_subject_with_off_default(tmp_path / "promo_copy.py"),
        evaluation_db_path=tmp_path / "freeze" / "index" / "automation_state.db",
        live_db_path=tmp_path / "live" / "automation_state.db",
    )

    assert report["valid"] is True
    assert report["fixture_count"] == 24
    assert report["normal_runtime_default"] is False


def test_execution_preflight_rejects_threshold_hash_mismatch(tmp_path):
    from scripts.aivsb.phase3_eval import (
        Phase3ValidationError,
        canonical_json_bytes,
        validate_execution_preflight,
    )

    manifest = {
        "schema_version": "phase3-frozen-manifest-v2-slice2r",
        "finalized": True,
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "fixture_count": 24,
        "scoring": {
            "quality_rubric_sha256": "7" * 64,
            "safety_rubric_sha256": "8" * 64,
            "threshold_policy_sha256": "9" * 64,
        },
    }
    manifest_path = tmp_path / "frozen-manifest.json"
    raw = canonical_json_bytes(manifest)
    manifest_path.write_bytes(raw)
    approval = {
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "frozen_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "controlled_on_flag_allowed": True,
        "normal_runtime_default_must_remain_off": True,
        "quality_rubric_sha256": "7" * 64,
        "safety_rubric_sha256": "8" * 64,
        "threshold_policy_sha256": "0" * 64,
        "approved": True,
        "approved_by": "David",
        "approved_at_utc": "2026-07-28T19:00:00Z",
    }

    with pytest.raises(Phase3ValidationError, match="threshold_policy_sha256"):
        validate_execution_preflight(
            manifest_path,
            approval,
            subject_file=_write_subject_with_off_default(tmp_path / "promo_copy.py"),
            evaluation_db_path=tmp_path / "eval.db",
            live_db_path=tmp_path / "live.db",
        )


def test_execution_preflight_rejects_noncanonical_manifest_bytes(tmp_path):
    from scripts.aivsb.phase3_eval import Phase3ValidationError, validate_execution_preflight

    manifest = {
        "schema_version": "phase3-frozen-manifest-v2-slice2r",
        "finalized": True,
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "fixture_count": 24,
        "scoring": {
            "quality_rubric_sha256": "7" * 64,
            "safety_rubric_sha256": "8" * 64,
            "threshold_policy_sha256": "9" * 64,
        },
    }
    manifest_path = tmp_path / "frozen-manifest.json"
    noncanonical = json.dumps(manifest, indent=2).encode("utf-8")
    manifest_path.write_bytes(noncanonical)
    approval = {
        "subject_commit": "5eed6e1823bc398084e8a46998186771a5970347",
        "frozen_manifest_sha256": hashlib.sha256(noncanonical).hexdigest(),
        "controlled_on_flag_allowed": True,
        "normal_runtime_default_must_remain_off": True,
        "quality_rubric_sha256": "7" * 64,
        "safety_rubric_sha256": "8" * 64,
        "threshold_policy_sha256": "9" * 64,
        "approved": True,
        "approved_by": "David",
        "approved_at_utc": "2026-07-28T19:00:00Z",
    }

    with pytest.raises(Phase3ValidationError, match="canonical JSON"):
        validate_execution_preflight(
            manifest_path,
            approval,
            subject_file=_write_subject_with_off_default(tmp_path / "promo_copy.py"),
            evaluation_db_path=tmp_path / "eval.db",
            live_db_path=tmp_path / "live.db",
        )


def test_cli_capabilities_exposes_no_freeze_or_execution_command(capsys):
    from scripts.aivsb.phase3_eval import main

    exit_code = main(["capabilities"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["fixture_freeze_enabled"] is False
    assert payload["evaluation_execution_enabled"] is False
    assert payload["commands"] == [
        "capabilities",
        "validate-candidates",
        "freeze-preflight",
        "execution-preflight",
    ]
