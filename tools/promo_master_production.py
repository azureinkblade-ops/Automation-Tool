"""Promo Master v1 production integration (CPU). Downstream of V2 stills.

Does not own Studio Bible, prompts, checkpoints, or V2 generation.
Calls tools.promo_master_deterministic.finish_image. Does not duplicate it.
Default OFF. Explicit override beats persistent env. Enabled failure fails closed.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PIL import Image

from tools import promo_master_deterministic as dpm

PROMO_MASTER_VERSION = "v1"
IMPLEMENTATION_ID = "tools.promo_master_deterministic"
ENV_FLAG = "PROMO_MASTER_ENABLED"
MASTER_SUFFIX = ".master.png"
PROVENANCE_SUFFIX = ".master.promo_master.json"
FAILURE_SUFFIX = ".master.failure.json"
POSTING_READY_ACTIVATION_SOURCES = frozenset({"explicit", "persistent", "bounded_rollout"})

GENERATIVE_MODEL_USED = False
LEARNED_UPSCALER_USED = False
GPU_USED = False
COMFYUI_USED = False


class PromoMasterProductionError(RuntimeError):
    """Enabled Promo Master finishing failed. Base image must remain."""


def _flag_on(raw: Any) -> bool:
    return str(raw if raw is not None else "").strip().lower() not in {
        "",
        "0",
        "false",
        "no",
        "off",
    }


def persistent_enabled(*, environ: Optional[Dict[str, str]] = None) -> bool:
    env = environ if environ is not None else os.environ
    return _flag_on(env.get(ENV_FLAG, "0"))


def resolve_activation(
    *,
    explicit: Optional[bool] = None,
    persistent: Optional[bool] = None,
    environ: Optional[Dict[str, str]] = None,
    novel: Any = None,
    seam: Any = None,
) -> Dict[str, Any]:
    """explicit -> persistent PROMO_MASTER_ENABLED -> bounded rollout -> default OFF."""
    pers = persistent if persistent is not None else persistent_enabled(environ=environ)
    if explicit is not None:
        return {"enabled": bool(explicit), "source": "explicit", "persistent": bool(pers)}
    if pers:
        return {"enabled": True, "source": "persistent", "persistent": True}
    from tools.promo_master_activation import admit_omitted_promo_master

    admitted = admit_omitted_promo_master(novel=novel, seam=seam)
    admitted["persistent"] = False
    return admitted


def master_path_for(base: Path) -> Path:
    base = Path(base)
    if is_master_path(base):
        raise PromoMasterProductionError("refusing master-of-master: source is already a master")
    return base.with_name(base.stem + MASTER_SUFFIX)


def provenance_path_for(base: Path) -> Path:
    return base.with_name(base.stem + PROVENANCE_SUFFIX)


def failure_path_for(base: Path) -> Path:
    return base.with_name(base.stem + FAILURE_SUFFIX)


def is_master_path(path: Path) -> bool:
    name = Path(path).name.lower()
    return name.endswith(".master.png") or ".master." in name


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _algorithm_fields() -> Dict[str, Any]:
    return {
        "promo_master_version": PROMO_MASTER_VERSION,
        "implementation": IMPLEMENTATION_ID,
        "resize_method": dpm.RESIZE_METHOD,
        "sharpen_method": dpm.SHARPEN_METHOD,
        "sharpen_radius": dpm.SHARPEN_RADIUS,
        "sharpen_amount": dpm.SHARPEN_AMOUNT,
        "sharpen_threshold": dpm.SHARPEN_THRESHOLD,
        "GENERATIVE_MODEL_USED": GENERATIVE_MODEL_USED,
        "LEARNED_UPSCALER_USED": LEARNED_UPSCALER_USED,
        "GPU_USED": GPU_USED,
        "COMFYUI_USED": COMFYUI_USED,
    }


@dataclass
class PromoMasterResult:
    enabled: bool
    activation_source: str
    status: str  # skipped | reused | written | failed
    base_path: str
    base_sha256: str
    master_path: Optional[str] = None
    master_sha256: Optional[str] = None
    provenance_path: Optional[str] = None
    failure_path: Optional[str] = None
    error: Optional[str] = None


def apply_promo_master(
    base_path: Path,
    *,
    explicit: Optional[bool] = None,
    persistent: Optional[bool] = None,
    environ: Optional[Dict[str, str]] = None,
    finish_image: Optional[Callable[[Image.Image], Image.Image]] = None,
    activation_source: Optional[str] = None,
) -> PromoMasterResult:
    """Finish a V2 base still if enabled. Never mutates the base file."""
    base_path = Path(base_path)
    if activation_source is not None:
        act = {
            "enabled": bool(explicit),
            "source": str(activation_source),
            "persistent": False,
        }
    else:
        act = resolve_activation(explicit=explicit, persistent=persistent, environ=environ)
    if not base_path.is_file():
        raise PromoMasterProductionError(f"base image missing: {base_path}")
    if is_master_path(base_path):
        raise PromoMasterProductionError("refusing master-of-master: source is already a master")
    before = sha256_file(base_path)
    if not act["enabled"]:
        return PromoMasterResult(
            enabled=False,
            activation_source=act["source"],
            status="skipped",
            base_path=str(base_path),
            base_sha256=before,
        )
    finisher = finish_image or dpm.finish_image
    dest = master_path_for(base_path)
    prov_path = provenance_path_for(base_path)
    fail_path = failure_path_for(base_path)
    try:
        if dest.is_file() and prov_path.is_file():
            existing = json.loads(prov_path.read_text(encoding="utf-8"))
            if (
                existing.get("source_sha256") == before
                and existing.get("resize_method") == dpm.RESIZE_METHOD
                and existing.get("sharpen_method") == dpm.SHARPEN_METHOD
                and existing.get("sharpen_radius") == dpm.SHARPEN_RADIUS
                and existing.get("sharpen_amount") == dpm.SHARPEN_AMOUNT
                and existing.get("sharpen_threshold") == dpm.SHARPEN_THRESHOLD
            ):
                after = sha256_file(base_path)
                if after != before:
                    raise PromoMasterProductionError("base SHA changed during reuse check")
                return PromoMasterResult(
                    enabled=True,
                    activation_source=act["source"],
                    status="reused",
                    base_path=str(base_path),
                    base_sha256=before,
                    master_path=str(dest),
                    master_sha256=sha256_file(dest),
                    provenance_path=str(prov_path),
                )
        with Image.open(base_path) as opened:
            src_im = opened.convert("RGB") if opened.mode not in ("RGB", "RGBA") else opened.copy()
            src_mode = opened.mode if opened.mode in ("RGB", "RGBA") else "RGB"
            src_size = opened.size
        master = finisher(src_im)
        if master.size != dpm.FINAL_OUTPUT:
            raise PromoMasterProductionError(f"master size {master.size} is not 2048x2048")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dpm.save_png(master, dest)
        after = sha256_file(base_path)
        if after != before:
            raise PromoMasterProductionError("base SHA changed during mastering")
        master_sha = sha256_file(dest)
        payload = {
            **_algorithm_fields(),
            "source_path": str(base_path),
            "source_sha256": before,
            "source_dimensions": list(src_size),
            "source_mode": src_mode,
            "master_path": str(dest),
            "master_sha256": master_sha,
            "master_dimensions": list(master.size),
            "master_mode": master.mode,
            "activation_source": act["source"],
        }
        prov_path.write_text(_canonical_json(payload), encoding="utf-8")
        return PromoMasterResult(
            enabled=True,
            activation_source=act["source"],
            status="written",
            base_path=str(base_path),
            base_sha256=before,
            master_path=str(dest),
            master_sha256=master_sha,
            provenance_path=str(prov_path),
        )
    except PromoMasterProductionError as exc:
        _write_failure(fail_path, base_path, before, dest, act, type(exc).__name__, str(exc))
        after = sha256_file(base_path) if base_path.is_file() else ""
        if after and after != before:
            raise PromoMasterProductionError(
                f"base SHA changed during failure handling ({before} -> {after})"
            ) from exc
        raise PromoMasterProductionError(str(exc)) from exc
    except Exception as exc:
        _write_failure(fail_path, base_path, before, dest, act, type(exc).__name__, str(exc))
        after = sha256_file(base_path) if base_path.is_file() else ""
        if after and after != before:
            raise PromoMasterProductionError(
                f"base SHA changed during failure handling ({before} -> {after})"
            ) from exc
        raise PromoMasterProductionError(f"Promo Master finishing failed: {exc}") from exc


def posting_image_from_promo_master_out(
    *,
    promo_master_enabled: bool,
    promo_master_out: Optional[Dict[str, Any]],
    base_path: Path,
) -> Path:
    """Select the posting artifact. Enabled mastering never silently returns the base."""
    base = Path(base_path)
    if not promo_master_enabled:
        return base
    captured = promo_master_out if isinstance(promo_master_out, dict) else None
    if not captured:
        raise PromoMasterProductionError("promo_master_out was not captured")
    err = captured.get("error")
    if err:
        raise PromoMasterProductionError(f"Promo Master failed: {err}")
    status = str(captured.get("status") or "")
    if status not in {"written", "reused"}:
        raise PromoMasterProductionError(
            f"Promo Master status {status!r} is not posting-ready; will not fall back to base"
        )
    if captured.get("enabled") is not True:
        raise PromoMasterProductionError(
            "Promo Master capture is not enabled=True; will not fall back to base"
        )
    if str(captured.get("activation_source") or "") not in POSTING_READY_ACTIVATION_SOURCES:
        raise PromoMasterProductionError(
            "Promo Master activation_source is not posting-ready; will not fall back to base"
        )
    master_raw = captured.get("master_path")
    if not master_raw:
        raise PromoMasterProductionError("missing master_path despite enabled Promo Master")
    master = Path(str(master_raw))
    if not master.is_file():
        raise PromoMasterProductionError(f"master_path does not exist: {master}")
    if master.resolve() == base.resolve():
        raise PromoMasterProductionError("master_path equals base_path; refusing to post the base as master")
    return master


def _write_failure(
    fail_path: Path,
    base_path: Path,
    source_sha: str,
    dest: Path,
    act: Dict[str, Any],
    failure_type: str,
    message: str,
) -> None:
    payload = {
        **_algorithm_fields(),
        "source_path": str(base_path),
        "source_sha256": source_sha,
        "requested_master_path": str(dest),
        "failure_type": failure_type,
        "failure_message": message,
        "activation_source": act["source"],
    }
    fail_path.write_text(_canonical_json(payload), encoding="utf-8")
