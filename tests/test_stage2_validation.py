from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_valid_pilot(tmp_path):
    import app
    from PIL import Image

    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    guide = tmp_path / "guide.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source)
    m = Image.new("L", (4, 4), 0)
    m.putpixel((1, 1), 255)
    m.putpixel((1, 2), 255)
    m.save(mask)
    Image.new("RGB", (4, 4), (40, 50, 60)).save(guide)
    manifest = {
        "schema_version": 1,
        "suite_id": "pilot-v0",
        "suite_kind": "pilot",
        "cases": [{
            "case_id": "case-001",
            "strata": {
                "object_class": "sheathed_sword",
                "lighting": "warm",
                "composition": "kneeling",
                "mask_size": "small",
            },
            "source_path": source.name,
            "mask_path": mask.name,
            "guide_path": guide.name,
            "object_type": "jian",
            "target_region": "outer hip",
            "prompt": "one coherent sheathed jian",
            "generation_config": {
                "model": "models/sdxl-base",
                "lora": "loras/main-posts/pytorch_lora_weights.safetensors",
                "lora_scale": 0.5,
                "seed": 917364,
                "strength": 0.25,
                "steps": 35,
                "guidance_scale": 7.0,
                "padding_mask_crop": 64,
            },
        }],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_preflight_valid_pilot_records_hashes_and_mask_coverage(tmp_path):
    from stage2_validation import preflight_manifest

    report = preflight_manifest(_write_valid_pilot(tmp_path))

    assert report.ok is True
    assert report.suite_kind == "pilot"
    assert len(report.cases) == 1
    row = report.cases[0]
    assert row.case_id == "case-001"
    assert len(row.source_sha256) == 64
    assert len(row.mask_sha256) == 64
    assert len(row.guide_sha256) == 64
    assert row.mask_authorized_pixels == 2
    assert row.mask_coverage == 0.125


def test_preflight_blocks_case_with_incomplete_generation_config(tmp_path):
    from stage2_validation import preflight_manifest

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["cases"][0]["generation_config"]["seed"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = preflight_manifest(manifest_path)

    assert report.ok is False
    assert report.cases == ()
    assert report.errors == ("case-001: generation_config missing: seed",)


def test_aggregation_uses_measured_denominators_and_marks_missing_fields():
    from stage2_validation import aggregate_measurements

    rows = [
        {
            "case_id": "case-001",
            "generation_status": "accepted",
            "overall_accept": True,
            "outside_mask_changed_pixels": 0,
            "review": {
                "object_recognizable": True,
                "placement_attachment_valid": True,
                "no_duplicate_floating_substitution": True,
                "identity_preserved": True,
                "pose_preserved": True,
                "anatomy_preserved": True,
                "clothing_composition_preserved": True,
            },
            "preparation_seconds": 30,
            "review_seconds": 12,
            "manual_intervention_cycles": 1,
        },
        {
            "case_id": "case-002",
            "generation_status": "rejected",
            "overall_accept": False,
            "outside_mask_changed_pixels": 0,
            "review": {
                "object_recognizable": False,
                "placement_attachment_valid": False,
            },
            "preparation_seconds": 50,
            "review_seconds": 18,
            "manual_intervention_cycles": 2,
        },
    ]

    report = aggregate_measurements(rows, suite_kind="pilot")

    assert report.acceptance.numerator == 1
    assert report.acceptance.denominator == 2
    assert report.gates["object_recognizable"].denominator == 2
    assert report.gates["identity_preserved"].numerator == 1
    assert report.gates["identity_preserved"].denominator == 1
    assert report.missing_review_fields["case-002"] == (
        "no_duplicate_floating_substitution",
        "identity_preserved",
        "pose_preserved",
        "anatomy_preserved",
        "clothing_composition_preserved",
    )
    assert report.mean_preparation_seconds == 40.0
    assert report.mean_review_seconds == 15.0
    assert report.mean_manual_intervention_cycles == 1.5


def test_collect_measurements_blocks_provenance_source_hash_mismatch(tmp_path):
    import pytest
    from stage2_validation import collect_measurements

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    provenance = tmp_path / "final-provenance.json"
    provenance.write_text(json.dumps({
        "status": "accepted",
        "source_sha256": "0" * 64,
        "mask_sha256": "1" * 64,
        "guide_sha256": "2" * 64,
        "candidate_path": str(tmp_path / "candidate.png"),
        "candidate_sha256": "3" * 64,
        "outside_mask_changed_pixels": 0,
    }), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"case_id": "case-001", "overall_accept": True}), encoding="utf-8")
    payload["cases"][0]["final_provenance_path"] = provenance.name
    payload["cases"][0]["review_path"] = review.name
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case-001: provenance source hash mismatch"):
        collect_measurements(manifest_path)


def test_serialized_report_uses_not_measured_instead_of_zero():
    from stage2_validation import aggregate_measurements, serialize_report

    rows = ({
        "case_id": "case-001",
        "generation_status": "pending_review",
        "overall_accept": None,
        "outside_mask_changed_pixels": 0,
        "review": {},
        "preparation_seconds": None,
        "review_seconds": None,
        "manual_intervention_cycles": None,
    },)
    report = aggregate_measurements(rows, suite_kind="pilot")

    payload = serialize_report(report, rows)

    assert payload["metrics"]["acceptance_rate"]["rate"] == "NOT_MEASURED"
    assert payload["confidence_reporting"]["sampling_design"] == "single_case_mechanics"
    assert payload["metrics"]["acceptance_rate"]["confidence_interval_95"] == "NOT_MEASURED"
    assert payload["metrics"]["identity_preserved"]["rate"] == "NOT_MEASURED"
    assert payload["metrics"]["mean_review_seconds"] == "NOT_MEASURED"
    assert payload["cases"][0]["case_id"] == "case-001"
    assert len(payload["cases"]) == 1


def test_preflight_blocks_duplicate_case_ids(tmp_path):
    from stage2_validation import preflight_manifest

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["cases"].append(dict(payload["cases"][0]))
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = preflight_manifest(manifest_path)

    assert report.ok is False
    assert "duplicate case_id: case-001" in report.errors


def test_preflight_blocks_empty_authorized_mask(tmp_path):
    import app
    from PIL import Image
    from stage2_validation import preflight_manifest

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    Image.new("L", (4, 4), 0).save(tmp_path / payload["cases"][0]["mask_path"])

    report = preflight_manifest(manifest_path)

    assert report.ok is False
    assert report.errors == ("case-001: mask has no authorized pixels",)


def test_production_suite_below_sample_floor_stays_not_measured():
    from stage2_validation import aggregate_measurements

    rows = tuple({
        "case_id": f"case-{index:03d}",
        "overall_accept": True,
        "outside_mask_changed_pixels": 0,
        "review": {},
    } for index in range(19))

    report = aggregate_measurements(rows, suite_kind="production_validation")

    assert report.decision_status == "RELIABILITY_NOT_MEASURED"


def test_collect_measurements_blocks_seed_drift_from_frozen_manifest(tmp_path):
    import hashlib
    import app
    from PIL import Image
    import pytest
    from stage2_validation import collect_measurements

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (4, 4), (70, 80, 90)).save(candidate)

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    case = payload["cases"][0]
    provenance = tmp_path / "final-provenance.json"
    provenance.write_text(json.dumps({
        "status": "accepted",
        "source_sha256": digest(tmp_path / case["source_path"]),
        "mask_sha256": digest(tmp_path / case["mask_path"]),
        "guide_sha256": digest(tmp_path / case["guide_path"]),
        "candidate_path": str(candidate),
        "candidate_sha256": digest(candidate),
        "outside_mask_changed_pixels": 0,
        "backend": {
            "model": "models/sdxl-base",
            "seed": 111,
            "parameters": {
                "lora_path": "loras/main-posts/pytorch_lora_weights.safetensors",
                "lora_scale": 0.5,
                "strength": 0.25,
                "steps": 35,
                "guidance_scale": 7.0,
                "padding_mask_crop": 64
            }
        }
    }), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"case_id": "case-001", "overall_accept": True}), encoding="utf-8")
    case["final_provenance_path"] = provenance.name
    case["review_path"] = review.name
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case-001: backend seed mismatch"):
        collect_measurements(manifest_path)


def test_production_suite_at_sample_floor_is_descriptive_not_activation_gate():
    from stage2_validation import aggregate_measurements

    rows = tuple({
        "case_id": f"case-{index:03d}",
        "overall_accept": index % 2 == 0,
        "outside_mask_changed_pixels": 0,
        "review": {},
    } for index in range(20))

    report = aggregate_measurements(rows, suite_kind="production_validation")

    assert report.decision_status == "RELIABILITY_DESCRIBED_THRESHOLDS_NOT_FROZEN"


def test_serialized_acceptance_rate_includes_95_percent_wilson_interval():
    import pytest
    from stage2_validation import aggregate_measurements, serialize_report

    rows = tuple({
        "case_id": f"case-{index:03d}",
        "overall_accept": index < 18,
        "outside_mask_changed_pixels": 0,
        "review": {},
    } for index in range(24))
    report = aggregate_measurements(rows, suite_kind="production_validation")

    payload = serialize_report(report, rows)
    metric = payload["metrics"]["acceptance_rate"]

    assert payload["confidence_reporting"]["method"] == "wilson"
    assert payload["confidence_reporting"]["confidence_level"] == 0.95
    assert payload["confidence_reporting"]["distinct_source_images_required"] is True
    assert payload["confidence_reporting"]["independence_assumption"] == "APPROXIMATE"
    assert payload["confidence_reporting"]["population_generalization"] == "NOT_ESTABLISHED"
    assert metric["numerator"] == 18
    assert metric["denominator"] == 24
    assert metric["rate"] == 0.75
    assert metric["confidence_method"] == "wilson"
    assert metric["confidence_level"] == 0.95
    assert metric["confidence_interval_95"]["lower"] == pytest.approx(0.55100556)
    assert metric["confidence_interval_95"]["upper"] == pytest.approx(0.88000634)


def test_wilson_interval_stays_bounded_for_zero_and_full_success():
    import pytest
    from stage2_validation import Metric

    zero_lower, zero_upper = Metric(0, 24).confidence_interval_95
    full_lower, full_upper = Metric(24, 24).confidence_interval_95

    assert zero_lower == 0.0
    assert zero_upper == pytest.approx(0.13797620)
    assert full_lower == pytest.approx(0.86202380)
    assert full_upper == 1.0


def test_serialized_report_groups_rates_and_failures_by_declared_stratum():
    from stage2_validation import aggregate_measurements, serialize_report

    rows = (
        {"case_id": "s1", "strata": {"object_class": "sheathed_sword"}, "overall_accept": True, "outside_mask_changed_pixels": 0, "review": {}, "rejection_categories": []},
        {"case_id": "s2", "strata": {"object_class": "sheathed_sword"}, "overall_accept": True, "outside_mask_changed_pixels": 0, "review": {}, "rejection_categories": []},
        {"case_id": "s3", "strata": {"object_class": "sheathed_sword"}, "overall_accept": False, "outside_mask_changed_pixels": 0, "review": {}, "rejection_categories": ["object_unrecognizable"]},
        {"case_id": "p1", "strata": {"object_class": "non_weapon_prop"}, "overall_accept": False, "outside_mask_changed_pixels": 0, "review": {}, "rejection_categories": ["floating_object"]},
    )
    report = aggregate_measurements(rows, suite_kind="pilot")

    strata = serialize_report(report, rows)["strata"]["object_class"]

    sword = strata["sheathed_sword"]
    assert sword["total_cases"] == 3
    assert sword["acceptance_rate"]["numerator"] == 2
    assert sword["acceptance_rate"]["denominator"] == 3
    assert sword["rejection_category_counts"] == {"object_unrecognizable": 1}
    assert strata["non_weapon_prop"]["rejection_category_counts"] == {"floating_object": 1}


def test_production_preflight_blocks_duplicate_source_images(tmp_path):
    from stage2_validation import preflight_manifest

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["suite_kind"] = "production_validation"
    duplicate = dict(payload["cases"][0])
    duplicate["case_id"] = "case-002"
    payload["cases"].append(duplicate)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = preflight_manifest(manifest_path)

    assert report.ok is False
    assert report.errors == (
        "duplicate source_sha256 across production cases: case-001, case-002",
    )


def test_aggregation_reports_backend_noop_retry_and_generation_metrics():
    from stage2_validation import aggregate_measurements, serialize_report

    rows = (
        {
            "case_id": "ok",
            "strata": {"object_class": "sheathed_sword"},
            "backend_success": True,
            "no_op": False,
            "second_refinement_attempted": False,
            "generation_seconds": 10.0,
            "overall_accept": True,
            "outside_mask_changed_pixels": 0,
            "review": {},
            "rejection_categories": (),
        },
        {
            "case_id": "failed",
            "strata": {"object_class": "sheathed_sword"},
            "backend_success": False,
            "no_op": None,
            "second_refinement_attempted": True,
            "generation_seconds": 20.0,
            "overall_accept": False,
            "outside_mask_changed_pixels": None,
            "review": {},
            "rejection_categories": ("backend_failure",),
        },
    )

    report = aggregate_measurements(rows, suite_kind="production_validation")
    payload = serialize_report(report, rows)

    assert payload["schema_version"] == 3
    assert payload["metrics"]["acceptance_rate"]["numerator"] == 1
    assert payload["metrics"]["acceptance_rate"]["denominator"] == 2
    assert payload["metrics"]["backend_success_rate"]["numerator"] == 1
    assert payload["metrics"]["backend_success_rate"]["denominator"] == 2
    assert payload["metrics"]["no_op_rate"]["numerator"] == 0
    assert payload["metrics"]["no_op_rate"]["denominator"] == 1
    assert payload["metrics"]["second_refinement_frequency"]["numerator"] == 1
    assert payload["metrics"]["second_refinement_frequency"]["denominator"] == 2
    assert payload["metrics"]["mean_generation_seconds"] == 15.0
    stratum = payload["strata"]["object_class"]["sheathed_sword"]
    assert stratum["backend_success_rate"]["denominator"] == 2
    assert stratum["no_op_rate"]["denominator"] == 1
    assert stratum["second_refinement_frequency"]["denominator"] == 2


def test_collect_measurements_keeps_backend_failure_visible_without_provenance_or_review(tmp_path):
    from stage2_validation import collect_measurements

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = tmp_path / "execution.json"
    execution.write_text(json.dumps({
        "case_id": "case-001",
        "status": "backend_failed",
        "attempts": 1,
        "second_refinement_attempted": False,
        "generation_seconds": 12.5,
        "automatic_publish_events": 0,
        "error_type": "RuntimeError",
        "error_message": "synthetic backend failure",
    }), encoding="utf-8")
    payload["cases"][0]["execution_record_path"] = execution.name
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_measurements(manifest_path)

    assert len(rows) == 1
    assert rows[0]["backend_success"] is False
    assert rows[0]["overall_accept"] is False
    assert rows[0]["generation_seconds"] == 12.5
    assert rows[0]["rejection_categories"] == ("backend_failure",)
    assert rows[0]["provenance_path"] is None
    assert rows[0]["review_path"] is None


def test_serialized_failure_inclusive_report_is_deterministic():
    from stage2_validation import aggregate_measurements, serialize_report

    rows = (
        {
            "case_id": "case-002",
            "strata": {"object_class": "drawn_sword", "lighting": "cool"},
            "backend_success": False,
            "no_op": None,
            "second_refinement_attempted": False,
            "generation_seconds": 9.5,
            "overall_accept": False,
            "outside_mask_changed_pixels": None,
            "review": {},
            "rejection_categories": ("backend_failure",),
        },
        {
            "case_id": "case-001",
            "strata": {"object_class": "sheathed_sword", "lighting": "warm"},
            "backend_success": True,
            "no_op": False,
            "second_refinement_attempted": False,
            "generation_seconds": 8.0,
            "overall_accept": True,
            "outside_mask_changed_pixels": 0,
            "review": {},
            "rejection_categories": (),
        },
    )

    first = serialize_report(
        aggregate_measurements(rows, suite_kind="production_validation"), rows
    )
    second = serialize_report(
        aggregate_measurements(rows, suite_kind="production_validation"), rows
    )

    assert json.dumps(first, indent=2) == json.dumps(second, indent=2)


def test_collect_measurements_falls_back_to_pending_provenance_when_final_absent(tmp_path):
    """The collector must still aggregate a reviewed-but-not-yet-finalized case
    by reading the pending provenance at the conventional output location, since
    finalize_review() promotion is a separate step. Regression guard for the
    pending-provenance fallback branch.
    """
    from stage2_validation import collect_measurements
    from PIL import Image

    manifest_path = _write_valid_pilot(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    # final_provenance_path points at a file that does NOT exist yet
    missing = tmp_path / "final-provenance.json"
    review = tmp_path / "review.json"
    review.write_text(json.dumps({
        "case_id": "case-001",
        "overall_accept": True,
        "gates": {
            "object_recognizable": True,
            "placement_attachment_valid": True,
            "no_duplicate_floating_substitution": True,
            "identity_preserved": True,
            "pose_preserved": True,
            "anatomy_preserved": True,
            "clothing_composition_preserved": True,
        },
        "rejection_categories": [],
    }), encoding="utf-8")

    # pending provenance at the conventional location the collector falls back to.
    # Declare it in the manifest case so the collector resolves it directly
    # (the preferred branch over the hardcoded repo-root convention).
    pending_dir = tmp_path / "tests" / "render_ab" / "output" / "stage2_v1" / "case-001"
    pending_dir.mkdir(parents=True)
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    guide = tmp_path / "guide.png"
    candidate = pending_dir / "candidate.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(candidate)

    import hashlib

    def _sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    pending = pending_dir / "provenance.json"
    pending.write_text(json.dumps({
        "status": "pending_review",
        "source_sha256": _sha(source),
        "mask_sha256": _sha(mask),
        "guide_sha256": _sha(guide),
        "candidate_path": str(candidate),
        "candidate_sha256": _sha(candidate),
        "outside_mask_changed_pixels": 0,
        "outside_mask_max_channel_delta": 0,
        "backend": {
            "model": "models/sdxl-base",
            "seed": 917364,
            "parameters": {
                "strength": 0.25,
                "steps": 35,
                "guidance_scale": 7.0,
                "padding_mask_crop": 64,
                "lora_path": "loras/main-posts/pytorch_lora_weights.safetensors",
                "lora_scale": 0.5,
            },
        },
    }), encoding="utf-8")

    payload["cases"][0]["final_provenance_path"] = missing.name
    payload["cases"][0]["provenance_path"] = str(pending)
    payload["cases"][0]["review_path"] = review.name
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_measurements(manifest_path)

    assert len(rows) == 1
    assert rows[0]["backend_success"] is True
    assert rows[0]["overall_accept"] is True
    assert rows[0]["outside_mask_changed_pixels"] == 0
    # fell back to the pending provenance, not the (absent) final one
    assert str(pending) == rows[0]["provenance_path"]
