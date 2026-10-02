"""Deterministic structural and instance-bound Codex result schemas."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


RESULT_SCHEMA_ID = "hermes.delegation_result/v1"
STRUCTURAL_POLICY_VERSION = "codex-result-structural-policy/v1"
INSTANCE_QUALIFICATION_VERSION = "codex-instance-schema-qualification/v1"
VALIDATOR_POLICY = "codex-structured-output-schema/v1"
QUALIFICATION_STATEMENT = "EA-4D.4F R12E governed delegation proof complete."
_TASK_MARKER = "<instance:task_input_hash>"
_RECEIPT_MARKER = "<instance:receiver_receipt_hash>"


class CodexInstanceSchemaError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_sha256(name: str, value: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise CodexInstanceSchemaError(f"{name} must be a 64-character SHA-256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise CodexInstanceSchemaError(f"{name} must be hexadecimal") from exc
    if value != value.lower():
        raise CodexInstanceSchemaError(f"{name} must use canonical lowercase hexadecimal")


@dataclass(frozen=True)
class CodexResultSchemaLineage:
    task_input_hash: str
    receiver_receipt_hash: str

    def __post_init__(self) -> None:
        _require_sha256("task_input_hash", self.task_input_hash)
        _require_sha256("receiver_receipt_hash", self.receiver_receipt_hash)

    def material(self) -> dict[str, str]:
        return {
            "receiver_receipt_hash": self.receiver_receipt_hash,
            "task_input_hash": self.task_input_hash,
        }

    @property
    def lineage_hash(self) -> str:
        return _sha256(self.material())


@dataclass(frozen=True)
class CodexInstanceSchemaQualification:
    structural_policy_id: str
    instance_schema_sha256: str
    instance_lineage_hash: str
    binary_sha256: str
    binary_version: str
    cli_contract_id: str
    validator_policy: str
    qualification_version: str
    qualification_id: str


def _schema(task_input_hash: str, receiver_receipt_hash: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version", "outcome", "result_payload", "output_manifest",
            "evidence_manifest", "error_code", "error_summary",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1"},
            "outcome": {"type": "string", "const": "SUCCEEDED"},
            "result_payload": {
                "type": "object", "additionalProperties": False,
                "required": ["qualification_statement", "task_input_hash"],
                "properties": {
                    "qualification_statement": {
                        "type": "string", "const": QUALIFICATION_STATEMENT,
                    },
                    "task_input_hash": {
                        "type": "string", "const": task_input_hash,
                    },
                },
            },
            "output_manifest": {
                "type": "array", "maxItems": 0,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": [], "properties": {},
                },
            },
            "evidence_manifest": {
                "type": "array", "minItems": 1, "maxItems": 1,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["ordinal", "evidence_type", "sha256"],
                    "properties": {
                        "ordinal": {"type": "integer", "const": 0},
                        "evidence_type": {
                            "type": "string", "const": "receiver_acceptance_sha256",
                        },
                        "sha256": {
                            "type": "string", "const": receiver_receipt_hash,
                        },
                    },
                },
            },
            "error_code": {"type": "null"},
            "error_summary": {"type": "null"},
        },
    }


def structural_policy_material() -> dict[str, Any]:
    return {
        "policy_version": STRUCTURAL_POLICY_VERSION,
        "result_schema_id": RESULT_SCHEMA_ID,
        "validator_policy": VALIDATOR_POLICY,
        "instance_parameters": {
            "receiver_receipt_hash": {
                "source": "durable_delegation_receipt.artifact_hash",
                "type": "string",
                "format": "sha256-lowercase-hex",
                "required": True,
                "schema_path": "$.properties.evidence_manifest.items.properties.sha256.const",
            },
            "task_input_hash": {
                "source": "canonical_delegated_task.task_input_hash",
                "type": "string",
                "format": "sha256-lowercase-hex",
                "required": True,
                "schema_path": "$.properties.result_payload.properties.task_input_hash.const",
            },
        },
        "schema_template": _schema(_TASK_MARKER, _RECEIPT_MARKER),
    }


def structural_policy_id(material: Optional[dict[str, Any]] = None) -> str:
    return _sha256(structural_policy_material() if material is None else material)


STRUCTURAL_POLICY_ID = structural_policy_id()


def build_instance_bound_result_schema(
    lineage: CodexResultSchemaLineage,
) -> dict[str, Any]:
    if not isinstance(lineage, CodexResultSchemaLineage):
        raise CodexInstanceSchemaError("closed CodexResultSchemaLineage is required")
    return _schema(lineage.task_input_hash, lineage.receiver_receipt_hash)


def qualify_instance_bound_result_schema(
    schema: dict[str, Any],
    *,
    lineage: CodexResultSchemaLineage,
    binary_sha256: str,
    binary_version: str,
    cli_contract_id: str,
    expected_structural_policy_id: str = STRUCTURAL_POLICY_ID,
    expected_qualification_id: Optional[str] = None,
) -> CodexInstanceSchemaQualification:
    _require_sha256("binary_sha256", binary_sha256)
    _require_sha256("cli_contract_id", cli_contract_id)
    _require_sha256("expected_structural_policy_id", expected_structural_policy_id)
    if not isinstance(binary_version, str) or not binary_version.startswith("codex-cli "):
        raise CodexInstanceSchemaError("binary_version is not Codex CLI")
    if expected_structural_policy_id != STRUCTURAL_POLICY_ID:
        raise CodexInstanceSchemaError("structural policy ID mismatch")
    expected_schema = build_instance_bound_result_schema(lineage)
    if _canonical(schema) != _canonical(expected_schema):
        raise CodexInstanceSchemaError("instance schema does not match durable lineage and structural policy")
    schema_sha256 = _sha256(schema)
    material = {
        "binary_sha256": binary_sha256,
        "binary_version": binary_version,
        "cli_contract_id": cli_contract_id,
        "instance_lineage_hash": lineage.lineage_hash,
        "instance_schema_sha256": schema_sha256,
        "qualification_version": INSTANCE_QUALIFICATION_VERSION,
        "structural_policy_id": STRUCTURAL_POLICY_ID,
        "validator_policy": VALIDATOR_POLICY,
    }
    qualification_id = _sha256(material)
    if expected_qualification_id is not None and qualification_id != expected_qualification_id:
        raise CodexInstanceSchemaError("instance schema qualification ID mismatch")
    return CodexInstanceSchemaQualification(
        structural_policy_id=STRUCTURAL_POLICY_ID,
        instance_schema_sha256=schema_sha256,
        instance_lineage_hash=lineage.lineage_hash,
        binary_sha256=binary_sha256,
        binary_version=binary_version,
        cli_contract_id=cli_contract_id,
        validator_policy=VALIDATOR_POLICY,
        qualification_version=INSTANCE_QUALIFICATION_VERSION,
        qualification_id=qualification_id,
    )


def qualify_instance_bound_result_schema_file(
    path: str | Path,
    **kwargs,
) -> CodexInstanceSchemaQualification:
    try:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CodexInstanceSchemaError(f"cannot load instance result schema: {exc}") from exc
    return qualify_instance_bound_result_schema(schema, **kwargs)
