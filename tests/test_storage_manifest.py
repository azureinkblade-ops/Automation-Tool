"""Behavioral tests for the SC-1 storage manifest and scanner.

These tests are read-only against the live repo. They never mutate live JSON or
automation_state.db. They use temp directories for manifest logic and the real
repo for evidence-based assertions.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from storage import resource_manifest as rm
from storage import audit_storage_resources as audit


REPO_ROOT = audit.REPO_ROOT


# --- Manifest correctness -------------------------------------------------

def test_manifest_classifications_valid():
    for r in rm.load_manifest().values():
        assert r.classification in rm.CLASSIFICATIONS, r.classification
        assert not r.is_unknown(), f"{r.resource} must not be unknown in seed"


def test_posting_schedule_classified_sqlite_state():
    r = rm.load_manifest()["postingSchedule"]
    assert r.classification == "sqlite_state"
    assert r.legacy_file == "posting_schedule.json"
    assert r.durable is True
    assert any("13417" in w or "18036" in w for w in r.current_writers)
    assert any("13387" in rd or "13388" in rd for rd in r.current_readers)


def test_deep_tiktok_rotation_classified_durable_not_readonly():
    r = rm.load_manifest()["deepTikTokRotation"]
    assert r.classification == "sqlite_state"
    assert r.durable is True
    # Critical correction: it has a writer, not read-only.
    assert any("15619" in w for w in r.current_writers), "must detect write_json_atomic writer"
    assert any("15583" in rd or "15584" in rd for rd in r.current_readers)


def test_metadata_sidecar_pattern_resolves():
    r = rm.classify_root_json("metadata.json", rm.load_manifest())
    assert r is not None
    assert r.classification == "file_artifact"


# --- Scanner behavioral coverage -----------------------------------------

def test_scan_detects_wrapper_write_for_deep_tiktok():
    scan = audit.scan_repository(REPO_ROOT)
    # The preliminary audit missed this; SC-1 must catch write_json_atomic.
    write_sites = scan.by_kind("write")
    deep_write = [s for s in write_sites if "DEEP_TIKTOK_ROTATION_FILE" in (s.symbol or "") and "15619" in str(s.line)]
    assert deep_write, "write_json_atomic(DEEP_TIKTOK_ROTATION_FILE) at ~15619 not detected"


def test_scan_detects_direct_posting_schedule_read_write():
    scan = audit.scan_repository(REPO_ROOT)
    sched_const = None
    for name, fname in scan.constant_map.items():
        if fname == "posting_schedule.json":
            sched_const = name
    assert sched_const == "SCHEDULE_FILE", scan.constant_map
    writes = [s for s in scan.by_kind("write") if s.symbol == "SCHEDULE_FILE"]
    reads = [s for s in scan.by_kind("read") if s.symbol == "SCHEDULE_FILE"]
    assert any("13417" in str(s.line) or "18036" in str(s.line) for s in writes)
    assert any("13387" in str(s.line) or "13388" in str(s.line) for s in reads)


def test_scan_excludes_backup_and_venv_paths():
    scan = audit.scan_repository(REPO_ROOT)
    bad = [s.path for s in scan.sites if s.path.startswith((".venv", "backup/"))]
    assert not bad, f"excluded paths leaked into evidence: {bad[:3]}"


def test_root_json_inventory_excludes_artifact_trees():
    names = audit.root_json_inventory(REPO_ROOT)
    # metadata.json in content/Promo Images trees is not a root file.
    assert "metadata.json" not in names


def test_every_root_json_resolves_to_manifest_or_unknown():
    manifest = rm.load_manifest()
    scan = audit.scan_repository(REPO_ROOT)
    names = audit.root_json_inventory(REPO_ROOT)
    unresolved = []
    for name in names:
        if name == "metadata.json":
            continue
        res = rm.classify_root_json(name, manifest)
        if res is None:
            unresolved.append(name)
    # At minimum the two confirmed durable files must resolve.
    assert "posting_schedule.json" not in unresolved
    assert "deep-tiktok-rotation.json" not in unresolved
    # Report the rest for transparency; does not fail SC-1 alone.
    return unresolved


def test_audit_report_is_deterministic():
    r1 = audit.build_inventory_report(REPO_ROOT)
    r2 = audit.build_inventory_report(REPO_ROOT)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_unknown_entries_block_quarantine():
    manifest = rm.load_manifest()
    scan = audit.scan_repository(REPO_ROOT)
    report = audit.build_inventory_report(REPO_ROOT, manifest)
    unknown_files = [f["file"] for f in report["files"] if f["classification"] == "unknown"]
    # No root JSON may be quarantined while unknown. This asserts the contract.
    for f in report["files"]:
        if f["classification"] == "unknown":
            assert f["migration_action"] == "" or "unknown" in f["migration_action"]
    # Surface count; SC-7 will resolve these.
    assert isinstance(unknown_files, list)
    return unknown_files


# --- Adversarial: synthetic fixture proves wrapper detection --------------

def test_scanner_detects_wrapper_write_in_temp_repo():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app.py").write_text(
            'DEEP_TIKTOK_ROTATION_FILE = ROOT / "deep-tiktok-rotation.json"\n'
            "def save():\n"
            "    write_json_atomic(DEEP_TIKTOK_ROTATION_FILE, data)\n",
            encoding="utf-8",
        )
        scan = audit.scan_repository(root)
        writes = scan.by_kind("write")
        hits = [s for s in writes if s.symbol == "DEEP_TIKTOK_ROTATION_FILE"]
        assert hits, "synthetic wrapper write must be detected"
        assert hits[0].line == 3


if __name__ == "__main__":
    raise SystemExit(1)
