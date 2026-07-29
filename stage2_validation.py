"""CPU-only validation harness for Stage 2 object refinement."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import sqrt
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Metric:
    numerator: int
    denominator: int

    @property
    def rate(self) -> Optional[float]:
        return self.numerator / self.denominator if self.denominator else None

    @property
    def confidence_interval_95(self) -> Optional[Tuple[float, float]]:
        """Return the two-sided 95% Wilson score interval for a binomial rate."""
        if not self.denominator:
            return None
        z = 1.959963984540054
        n = self.denominator
        proportion = self.numerator / n
        denominator = 1 + (z * z / n)
        center = (proportion + z * z / (2 * n)) / denominator
        margin = (
            z
            * sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n))
            / denominator
        )
        lower = 0.0 if self.numerator == 0 else max(0.0, center - margin)
        upper = 1.0 if self.numerator == n else min(1.0, center + margin)
        return lower, upper


@dataclass(frozen=True)
class ValidationReport:
    suite_kind: str
    total_cases: int
    acceptance: Metric
    exact_outside_mask_preservation: Metric
    backend_success: Metric
    no_op: Metric
    second_refinement: Metric
    gates: Mapping[str, Metric]
    missing_review_fields: Mapping[str, Tuple[str, ...]]
    mean_preparation_seconds: Optional[float]
    mean_review_seconds: Optional[float]
    mean_manual_intervention_cycles: Optional[float]
    mean_generation_seconds: Optional[float]
    decision_status: str


REVIEW_GATES = (
    "object_recognizable",
    "placement_attachment_valid",
    "no_duplicate_floating_substitution",
    "identity_preserved",
    "pose_preserved",
    "anatomy_preserved",
    "clothing_composition_preserved",
)


def _measured_mean(rows: Sequence[Mapping[str, Any]], field: str) -> Optional[float]:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return mean(values) if values else None


def aggregate_measurements(
    rows: Sequence[Mapping[str, Any]],
    *,
    suite_kind: str,
) -> ValidationReport:
    """Aggregate only explicitly measured fields with visible denominators."""
    accepted_values = [row["overall_accept"] for row in rows if isinstance(row.get("overall_accept"), bool)]
    acceptance = Metric(sum(1 for value in accepted_values if value), len(accepted_values))
    outside_values = [
        int(row["outside_mask_changed_pixels"])
        for row in rows
        if row.get("outside_mask_changed_pixels") is not None
    ]
    outside = Metric(sum(1 for value in outside_values if value == 0), len(outside_values))
    backend_values = [
        row["backend_success"]
        for row in rows
        if isinstance(row.get("backend_success"), bool)
    ]
    no_op_values = [
        row["no_op"] for row in rows if isinstance(row.get("no_op"), bool)
    ]
    retry_values = [
        row["second_refinement_attempted"]
        for row in rows
        if isinstance(row.get("second_refinement_attempted"), bool)
    ]
    backend_success = Metric(
        sum(1 for value in backend_values if value), len(backend_values)
    )
    no_op = Metric(sum(1 for value in no_op_values if value), len(no_op_values))
    second_refinement = Metric(
        sum(1 for value in retry_values if value), len(retry_values)
    )
    gates = {}
    missing = {}
    for gate in REVIEW_GATES:
        measured = []
        for row in rows:
            value = dict(row.get("review", {})).get(gate)
            if isinstance(value, bool):
                measured.append(value)
        gates[gate] = Metric(sum(1 for value in measured if value), len(measured))
    for row in rows:
        review = dict(row.get("review", {}))
        absent = tuple(gate for gate in REVIEW_GATES if not isinstance(review.get(gate), bool))
        if absent:
            missing[str(row.get("case_id", ""))] = absent
    if suite_kind == "pilot":
        decision_status = "HARNESS_VALIDATED" if rows else "RELIABILITY_NOT_MEASURED"
    elif len(rows) < 20:
        decision_status = "RELIABILITY_NOT_MEASURED"
    else:
        decision_status = "RELIABILITY_DESCRIBED_THRESHOLDS_NOT_FROZEN"
    return ValidationReport(
        suite_kind=suite_kind,
        total_cases=len(rows),
        acceptance=acceptance,
        exact_outside_mask_preservation=outside,
        backend_success=backend_success,
        no_op=no_op,
        second_refinement=second_refinement,
        gates=gates,
        missing_review_fields=missing,
        mean_preparation_seconds=_measured_mean(rows, "preparation_seconds"),
        mean_review_seconds=_measured_mean(rows, "review_seconds"),
        mean_manual_intervention_cycles=_measured_mean(rows, "manual_intervention_cycles"),
        mean_generation_seconds=_measured_mean(rows, "generation_seconds"),
        decision_status=decision_status,
    )


@dataclass(frozen=True)
class PreflightCase:
    case_id: str
    source_path: Path
    mask_path: Path
    guide_path: Optional[Path]
    source_sha256: str
    mask_sha256: str
    guide_sha256: Optional[str]
    mask_authorized_pixels: int
    mask_coverage: float
    strata: Mapping[str, str]
    generation_config: Mapping[str, Any]


@dataclass(frozen=True)
class PreflightReport:
    ok: bool
    suite_id: str
    suite_kind: str
    cases: Tuple[PreflightCase, ...]
    errors: Tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(base: Path, raw: Optional[str]) -> Optional[Path]:
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base / path).resolve()


def _serialize_metric(metric: Metric) -> Mapping[str, Any]:
    interval = metric.confidence_interval_95
    return {
        "numerator": metric.numerator,
        "denominator": metric.denominator,
        "rate": metric.rate if metric.rate is not None else "NOT_MEASURED",
        "confidence_method": "wilson",
        "confidence_level": 0.95,
        "confidence_interval_95": (
            {"lower": interval[0], "upper": interval[1]}
            if interval is not None
            else "NOT_MEASURED"
        ),
    }


def _serialize_strata(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    dimensions = sorted({
        str(dimension)
        for row in rows
        for dimension in dict(row.get("strata", {}))
    })
    serialized = {}
    for dimension in dimensions:
        values = sorted({
            str(dict(row.get("strata", {}))[dimension])
            for row in rows
            if dimension in dict(row.get("strata", {}))
        })
        serialized[dimension] = {}
        for value in values:
            subset = [
                row for row in rows
                if str(dict(row.get("strata", {})).get(dimension)) == value
            ]
            accepted = [
                row["overall_accept"] for row in subset
                if isinstance(row.get("overall_accept"), bool)
            ]
            outside = [
                int(row["outside_mask_changed_pixels"]) for row in subset
                if row.get("outside_mask_changed_pixels") is not None
            ]
            backend = [
                row["backend_success"] for row in subset
                if isinstance(row.get("backend_success"), bool)
            ]
            no_op = [
                row["no_op"] for row in subset
                if isinstance(row.get("no_op"), bool)
            ]
            retries = [
                row["second_refinement_attempted"] for row in subset
                if isinstance(row.get("second_refinement_attempted"), bool)
            ]
            rejection_counts = {}
            for row in subset:
                for category in row.get("rejection_categories", []):
                    key = str(category)
                    rejection_counts[key] = rejection_counts.get(key, 0) + 1
            serialized[dimension][value] = {
                "total_cases": len(subset),
                "acceptance_rate": _serialize_metric(Metric(
                    sum(1 for result in accepted if result), len(accepted)
                )),
                "exact_outside_mask_preservation_rate": _serialize_metric(Metric(
                    sum(1 for changed in outside if changed == 0), len(outside)
                )),
                "backend_success_rate": _serialize_metric(Metric(
                    sum(1 for result in backend if result), len(backend)
                )),
                "no_op_rate": _serialize_metric(Metric(
                    sum(1 for result in no_op if result), len(no_op)
                )),
                "second_refinement_frequency": _serialize_metric(Metric(
                    sum(1 for result in retries if result), len(retries)
                )),
                "rejection_category_counts": dict(sorted(rejection_counts.items())),
            }
    return serialized


def serialize_report(
    report: ValidationReport,
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    metrics = {
        "acceptance_rate": _serialize_metric(report.acceptance),
        "exact_outside_mask_preservation_rate": _serialize_metric(
            report.exact_outside_mask_preservation
        ),
        "backend_success_rate": _serialize_metric(report.backend_success),
        "no_op_rate": _serialize_metric(report.no_op),
        "second_refinement_frequency": _serialize_metric(report.second_refinement),
    }
    metrics.update({name: _serialize_metric(metric) for name, metric in report.gates.items()})
    metrics.update({
        "mean_preparation_seconds": report.mean_preparation_seconds
        if report.mean_preparation_seconds is not None else "NOT_MEASURED",
        "mean_review_seconds": report.mean_review_seconds
        if report.mean_review_seconds is not None else "NOT_MEASURED",
        "mean_manual_intervention_cycles": report.mean_manual_intervention_cycles
        if report.mean_manual_intervention_cycles is not None else "NOT_MEASURED",
        "mean_generation_seconds": report.mean_generation_seconds
        if report.mean_generation_seconds is not None else "NOT_MEASURED",
    })
    case_rows = []
    for row in rows:
        normalized = dict(row)
        normalized["strata"] = dict(row.get("strata", {}))
        normalized["review"] = dict(row.get("review", {}))
        normalized["rejection_categories"] = list(row.get("rejection_categories", []))
        case_rows.append(normalized)
    return {
        "schema_version": 3,
        "suite_kind": report.suite_kind,
        "decision_status": report.decision_status,
        "total_cases": report.total_cases,
        "confidence_reporting": {
            "method": "wilson",
            "confidence_level": 0.95,
            "applies_to": "binomial_rate_metrics",
            "sampling_design": (
                "quota_stratified"
                if report.suite_kind == "production_validation"
                else "single_case_mechanics"
            ),
            "distinct_source_images_required": report.suite_kind == "production_validation",
            "independence_assumption": "APPROXIMATE",
            "population_generalization": "NOT_ESTABLISHED",
            "interpretation": (
                "Intervals quantify uncertainty in observed case-level proportions; "
                "the suite design does not establish a random sample of all future images."
            ),
        },
        "metrics": metrics,
        "strata": _serialize_strata(rows),
        "missing_review_fields": {
            case_id: list(fields) for case_id, fields in report.missing_review_fields.items()
        },
        "cases": case_rows,
    }


def write_validation_report(manifest_path: Path, output_path: Path) -> Mapping[str, Any]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = collect_measurements(manifest_path)
    report = aggregate_measurements(rows, suite_kind=str(payload.get("suite_kind", "")))
    serialized = serialize_report(report, rows)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    return serialized


def collect_measurements(manifest_path: Path) -> Tuple[Mapping[str, Any], ...]:
    """Collect hash-verified mechanical evidence and structured human reviews."""
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    preflight = preflight_manifest(manifest_path)
    if not preflight.ok:
        raise ValueError("preflight failed: " + "; ".join(preflight.errors))
    preflight_by_id = {row.case_id: row for row in preflight.cases}
    collected = []
    for raw in payload["cases"]:
        case_id = str(raw["case_id"])
        fixture = preflight_by_id[case_id]
        execution_path = _resolve(manifest_path.parent, raw.get("execution_record_path"))
        execution = {}
        if raw.get("execution_record_path") is not None:
            if execution_path is None or not execution_path.exists():
                raise ValueError(f"{case_id}: execution_record_path missing")
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            if execution.get("case_id") != case_id:
                raise ValueError(f"{case_id}: execution record case_id mismatch")
            if int(execution.get("automatic_publish_events", 0)) != 0:
                raise ValueError(f"{case_id}: automatic publishing event recorded")
            if execution.get("status") not in {"completed", "backend_failed"}:
                raise ValueError(f"{case_id}: execution status is not terminal")
        if execution.get("status") == "backend_failed":
            collected.append({
                "case_id": case_id,
                "strata": dict(fixture.strata),
                "generation_status": "backend_failed",
                "backend_success": False,
                "no_op": None,
                "second_refinement_attempted": execution.get(
                    "second_refinement_attempted"
                ),
                "generation_seconds": execution.get("generation_seconds"),
                "overall_accept": False,
                "outside_mask_changed_pixels": None,
                "review": {},
                "rejection_categories": ("backend_failure",),
                "preparation_seconds": execution.get("preparation_seconds"),
                "review_seconds": None,
                "manual_intervention_cycles": execution.get(
                    "manual_intervention_cycles"
                ),
                "provenance_path": None,
                "review_path": None,
                "execution_record_path": str(execution_path),
                "backend_error_type": execution.get("error_type"),
                "backend_error_message": execution.get("error_message"),
            })
            continue
        provenance_path = _resolve(manifest_path.parent, raw.get("final_provenance_path"))
        is_final = provenance_path is not None and provenance_path.exists()
        if not is_final:
            # Review phase: the pending provenance is the authoritative artifact
            # until finalize_review() promotes it. Fall back to the declared or
            # conventional pending path so the descriptive report can aggregate
            # reviewed-but-not-yet-finalized cases.
            pending = _resolve(manifest_path.parent, raw.get("provenance_path"))
            if pending is None:
                pending = (
                    manifest_path.parent
                    / ".."
                    / ".."
                    / "tests"
                    / "render_ab"
                    / "output"
                    / "stage2_v1"
                    / case_id
                    / "provenance.json"
                ).resolve()
            provenance_path = pending
        review_path = _resolve(manifest_path.parent, raw.get("review_path"))
        if provenance_path is None or not provenance_path.exists():
            raise ValueError(f"{case_id}: provenance file missing (checked final then pending)")
        if review_path is None or not review_path.exists():
            raise ValueError(f"{case_id}: review_path missing")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if provenance.get("source_sha256") != fixture.source_sha256:
            raise ValueError(f"{case_id}: provenance source hash mismatch")
        if provenance.get("mask_sha256") != fixture.mask_sha256:
            raise ValueError(f"{case_id}: provenance mask hash mismatch")
        if provenance.get("guide_sha256") != fixture.guide_sha256:
            raise ValueError(f"{case_id}: provenance guide hash mismatch")
        backend = dict(provenance.get("backend", {}))
        parameters = dict(backend.get("parameters", {}))
        declared = fixture.generation_config
        comparisons = (
            ("model", backend.get("model"), declared.get("model")),
            ("seed", backend.get("seed"), declared.get("seed")),
            ("lora", parameters.get("lora_path"), declared.get("lora")),
            ("lora_scale", parameters.get("lora_scale"), declared.get("lora_scale")),
            ("strength", parameters.get("strength"), declared.get("strength")),
            ("steps", parameters.get("steps"), declared.get("steps")),
            ("guidance_scale", parameters.get("guidance_scale"), declared.get("guidance_scale")),
            ("padding_mask_crop", parameters.get("padding_mask_crop"), declared.get("padding_mask_crop")),
        )
        for field, observed, expected in comparisons:
            if field in {"model", "lora"}:
                observed_norm = str(observed).replace("\\", "/").lower()
                expected_norm = str(expected).replace("\\", "/").lower()
                matches = observed_norm == expected_norm or observed_norm.endswith("/" + expected_norm)
            else:
                matches = observed == expected
            if not matches:
                raise ValueError(f"{case_id}: backend {field} mismatch")
        candidate_path = Path(str(provenance.get("candidate_path", "")))
        if not candidate_path.exists():
            raise ValueError(f"{case_id}: candidate missing")
        if _sha256(candidate_path) != provenance.get("candidate_sha256"):
            raise ValueError(f"{case_id}: provenance candidate hash mismatch")
        if review.get("case_id") != case_id:
            raise ValueError(f"{case_id}: review case_id mismatch")
        collected.append({
            "case_id": case_id,
            "strata": dict(fixture.strata),
            "generation_status": provenance.get("status"),
            "backend_success": True,
            "no_op": provenance.get("candidate_sha256") == fixture.source_sha256,
            "second_refinement_attempted": execution.get(
                "second_refinement_attempted"
            ),
            "generation_seconds": execution.get("generation_seconds"),
            "overall_accept": review.get("overall_accept"),
            "outside_mask_changed_pixels": provenance.get("outside_mask_changed_pixels"),
            "review": dict(review.get("gates", {})),
            "rejection_categories": tuple(review.get("rejection_categories", [])),
            "preparation_seconds": review.get("preparation_seconds"),
            "review_seconds": review.get("review_seconds"),
            "manual_intervention_cycles": review.get("manual_intervention_cycles"),
            "provenance_path": str(provenance_path),
            "review_path": str(review_path),
            "execution_record_path": str(execution_path) if execution_path else None,
        })
    return tuple(collected)


def preflight_manifest(manifest_path: Path) -> PreflightReport:
    """Validate fixture mechanics without invoking a refinement backend."""
    from PIL import Image

    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    errors = []
    rows = []
    seen = set()
    for raw in payload.get("cases", []):
        case_id = str(raw.get("case_id", "")).strip()
        if not case_id:
            errors.append("case missing case_id")
            continue
        if case_id in seen:
            errors.append(f"duplicate case_id: {case_id}")
            continue
        seen.add(case_id)
        source = _resolve(base, raw.get("source_path"))
        mask = _resolve(base, raw.get("mask_path"))
        guide = _resolve(base, raw.get("guide_path"))
        missing = [str(p) for p in (source, mask, guide) if p is not None and not p.exists()]
        if missing:
            errors.append(f"{case_id}: missing files: {', '.join(missing)}")
            continue
        if source is None or mask is None:
            errors.append(f"{case_id}: source_path and mask_path are required")
            continue
        config = dict(raw.get("generation_config", {}))
        required_config = (
            "model", "lora", "lora_scale", "seed", "strength", "steps",
            "guidance_scale", "padding_mask_crop",
        )
        missing_config = [key for key in required_config if key not in config]
        if missing_config:
            errors.append(
                f"{case_id}: generation_config missing: {', '.join(missing_config)}"
            )
            continue
        source_image = Image.open(source).convert("RGB")
        mask_image = Image.open(mask).convert("L")
        if source_image.size != mask_image.size:
            errors.append(f"{case_id}: source and mask dimensions differ")
            continue
        if guide is not None and Image.open(guide).size != source_image.size:
            errors.append(f"{case_id}: source and guide dimensions differ")
            continue
        authorized = sum(1 for value in mask_image.getdata() if value > 0)
        if authorized == 0:
            errors.append(f"{case_id}: mask has no authorized pixels")
            continue
        total = source_image.width * source_image.height
        rows.append(PreflightCase(
            case_id=case_id,
            source_path=source,
            mask_path=mask,
            guide_path=guide,
            source_sha256=_sha256(source),
            mask_sha256=_sha256(mask),
            guide_sha256=_sha256(guide) if guide else None,
            mask_authorized_pixels=authorized,
            mask_coverage=authorized / total,
            strata=dict(raw.get("strata", {})),
            generation_config=dict(raw.get("generation_config", {})),
        ))
    if not payload.get("cases"):
        errors.append("manifest has no cases")
    if payload.get("suite_kind") == "production_validation":
        source_cases = {}
        for row in rows:
            source_cases.setdefault(row.source_sha256, []).append(row.case_id)
        for case_ids in source_cases.values():
            if len(case_ids) > 1:
                errors.append(
                    "duplicate source_sha256 across production cases: "
                    + ", ".join(case_ids)
                )
    return PreflightReport(
        ok=not errors,
        suite_id=str(payload.get("suite_id", "")),
        suite_kind=str(payload.get("suite_kind", "")),
        cases=tuple(rows),
        errors=tuple(errors),
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate Stage 2 refinement evidence")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = write_validation_report(args.manifest, args.output)
    print(json.dumps({
        "decision_status": payload["decision_status"],
        "total_cases": payload["total_cases"],
        "output": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
