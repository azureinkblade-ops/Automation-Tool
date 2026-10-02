"""Image Pipeline V2 — single canonical approved-asset registry (CPU-only).

This module is the ONE authoritative owner of the V2 approved-asset registry.
``main_posts_pipeline_v2`` and ``realistic_pipeline_v2`` previously each held a
duplicated copy of ``ApprovedAsset``, ``_APPROVED_REGISTRY``, ``resolve_asset``,
and the ComfyUI-reference helpers. Those duplicated copies had drifted (e.g.
``sdxl_base_1.0`` carried different ``pipeline_role`` metadata in each copy).

Unification contract (enforced by tests):
  - Exactly one ``ApprovedAsset`` definition.
  - Exactly one ``_APPROVED_REGISTRY`` (the canonical tuple below).
  - Exactly one ``resolve_asset`` implementation.
  - The pipeline modules consume this module and re-export the symbols for
    backward-compatible imports; they MUST NOT own independent registry data.

Authoritative source: M4 asset manifest (image_pipeline_v2_m4_asset_manifest_20260818.json,
M4_ASSET_PROVISIONING_AUTHORITY). The registry values (asset identity, path,
SHA-256, asset class, provisioned state) are taken verbatim from that manifest;
no asset identity, path, SHA pin, model selection, or LoRA selection is altered
by this unification. ``pipeline_role`` is descriptive metadata only and is not
consumed by ``resolve_asset`` (resolution is by unique asset identity, never by
role), so unifying it cannot change effective asset selection or fail-closed
behavior.

This module performs NO GPU work and NO ComfyUI I/O at import time.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Asset root (shared; verbatim from M4 manifest LOCAL_PATH / CANONICAL_PATH)
# --------------------------------------------------------------------------- #

_ASSET_ROOT = Path(r"C:\Users\David\Documents\Automation tool")


# --------------------------------------------------------------------------- #
# Approved asset record (single definition)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ApprovedAsset:
    asset_id: str
    asset_class: str
    canonical_path: str
    comfyui_reference: str
    sha256: str
    pipeline_role: Tuple[str, ...]
    provisioned: bool


# --------------------------------------------------------------------------- #
# Canonical approved-asset registry (single authoritative owner)
# --------------------------------------------------------------------------- #
#
# Values sourced verbatim from the M4 asset manifest. Membership is the union of
# every approved asset across Main Posts and Realistic V2 (and the comic
# foundation they share). ``sdxl_base_1.0`` legitimately serves the
# ``("comic", "realistic", "main_posts")`` roles: the M4 manifest records the
# base checkpoint as the shared foundation for the comic and realistic bases,
# and Main Posts V2 resolves it as ``MAIN_POSTS_CHECKPOINT_ASSET_ID``.

_APPROVED_REGISTRY: Tuple[ApprovedAsset, ...] = (
    ApprovedAsset(
        asset_id="sdxl_base_1.0",
        asset_class="SDXL_CHECKPOINT",
        canonical_path=str(_ASSET_ROOT / "models" / "sdxl-base" / "sd_xl_base_1.0.safetensors"),
        comfyui_reference="sd_xl_base_1.0.safetensors",
        sha256="31E35C80FC4829D14F90153F4C74CD59C90B779F6AFE05A74CD6120B893F7E5B",
        pipeline_role=("comic", "realistic", "main_posts"),
        provisioned=True,
    ),
    ApprovedAsset(
        asset_id="lora_main_posts",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "main-posts" / "pytorch_lora_weights.safetensors"),
        comfyui_reference="main-posts/pytorch_lora_weights.safetensors",
        sha256="5093D90510BF1E40B12B49776F54EB5D1C6019B41203066444C35554619EF69B",
        pipeline_role=("main_posts",),
        provisioned=True,
    ),
    ApprovedAsset(
        asset_id="lora_realistic_posts",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "realistic_posts" / "pytorch_lora_weights.safetensors"),
        comfyui_reference="realistic_posts/pytorch_lora_weights.safetensors",
        sha256="FF795D7028D3473083901EBCE2CC7B284D12FF6C904E7834428A0213CD92C564",
        pipeline_role=("realistic",),
        provisioned=True,
    ),
    ApprovedAsset(
        asset_id="lora_comic_style",
        asset_class="LoRA",
        canonical_path=str(_ASSET_ROOT / "loras" / "comic-style"),
        comfyui_reference="",
        sha256="",
        pipeline_role=("comic",),
        provisioned=False,  # NOT_YET_TRAINED (M5 concern, not M6)
    ),
    ApprovedAsset(
        asset_id="controlnet_openpose_sdxl_1.0",
        asset_class="STRUCTURAL_CONDITIONING",
        canonical_path=str(
            _ASSET_ROOT / "models" / "controlnet-openpose-sdxl-1.0" / "diffusion_pytorch_model.safetensors"
        ),
        # Backend-visible ComfyUI ControlNetLoader value. ``extra_model_paths.yaml``
        # maps the ComfyUI ``controlnet`` category root directly to
        # ``models/controlnet-openpose-sdxl-1.0`` (the file's own directory), so the
        # accepted ``control_net_name`` is the bare filename
        # ``diffusion_pytorch_model.safetensors`` — NOT the Automation-Tool-asset-root
        # relative path ``controlnet-openpose-sdxl-1.0/diffusion_pytorch_model.safetensors``.
        # This is the single authoritative backend reference (Strategy A); it is
        # consistent with ``sdxl_base_1.0`` (basename-only, checkpoint root = file dir)
        # and the LoRAs (subdir/basename, lora root = ``loras``).
        comfyui_reference="diffusion_pytorch_model.safetensors",
        sha256="B8524E557A7DF60D081F5D4A0EB109967D107DF217943BF88C2D99B9EBCC06C5",
        pipeline_role=("comic", "realistic"),
        provisioned=True,
    ),
)


# --------------------------------------------------------------------------- #
# ComfyUI reference helpers (single implementation)
# --------------------------------------------------------------------------- #


def derive_comfyui_reference(canonical_path: str) -> str:
    """Deterministic ComfyUI-visible model reference (last two path components)."""
    p = Path(canonical_path)
    return f"{p.parent.name}/{p.name}"


def normalize_comfyui_reference(reference: str) -> str:
    """Normalize a ComfyUI model reference to the backend's path-separator form.

    Mirrors the M6 Defect 3 remediation: the live ComfyUI 0.33.2 backend builds
    its accepted model-name list with the host OS separator (``os.sep``), so on
    Windows a forward-slash LoRA reference is rejected with ``value_not_in_list``.
    Normalizing the execution-visible reference to ``os.sep`` reconciles the
    approved M4 semantic reference with the backend's canonical form without
    altering asset identity, canonical path, SHA, or the load-bearing topology.
    Empty references (unprovisioned assets) are returned unchanged.
    """
    if not reference:
        return reference
    return reference.replace("/", os.sep).replace("\\", os.sep)


# --------------------------------------------------------------------------- #
# Deterministic, fail-closed asset resolution (single implementation)
# --------------------------------------------------------------------------- #


class AssetResolutionError(Exception):
    """Fail-closed error raised when an asset cannot be resolved deterministically."""


_FULL_RESOLVE_CACHE: Dict[str, ApprovedAsset] = {}


def resolve_asset(
    asset_id: str,
    *,
    read_bytes: Optional[Callable[[str], bytes]] = None,
) -> ApprovedAsset:
    """Deterministically resolve an approved asset from its authoritative identity.

    Fail-closed if zero/multiple assets match, the asset is unprovisioned, the
    on-disk SHA-256 does not match the approved manifest, or reads fail.

    `read_bytes` lets tests inject deterministic content; when None the real file
    is read and cached so the multi-GB checkpoint is not re-read per call.
    """
    if read_bytes is None and asset_id in _FULL_RESOLVE_CACHE:
        return _FULL_RESOLVE_CACHE[asset_id]
    matches = [a for a in _APPROVED_REGISTRY if a.asset_id == asset_id]
    if len(matches) == 0:
        raise AssetResolutionError(f"no approved asset resolves for identity {asset_id!r}")
    if len(matches) > 1:
        raise AssetResolutionError(
            f"ambiguous asset identity {asset_id!r} resolves to {len(matches)} approved assets; "
            f"resolution must be by unique asset identity, not basename"
        )
    asset = matches[0]
    if not asset.provisioned:
        raise AssetResolutionError(
            f"asset {asset_id!r} is not provisioned (NOT_YET_TRAINED / MISSING); "
            f"cannot resolve for V2"
        )

    used_default_reader = read_bytes is None
    if read_bytes is None:
        read_bytes = lambda p: Path(p).read_bytes()  # noqa: E731
    try:
        data = read_bytes(asset.canonical_path)
    except OSError as exc:
        raise AssetResolutionError(
            f"cannot read asset {asset_id!r} at {asset.canonical_path!r}: {exc}"
        )

    actual_sha = hashlib.sha256(data).hexdigest().upper()
    if actual_sha != asset.sha256.upper():
        raise AssetResolutionError(
            f"asset {asset_id!r} SHA mismatch: on-disk {actual_sha} != approved {asset.sha256}"
        )

    if used_default_reader:
        _FULL_RESOLVE_CACHE[asset_id] = asset
    return asset


def resolve_asset_by_basename(basename: str) -> List[ApprovedAsset]:
    """Simulates the dangerous basename-only resolution pattern.

    Returns every approved asset whose on-disk file basename equals `basename`.
    When this returns more than one asset, basename-only resolution is ambiguous
    and MUST be rejected. Pipelines must never use this path; it is provided so
    tests can prove the ambiguity fail-closed guarantee.
    """
    return [a for a in _APPROVED_REGISTRY if Path(a.canonical_path).name == basename]


# --------------------------------------------------------------------------- #
# Registry integrity: backend-reference uniqueness (fail-closed)
# --------------------------------------------------------------------------- #
#
# ComfyUI scopes accepted model names per model-category root (checkpoints,
# loras, controlnet, ...). The stored ``comfyui_reference`` is the exact
# backend-visible identifier (relative to that category root). If two approved
# assets within the same ``asset_class`` exposed the same normalized backend
# reference, the loader could not distinguish them and basename-only selection
# would be ambiguous. This guard fails closed at import time without ever
# selecting by basename.


def validate_registry_backend_reference_uniqueness() -> None:
    """Raise ``AssetResolutionError`` if two same-class assets share a backend ref.

    Empty (unprovisioned) references are ignored because they carry no backend
    value. The check operates on the *full* normalized reference, so distinct
    sub-paths within the same category (e.g. ``main-posts/...`` vs
    ``realistic_posts/...``) do not collide.
    """
    by_class: Dict[str, List[Tuple[str, str]]] = {}
    for a in _APPROVED_REGISTRY:
        if not a.comfyui_reference:
            continue
        key = normalize_comfyui_reference(a.comfyui_reference)
        by_class.setdefault(a.asset_class, []).append((a.asset_id, key))
    for asset_class, entries in by_class.items():
        seen: Dict[str, str] = {}
        for asset_id, key in entries:
            if key in seen:
                raise AssetResolutionError(
                    f"duplicate backend reference {key!r} across {asset_class} assets "
                    f"{seen[key]!r} and {asset_id!r}; resolution must be unique, not by basename"
                )
            seen[key] = asset_id


validate_registry_backend_reference_uniqueness()
