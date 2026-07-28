"""Phase 3 deterministic evidence harness.

Current authorization is design and validation only. This module does not
import promo_copy, build an index, enable retrieval, or run evaluation cases.
"""
from __future__ import annotations

import argparse
import ast
import json
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


FIXTURE_SCHEMA_VERSION = "phase3-fixture-v2-slice2r"
SUBJECT_COMMIT = "5eed6e1823bc398084e8a46998186771a5970347"
NOVEL_IDS = ("en", "ha", "hp", "sf")
REQUIRED_FOCUSES = (
    "royal_road_live",
    "patreon_early",
    "youtube_release",
    "weekly_general_promo",
    "catch_up_archive",
    "generic",
)
PUBLIC_KEYS = {
    "caption", "patreon_note", "facebook_post", "x_post", "x_thread_links",
    "post_focus", "caption_style", "tracking_campaign", "_agent_source",
}
SCORED_TEXT_FIELDS = {"caption", "patreon_note", "facebook_post", "x_post"}


class Phase3ValidationError(ValueError):
    """Raised when a Phase 3 artifact violates its frozen contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON with one terminal newline."""
    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (text + "\n").encode("utf-8")


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _is_git_oid(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(ch in "0123456789abcdef" for ch in text)


def inspect_aivsb_default(subject_file: Path) -> bool:
    """Read the retrieval env default from source without importing the module."""
    path = Path(subject_file)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise Phase3ValidationError([f"cannot inspect subject default: {type(exc).__name__}"])
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "ENABLE_AIVSB_RETRIEVAL" for target in node.targets):
            continue
        for child in ast.walk(node.value):
            if not isinstance(child, ast.Call) or len(child.args) < 2:
                continue
            if not isinstance(child.func, ast.Attribute) or child.func.attr != "get":
                continue
            key, default = child.args[:2]
            if (
                isinstance(key, ast.Constant)
                and key.value == "ENABLE_AIVSB_RETRIEVAL"
                and isinstance(default, ast.Constant)
                and isinstance(default.value, str)
            ):
                normalized = default.value.strip().lower()
                if normalized in {"false", "0", "no", "off"}:
                    return False
                if normalized in {"true", "1", "yes", "on"}:
                    return True
    raise Phase3ValidationError(["cannot prove ENABLE_AIVSB_RETRIEVAL source default"])


def validate_freeze_preflight(proposal: dict[str, Any]) -> dict[str, Any]:
    """Validate freeze prerequisites without creating a freeze or running retrieval."""
    errors: list[str] = []
    if proposal.get("subject_commit") != SUBJECT_COMMIT:
        errors.append(f"subject_commit must equal {SUBJECT_COMMIT}")
    for field in ("harness_commit", "source_commit"):
        if not _is_git_oid(proposal.get(field)):
            errors.append(f"{field} must be a full 40-character Git object ID")
    if proposal.get("source_clean") is not True:
        errors.append("source_clean must be true")

    model = proposal.get("model") or {}
    if not str(model.get("model_id") or "").strip():
        errors.append("model.model_id is required")
    if not _is_git_oid(model.get("revision")) and not _is_sha256(model.get("revision")):
        errors.append("model.revision must be an immutable 40- or 64-character identity")
    if not _is_sha256(model.get("manifest_sha256")):
        errors.append("model.manifest_sha256 must be SHA-256")
    if model.get("hashes_verified") is not True:
        errors.append("model.hashes_verified must be true")
    if model.get("offline_verified") is not True:
        errors.append("model.offline_verified must be true")

    expected_versions = {
        "fixture_schema": "phase3-fixture-v2-slice2r",
        "attempt_schema": "phase3-attempt-v2-slice2r",
        "automated_scorer": "phase3-eval-v1",
        "quality_rubric": "phase3-quality-rubric-v2",
        "safety_rubric": "phase3-safety-rubric-v2",
        "threshold_policy": "phase3-thresholds-v2",
    }
    if proposal.get("versions") != expected_versions:
        errors.append("versions must exactly match the approved Phase 3 version set")
    hashes = proposal.get("governance_hashes") or {}
    for field in ("rubric", "thresholds"):
        if not _is_sha256(hashes.get(field)):
            errors.append(f"governance_hashes.{field} must be SHA-256")

    if errors:
        raise Phase3ValidationError(errors)
    return {
        "subject_commit": SUBJECT_COMMIT,
        "source_clean": True,
        "valid": True,
    }


def validate_execution_preflight(
    manifest_path: Path,
    approval: dict[str, Any],
    *,
    subject_file: Path,
    evaluation_db_path: Path,
    live_db_path: Path,
) -> dict[str, Any]:
    """Validate execution authority without importing or invoking the consumer."""
    errors: list[str] = []
    path = Path(manifest_path)
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase3ValidationError([f"frozen manifest is unreadable: {type(exc).__name__}"])

    actual_hash = hashlib.sha256(raw).hexdigest()
    if raw != canonical_json_bytes(manifest):
        errors.append("frozen manifest must use canonical JSON encoding")
    if approval.get("approved") is not True:
        errors.append("execution approval must be explicitly true")
    if not str(approval.get("approved_by") or "").strip():
        errors.append("execution approval requires approved_by")
    if not str(approval.get("approved_at_utc") or "").strip():
        errors.append("execution approval requires approved_at_utc")
    if approval.get("subject_commit") != SUBJECT_COMMIT:
        errors.append(f"approval subject_commit must equal {SUBJECT_COMMIT}")
    if approval.get("frozen_manifest_sha256") != actual_hash:
        errors.append("execution approval does not match frozen manifest SHA-256")
    if approval.get("controlled_on_flag_allowed") is not True:
        errors.append("controlled_on_flag_allowed must be true")
    if approval.get("normal_runtime_default_must_remain_off") is not True:
        errors.append("normal runtime OFF invariant is missing")

    normal_runtime_default = inspect_aivsb_default(subject_file)
    if normal_runtime_default is not False:
        errors.append("normal runtime default must be false")
    if Path(evaluation_db_path).resolve() == Path(live_db_path).resolve():
        errors.append("evaluation database must not be the live database")
    if manifest.get("schema_version") != "phase3-frozen-manifest-v2-slice2r":
        errors.append("frozen manifest schema_version mismatch")
    if manifest.get("finalized") is not True:
        errors.append("frozen manifest must be finalized")
    if manifest.get("subject_commit") != SUBJECT_COMMIT:
        errors.append(f"manifest subject_commit must equal {SUBJECT_COMMIT}")
    if manifest.get("fixture_count") != 24:
        errors.append("frozen manifest fixture_count must equal 24")
    scoring = manifest.get("scoring") or {}
    for field in (
        "quality_rubric_sha256",
        "safety_rubric_sha256",
        "threshold_policy_sha256",
    ):
        manifest_value = scoring.get(field)
        approval_value = approval.get(field)
        if not _is_sha256(manifest_value):
            errors.append(f"manifest scoring.{field} must be SHA-256")
        if not _is_sha256(approval_value):
            errors.append(f"approval {field} must be SHA-256")
        if manifest_value != approval_value:
            errors.append(f"approval {field} does not match frozen manifest")

    if errors:
        raise Phase3ValidationError(errors)
    return {
        "fixture_count": 24,
        "manifest_sha256": actual_hash,
        "normal_runtime_default": False,
        "valid": True,
    }


def validate_candidate_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    """Validate a proposed fixture inventory without retrieval or file writes."""
    errors: list[str] = []
    if inventory.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        errors.append("schema_version must be phase3-fixture-v2-slice2r")
    fixtures = inventory.get("fixtures")
    if not isinstance(fixtures, list):
        raise Phase3ValidationError(errors + ["fixtures must be a list"])
    if len(fixtures) != 24:
        errors.append("fixture count must equal 24")

    ids: list[str] = []
    allocation: Counter[str] = Counter()
    focuses: dict[str, set[str]] = defaultdict(set)
    for index, fixture in enumerate(fixtures):
        prefix = f"fixture[{index}]"
        if not isinstance(fixture, dict):
            errors.append(f"{prefix} must be an object")
            continue
        fixture_id = str(fixture.get("fixture_id") or "")
        ids.append(fixture_id)
        if not fixture_id:
            errors.append(f"{prefix}.fixture_id is required")
        if not str(fixture.get("chapter_id") or "").strip():
            errors.append(f"{prefix}.chapter_id is required")
        novel_id = str(fixture.get("novel_id") or "")
        allocation[novel_id] += 1
        focuses[novel_id].add(str(fixture.get("requested_focus") or ""))

        composer = fixture.get("composer_inputs")
        if not isinstance(composer, dict):
            errors.append(f"{prefix}.composer_inputs must be an object")
        else:
            for field in ("abbr", "novel", "chapter", "title", "phrases", "characters"):
                if field not in composer or composer[field] in (None, "", []):
                    errors.append(f"{prefix}.composer_inputs.{field} is required")
            if composer.get("abbr") != novel_id:
                errors.append(f"{prefix}.composer_inputs.abbr must match novel_id")
        rotation = fixture.get("rotation_stub") or {}
        if rotation.get("version") != "phase3-rotation-stub-v1":
            errors.append(f"{prefix}.rotation_stub.version mismatch")
        if not isinstance(rotation.get("return_index"), int) or rotation.get("return_index", -1) < 0:
            errors.append(f"{prefix}.rotation_stub.return_index must be a nonnegative integer")
        if not isinstance(fixture.get("ledger_state"), dict):
            errors.append(f"{prefix}.ledger_state must be an object")
        if not isinstance(fixture.get("release_status"), dict):
            errors.append(f"{prefix}.release_status must be an object")

        canon = fixture.get("canon_reference") or {}
        source_files = canon.get("source_files") or []
        source_hashes = canon.get("source_hashes") or []
        if not source_files or len(source_files) != len(source_hashes):
            errors.append(f"{prefix}.canon_reference source files/hashes must pair")
        if not source_hashes or not all(_is_sha256(value) for value in source_hashes):
            errors.append(f"{prefix}.canon_reference source_hashes must be SHA-256")
        if not canon.get("relevant_facts") or not canon.get("prohibited_claims"):
            errors.append(f"{prefix}.canon_reference requires reviewed facts and prohibited claims")

        qualification = fixture.get("qualification") or {}
        if qualification.get("product_reviewed") is not True:
            errors.append(f"{prefix}.qualification.product_reviewed must be true")
        if qualification.get("selected_without_observing_on_output") is not True:
            errors.append(f"{prefix} must be selected without observing ON output")
        if qualification.get("status") != "qualified":
            errors.append(f"{prefix}.qualification.status must be qualified")

        contract = fixture.get("expected_contract") or {}
        if set(contract.get("public_keys") or []) != PUBLIC_KEYS:
            errors.append(f"{prefix}.expected_contract.public_keys mismatch")
        if set(contract.get("scored_text_fields") or []) != SCORED_TEXT_FIELDS:
            errors.append(f"{prefix}.expected_contract.scored_text_fields mismatch")
        if contract.get("leak_checked_fields") != "ALL_RECURSIVE":
            errors.append(f"{prefix}.expected_contract.leak_checked_fields must be ALL_RECURSIVE")

    if len(ids) != len(set(ids)):
        errors.append("fixture IDs must be unique")
    expected_allocation = {novel_id: 6 for novel_id in NOVEL_IDS}
    actual_allocation = {novel_id: allocation.get(novel_id, 0) for novel_id in NOVEL_IDS}
    if actual_allocation != expected_allocation or any(k not in NOVEL_IDS for k in allocation):
        errors.append("novel allocation must equal en=6, ha=6, hp=6, sf=6")
    required_focus_set = set(REQUIRED_FOCUSES)
    for novel_id in NOVEL_IDS:
        if focuses.get(novel_id, set()) != required_focus_set:
            errors.append(f"{novel_id} must cover each required focus exactly once")

    if errors:
        raise Phase3ValidationError(errors)
    return {
        "fixture_count": len(fixtures),
        "novel_allocation": actual_allocation,
        "valid": True,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase3ValidationError([f"cannot read JSON {path}: {type(exc).__name__}"])
    if not isinstance(value, dict):
        raise Phase3ValidationError([f"JSON root must be an object: {path}"])
    return value


def _emit(value: dict[str, Any], *, stream=None) -> None:
    target = stream or sys.stdout
    target.write(canonical_json_bytes(value).decode("utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIVSB Phase 3 validation-only harness")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities")

    candidates = commands.add_parser("validate-candidates")
    candidates.add_argument("--input", required=True, type=Path)

    freeze = commands.add_parser("freeze-preflight")
    freeze.add_argument("--proposal", required=True, type=Path)

    execution = commands.add_parser("execution-preflight")
    execution.add_argument("--manifest", required=True, type=Path)
    execution.add_argument("--approval", required=True, type=Path)
    execution.add_argument("--subject-file", required=True, type=Path)
    execution.add_argument("--evaluation-db", required=True, type=Path)
    execution.add_argument("--live-db", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run validation-only commands. No command performs freeze or evaluation."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            result = {
                "commands": [
                    "capabilities",
                    "validate-candidates",
                    "freeze-preflight",
                    "execution-preflight",
                ],
                "evaluation_execution_enabled": False,
                "fixture_freeze_enabled": False,
                "subject_commit": SUBJECT_COMMIT,
            }
        elif args.command == "validate-candidates":
            result = validate_candidate_inventory(_load_json(args.input))
        elif args.command == "freeze-preflight":
            result = validate_freeze_preflight(_load_json(args.proposal))
        else:
            result = validate_execution_preflight(
                args.manifest,
                _load_json(args.approval),
                subject_file=args.subject_file,
                evaluation_db_path=args.evaluation_db,
                live_db_path=args.live_db,
            )
    except Phase3ValidationError as exc:
        _emit({"errors": exc.errors, "valid": False}, stream=sys.stderr)
        return 2
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
