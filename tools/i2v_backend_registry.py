"""I2V backend registry (PASS_CPU P0 scaffolding).

SVD-XT 1.1 remains the production default until explicit APPROVE.
Wan 2.2 is registered for additive selection behind I2V_BACKEND /
I2V_WAN_SHADOW (.env.local only — never commit secrets) but has no P0
transport. Selecting Wan without P1 adapter fails closed (no fake
SOCIAL_READY / MEDIA_OUTCOME flip).

Room-locked gates through P3:
- VIDEO_CREATES_IDENTITY_CANON = NO
- SOCIAL_READY_CREATES_IDENTITY_CANON = NO
- LIVE_PUBLISH = NO
- ExclusiveGpuLease KIND_I2V is sequential for all I2V backends: SVD and
  Wan must never be co-resident on the GPU (one KIND_I2V owner at a time).
- Shadow must not flip MEDIA_OUTCOME or enqueue live posts (see guards).
- Media validity (10KB / decode / frames / duration / 1080x1920) already
  lives in tools.media_validity; Wan presented output must use the same
  gate later (hook below — P0 ensures the hook exists, not GPU runs).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Set

# --------------------------------------------------------------------------- #
# Backend IDs
# --------------------------------------------------------------------------- #

BACKEND_ID_SVD_XT_1_1 = "svd_xt_1_1"
BACKEND_ID_WAN_22 = "wan_22"

DEFAULT_I2V_BACKEND = BACKEND_ID_SVD_XT_1_1

ENV_I2V_BACKEND = "I2V_BACKEND"
ENV_I2V_WAN_SHADOW = "I2V_WAN_SHADOW"

# Live publish stays NO through P3 (do not enable here).
LIVE_PUBLISH = "NO"
VIDEO_CREATES_IDENTITY_CANON_GATE = "NO"
SOCIAL_READY_CREATES_IDENTITY_CANON_GATE = "NO"

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}


class UnsupportedBackend(Exception):
    """Backend id is unknown or not selectable for generate (fail closed)."""

    def __init__(self, backend_id: str, message: str) -> None:
        self.backend_id = backend_id
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class BackendRegistration:
    backend_id: str
    selectable_as_default: bool
    """If False, never becomes default via env omission."""
    implementation_ready: bool
    """P0: Wan is registered but False until P1 transport lands."""
    display_name: str
    notes: str = ""


# Allowlist registry. Unknown ids fail closed.
_REGISTRY: Dict[str, BackendRegistration] = {
    BACKEND_ID_SVD_XT_1_1: BackendRegistration(
        backend_id=BACKEND_ID_SVD_XT_1_1,
        selectable_as_default=True,
        implementation_ready=True,
        display_name="SVD-XT 1.1",
        notes="Production default until explicit APPROVE to flip.",
    ),
    BACKEND_ID_WAN_22: BackendRegistration(
        backend_id=BACKEND_ID_WAN_22,
        selectable_as_default=False,
        implementation_ready=True,  # P1: API workflow builder + adapter branch
        display_name="Wan 2.2",
        notes=(
            "Additive I2V port only. Not selectable as default. "
            "P1: build_wan_22_ti2v_workflow transport ready; SVD remains default."
        ),
    ),
}


def registered_backend_ids() -> Set[str]:
    return set(_REGISTRY.keys())


def get_registration(backend_id: str) -> Optional[BackendRegistration]:
    return _REGISTRY.get(backend_id)


def is_registered(backend_id: str) -> bool:
    return backend_id in _REGISTRY


def is_default_backend(backend_id: str) -> bool:
    return backend_id == DEFAULT_I2V_BACKEND


# --------------------------------------------------------------------------- #
# Env helpers (safe defaults)
# --------------------------------------------------------------------------- #


def _env_map(environ: Optional[Mapping[str, str]] = None) -> Mapping[str, str]:
    return environ if environ is not None else os.environ


def parse_env_bool(raw: Optional[str], *, default: bool = False) -> bool:
    """Parse common truthy/falsy env strings; unset -> default."""
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    # Unrecognized -> safe default
    return default


def get_i2v_backend(environ: Optional[Mapping[str, str]] = None) -> str:
    """I2V_BACKEND from env; default svd_xt_1_1. Does not validate selection."""
    env = _env_map(environ)
    raw = str(env.get(ENV_I2V_BACKEND, "") or "").strip()
    if not raw:
        return DEFAULT_I2V_BACKEND
    return raw


def is_i2v_wan_shadow_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """I2V_WAN_SHADOW; default False (0/false/unset)."""
    env = _env_map(environ)
    raw = env.get(ENV_I2V_WAN_SHADOW)
    if raw is None or str(raw).strip() == "":
        return False
    return parse_env_bool(str(raw), default=False)


def i2v_backend_packet_field(backend_id: Optional[str] = None,
                             environ: Optional[Mapping[str, str]] = None) -> str:
    """Packet report line value: I2V_BACKEND=<id>."""
    bid = backend_id if backend_id is not None else get_i2v_backend(environ)
    return f"I2V_BACKEND={bid}"


def gate_status_packet() -> Dict[str, str]:
    """Observability packet for locked gates (P0–P3)."""
    return {
        "I2V_BACKEND": get_i2v_backend(),
        "I2V_WAN_SHADOW": "1" if is_i2v_wan_shadow_enabled() else "0",
        "LIVE_PUBLISH": LIVE_PUBLISH,
        "VIDEO_CREATES_IDENTITY_CANON": VIDEO_CREATES_IDENTITY_CANON_GATE,
        "SOCIAL_READY_CREATES_IDENTITY_CANON": SOCIAL_READY_CREATES_IDENTITY_CANON_GATE,
        "DEFAULT_I2V_BACKEND": DEFAULT_I2V_BACKEND,
    }


# --------------------------------------------------------------------------- #
# Selection / generate gates (fail closed)
# --------------------------------------------------------------------------- #

_WAN_P1_REQUIRED_MSG = (
    "backend_id is registered but implementation_ready=False; "
    "transport required (no fake success). "
    "SVD-XT 1.1 remains default until explicit APPROVE."
)


def validate_backend_registered(backend_id: str) -> None:
    """Raise UnsupportedBackend if id is not on the allowlist."""
    if not is_registered(backend_id):
        raise UnsupportedBackend(
            backend_id,
            f"unsupported backend_id={backend_id}",
        )


def assert_backend_ready_for_generate(backend_id: str) -> None:
    """Fail closed unless backend is registered AND implementation_ready.

    Wan may be selected via I2V_BACKEND / explicit backend_id only after P1
    sets implementation_ready. Shadow flag alone does not unlock generate.
    """
    validate_backend_registered(backend_id)
    reg = _REGISTRY[backend_id]
    if not reg.implementation_ready:
        raise UnsupportedBackend(backend_id, _WAN_P1_REQUIRED_MSG)


def resolve_backend_for_generate(
    backend_id: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Resolve backend id for generate_video; raise UnsupportedBackend if unsafe.

    Prefer explicit backend_id argument; else I2V_BACKEND env; else SVD default.
    """
    if backend_id is None or str(backend_id).strip() == "":
        bid = get_i2v_backend(environ)
    else:
        bid = str(backend_id).strip()
    assert_backend_ready_for_generate(bid)
    return bid


# --------------------------------------------------------------------------- #
# GPU exclusivity + shadow / media-validity hooks (stubs for later phases)
# --------------------------------------------------------------------------- #


def document_exclusive_i2v_gpu_policy() -> str:
    """Human-readable policy: KIND_I2V sequential; no SVD+Wan co-resident."""
    return (
        "ExclusiveGpuLease.KIND_I2V is shared by all I2V backends. "
        "SVD-XT and Wan must never be co-resident: acquire KIND_I2V "
        "sequentially (one owner_job_id at a time). Do not run SVD and Wan "
        "workflows on the same GPU concurrently."
    )


def assert_no_svd_wan_coresident(
    active_backend_id: Optional[str],
    incoming_backend_id: str,
) -> None:
    """Guard stub: refuse starting a second I2V backend while another is active.

    P0: call sites may invoke this before acquire; raises UnsupportedBackend
    when SVD and Wan would overlap. Same-backend re-entrancy is left to
    ExclusiveGpuLease job-id rules.
    """
    if not active_backend_id:
        return
    pair = {active_backend_id, incoming_backend_id}
    if BACKEND_ID_SVD_XT_1_1 in pair and BACKEND_ID_WAN_22 in pair:
        raise UnsupportedBackend(
            incoming_backend_id,
            "refusing SVD+Wan co-resident I2V; ExclusiveGpuLease KIND_I2V "
            "is sequential (one backend at a time)",
        )


def shadow_must_not_flip_media_outcome() -> bool:
    """P0 guard: Wan shadow must not flip MEDIA_OUTCOME or enqueue live posts.

    Returns True as the locked policy constant. Callers that attempt to mark
    SOCIAL_READY or enqueue publish from a shadow path should check this and
    refuse (see assert_shadow_path_inert).
    """
    return True


def assert_shadow_path_inert(
    *,
    proposed_media_outcome: Optional[str] = None,
    enqueue_live_post: bool = False,
    live_publish_enabled: bool = False,
) -> None:
    """Fail closed if shadow/Wan path tries to promote or publish.

    P0: no shadow execution yet; this stub documents and enforces the gate
    for any early call site.
    """
    if live_publish_enabled or LIVE_PUBLISH == "YES":
        raise UnsupportedBackend(
            BACKEND_ID_WAN_22,
            "LIVE_PUBLISH must remain NO through P3; refusing live enqueue",
        )
    if enqueue_live_post:
        raise UnsupportedBackend(
            BACKEND_ID_WAN_22,
            "Wan/shadow path must not enqueue live posts",
        )
    if proposed_media_outcome and str(proposed_media_outcome).upper() in {
        "SOCIAL_READY",
        "READY",
    }:
        # Shadow must not flip MEDIA_OUTCOME to a publishable ready state.
        raise UnsupportedBackend(
            BACKEND_ID_WAN_22,
            "Wan/shadow path must not flip MEDIA_OUTCOME to "
            f"{proposed_media_outcome}",
        )


def wan_media_validity_hook_required() -> bool:
    """P0 hook: Wan presented MP4 must later use tools.media_validity gates.

    Same checks as SVD path: min 10KB, decode, frames, duration, 1080x1920.
    Returns True so call sites can assert the hook is wired before SOCIAL_READY.
    """
    return True


__all__ = [
    "BACKEND_ID_SVD_XT_1_1",
    "BACKEND_ID_WAN_22",
    "DEFAULT_I2V_BACKEND",
    "ENV_I2V_BACKEND",
    "ENV_I2V_WAN_SHADOW",
    "LIVE_PUBLISH",
    "UnsupportedBackend",
    "BackendRegistration",
    "registered_backend_ids",
    "get_registration",
    "is_registered",
    "is_default_backend",
    "parse_env_bool",
    "get_i2v_backend",
    "is_i2v_wan_shadow_enabled",
    "i2v_backend_packet_field",
    "gate_status_packet",
    "validate_backend_registered",
    "assert_backend_ready_for_generate",
    "resolve_backend_for_generate",
    "document_exclusive_i2v_gpu_policy",
    "assert_no_svd_wan_coresident",
    "shadow_must_not_flip_media_outcome",
    "assert_shadow_path_inert",
    "wan_media_validity_hook_required",
]
