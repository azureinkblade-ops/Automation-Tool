"""Image Pipeline V2 — application-owned provenance persistence (B4).

This module is the application persistence owner for Image Pipeline V2
provenance. It does NOT recompute any pipeline-owned value: it consumes the
``V2ExecutionResult`` produced by the qualified pipeline + B3 execution layer
(``tools.image_pipeline_v2_execution.execute_v2``) and projects it into a
small, versioned, deterministic, output-bound record.

Design constraints honored (see remediation brief):
  - PROVENANCE_RECOMPUTED_BY_CALLER = NO  (values pass through from the result)
  - PROVENANCE_SCHEMA_VERSIONED = YES     (explicit schema_version)
  - OUTPUT_TO_PROVENANCE_BINDING_DETERMINISTIC = YES (sidecar next to output)
  - PROVENANCE_WRITE_ATOMIC = YES         (temp + flush + os.replace)
  - PROVENANCE_PERSISTENCE_FAILURE_FAILS_CLOSED = YES (raises; caller must not
    report success)
  - PROVENANCE_OVERWRITE_PROTECTION = YES (a completed execution id is not
    overwritten)
  - FAILURE_PROVENANCE_TRUTHFUL = YES     (no fabricated output/success claims)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

IMAGE_PIPELINE_V2_PROVENANCE_VERSION = "image_pipeline_v2_provenance_v1"

SCHEMA_VERSION = IMAGE_PIPELINE_V2_PROVENANCE_VERSION


def v2_provenance_path(output_path: Any) -> Path:
    """Deterministic sidecar path bound to the generated output.

    ``<output>.v2provenance.json`` sits adjacent to the application-owned
    output so the binding is stable and discoverable without a separate index.
    """
    p = Path(str(output_path))
    return p.with_name(f"{p.name}.v2provenance.json")


def v2_failure_sidecar_path(output_path: Any, execution_id: Optional[str] = None) -> Path:
    """Distinct, attempt/execution-specific failure-evidence sidecar.

    Lives alongside the canonical success sidecar but is never the canonical
    output provenance. Bound to the actual failed execution id so that repeated
    failed retries each retain their own truthful evidence without ever
    touching the completed-success record.
    """
    p = Path(str(output_path))
    exec_part = execution_id or "unknown"
    return p.with_name(f"{p.name}.v2failure.{exec_part}.json")


def _dig(d: Optional[Dict[str, Any]], *keys: str) -> Any:
    cur: Any = d if isinstance(d, dict) else None
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _extract_lora(prov: Dict[str, Any]) -> Dict[str, Any]:
    """Pull LoRA identity/strength from the pipeline provenance (pass-through).

    Does not recompute: it reads the asset_id / sha256 / strengths that the
    qualified pipeline already placed in its provenance.
    """
    block = prov.get("main_posts_lora") or prov.get("realistic_lora")
    loras = prov.get("loras") or []
    strengths = prov.get("lora_strengths") or {}
    asset_id = None
    sha256 = None
    model_strength = None
    clip_strength = None
    if isinstance(block, dict):
        asset_id = block.get("asset_id")
        sha256 = block.get("sha256")
    if asset_id is None and loras:
        first = loras[0] if isinstance(loras[0], dict) else {}
        asset_id = first.get("name")
        sha256 = first.get("hash")
        model_strength = first.get("weight")
    if asset_id is not None and model_strength is None:
        model_strength = strengths.get(asset_id)
    return {
        "asset_id": asset_id,
        "sha256": sha256,
        "model_strength": model_strength,
        "clip_strength": clip_strength,
    }


def _cleanup_to_record(cleanup: Any) -> Optional[Dict[str, Any]]:
    if cleanup is None:
        return None
    if isinstance(cleanup, dict):
        return dict(cleanup)
    c = cleanup
    return {
        "attempted": getattr(c, "attempted", None),
        "free_http_status": getattr(c, "free_http_status", None),
        "comfyui_reachable_post": getattr(c, "comfyui_reachable_post", None),
        "pre_cleanup_vram_mib": getattr(c, "pre_cleanup_vram_mib", None),
        "post_cleanup_vram_mib": getattr(c, "post_cleanup_vram_mib", None),
        "vram_released_mib": getattr(c, "vram_released_mib", None),
        "cleanup_effective": getattr(c, "cleanup_effective", None),
        "cleanup_anomaly": getattr(c, "cleanup_anomaly", None),
        "cleanup_status": getattr(c, "cleanup_status", None),
        "note": getattr(c, "note", ""),
    }


def build_v2_provenance_record(
    result: Any,
    *,
    caller: Optional[str] = None,
    abbr: Optional[str] = None,
    index: Optional[int] = None,
    style: Optional[str] = None,
    promo_id: Optional[str] = None,
    archive_destination: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Project a B3 ``V2ExecutionResult`` into a versioned, normalized record.

    All pipeline/execution facts are taken verbatim from ``result`` (and its
    nested ``provenance``); nothing is recomputed or assumed here.
    """
    prov = dict(getattr(result, "provenance", None) or {})
    lora = _extract_lora(prov)

    dims = prov.get("dimensions") or prov.get("resolution")
    width = height = None
    if isinstance(dims, (list, tuple)) and len(dims) >= 2:
        width, height = dims[0], dims[1]

    checkpoint_id = _dig(prov, "checkpoint_identity", "asset_id") or prov.get("checkpoint")
    checkpoint_sha = _dig(prov, "checkpoint_identity", "sha256") or prov.get("checkpoint_hash")

    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        # Profile / style
        "profile": getattr(result, "profile", None),
        "style": style,
        "pipeline_implementation_identity": prov.get("pipeline")
        or prov.get("pipeline_implementation")
        or prov.get("pipeline_implementation_id"),
        # Spec / workflow identity
        "generation_spec_sha256": prov.get("generation_spec_sha256"),
        "workflow_template_sha256": prov.get("workflow_sha256"),
        "resolved_workflow_sha256": prov.get("resolved_workflow_sha256")
        or prov.get("built_workflow_sha256"),
        # Checkpoint identity
        "checkpoint_asset_id": checkpoint_id,
        "checkpoint_sha256": checkpoint_sha,
        # LoRA identity
        "lora_asset_id": lora.get("asset_id"),
        "lora_sha256": lora.get("sha256"),
        "lora_model_strength": lora.get("model_strength"),
        "lora_clip_strength": lora.get("clip_strength"),
        # Generation params
        "seed": prov.get("seed"),
        "sampler": prov.get("sampler"),
        "scheduler": prov.get("scheduler"),
        "steps": prov.get("steps"),
        "cfg": prov.get("cfg"),
        "width": width,
        "height": height,
        # Execution identity
        "execution_id": getattr(result, "execution_id", None),
        "comfyui_prompt_id": getattr(result, "prompt_id", None),
        "execution_status": getattr(result, "status", None),
        # Output identity
        "output_path": getattr(result, "output_path", None),
        "output_identity": getattr(result, "output_path", None),
        "output_sha256": getattr(result, "output_sha256", None),
        # Pre-execution state
        "gpu_preflight_result": getattr(result, "gpu_preflight", None) or {},
        "ollama_preflight_result": getattr(result, "ollama_preflight", None) or {},
        # Cleanup outcome (anomaly preserved, never collapsed to success)
        "cleanup_result": _cleanup_to_record(getattr(result, "cleanup", None)),
        # Failure evidence (only meaningful when failed)
        "primary_error": getattr(result, "primary_error", None),
        "error_type": getattr(result, "error_type", None),
        "duplicate": bool(getattr(result, "duplicate", False)),
        # Application context (added by the caller; never overwrites pipeline facts)
        "caller": caller,
        "abbr": abbr,
        "index": index,
        "promo_id": promo_id,
        "archive_destination": archive_destination,
        "generated_at": generated_at or time.strftime("%Y-%m-%d %H:%M:%S"),
        # Raw pipeline/execution passthrough (serializable projection)
        "pipeline_provenance": prov,
    }
    return record


def build_v2_failure_record(
    result: Any,
    *,
    caller: Optional[str] = None,
    abbr: Optional[str] = None,
    index: Optional[int] = None,
    style: Optional[str] = None,
    promo_id: Optional[str] = None,
    archive_destination: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Truthful failure record. Never claims output SHA / successful generation.

    Distinct from the success projection: a failed execution records its
    execution identity, profile, failure class, primary error, submission
    evidence (prompt id), and cleanup outcome, but does NOT assert an output
    SHA256 or a successful archive.
    """
    prov = dict(getattr(result, "provenance", None) or {})
    output_path = getattr(result, "output_path", None)
    output_exists = bool(output_path) and Path(str(output_path)).exists()
    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": getattr(result, "profile", None),
        "style": style,
        "execution_id": getattr(result, "execution_id", None),
        "comfyui_prompt_id": getattr(result, "prompt_id", None),
        "execution_status": "failed",
        "failure_class": getattr(result, "error_type", None),
        "primary_error": getattr(result, "primary_error", None)
        or getattr(result, "error_type", "V2ExecutionError"),
        "submitted": getattr(result, "prompt_id", None) is not None,
        "output_exists": output_exists,
        "output_path": output_path if output_exists else None,
        "output_sha256": None,
        "gpu_preflight_result": getattr(result, "gpu_preflight", None) or {},
        "ollama_preflight_result": getattr(result, "ollama_preflight", None) or {},
        "cleanup_result": _cleanup_to_record(getattr(result, "cleanup", None)),
        "duplicate": bool(getattr(result, "duplicate", False)),
        "caller": caller,
        "abbr": abbr,
        "index": index,
        "promo_id": promo_id,
        "archive_destination": archive_destination,
        "generated_at": generated_at or time.strftime("%Y-%m-%d %H:%M:%S"),
        "pipeline_provenance": prov,
    }
    return record


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Serialize deterministically, write temp, flush, atomic replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def persist_v2_provenance(
    output_path: Any,
    result: Any,
    *,
    caller: Optional[str] = None,
    abbr: Optional[str] = None,
    index: Optional[int] = None,
    style: Optional[str] = None,
    promo_id: Optional[str] = None,
    archive_destination: Optional[str] = None,
    overwrite: bool = False,
) -> Path:
    """Persist complete V2 provenance for a SUCCESSFUL execution.

    Fail-closed: raises on write failure. Overwrite-protected: a completed
    execution with the same execution_id is not silently overwritten.
    """
    record = build_v2_provenance_record(
        result,
        caller=caller,
        abbr=abbr,
        index=index,
        style=style,
        promo_id=promo_id,
        archive_destination=archive_destination,
    )
    path = v2_provenance_path(output_path)
    if not overwrite and path.exists():
        existing = read_v2_provenance(output_path)
        if (
            isinstance(existing, dict)
            and existing.get("execution_id") == record.get("execution_id")
            and existing.get("execution_status") == "success"
        ):
            # Completed prior execution: do not overwrite its provenance.
            return path
    _atomic_write_json(path, record)
    return path


def persist_v2_failure_provenance(
    output_path: Any,
    result: Any,
    *,
    caller: Optional[str] = None,
    abbr: Optional[str] = None,
    index: Optional[int] = None,
    style: Optional[str] = None,
    promo_id: Optional[str] = None,
    archive_destination: Optional[str] = None,
) -> Path:
    """Persist truthful failure evidence (no output/success claims).

    Overwrite protection: if a completed-success provenance already owns the
    canonical ``<output>.v2provenance.json`` sidecar, a later failed retry must
    not clobber that completed record. The failure evidence is instead retained
    in a distinct, execution-specific sidecar so the canonical record stays
    immutable. When no completed-success record exists, the failure evidence is
    written to the canonical sidecar per the existing B4 contract
    (``FAILURE_WITHOUT_EXISTING_SUCCESS_STILL_RECORDED``).
    """
    record = build_v2_failure_record(
        result,
        caller=caller,
        abbr=abbr,
        index=index,
        style=style,
        promo_id=promo_id,
        archive_destination=archive_destination,
    )
    path = v2_provenance_path(output_path)
    # Completed-success canonical ownership guard: never replace a completed
    # output-bound success record with a later failure. A failed retry instead
    # retains its own truthful evidence in a distinct sidecar.
    if path.exists():
        existing = read_v2_provenance(output_path)
        if isinstance(existing, dict) and existing.get("execution_status") == "success":
            failure_path = v2_failure_sidecar_path(
                output_path, getattr(result, "execution_id", None)
            )
            _atomic_write_json(failure_path, record)
            return failure_path
    _atomic_write_json(path, record)
    return path


def read_v2_provenance(output_path: Any) -> Optional[Dict[str, Any]]:
    path = v2_provenance_path(output_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass
class AppContext:
    """Optional application context the caller may attach (never a pipeline fact)."""

    caller: Optional[str] = None
    abbr: Optional[str] = None
    index: Optional[int] = None
    style: Optional[str] = None
    promo_id: Optional[str] = None
    archive_destination: Optional[str] = None
