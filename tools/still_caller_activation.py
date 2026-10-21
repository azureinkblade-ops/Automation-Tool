"""Resolve still-caller V2 + Promo Master flags together (CPU).

V2: tools.still_v2_activation.resolve_still_v2_enabled
PM: tools.promo_master_production.resolve_activation (existing env parser)

PM ON with effective V2 OFF fails closed before generation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from tools.promo_master_production import resolve_activation
from tools.still_v2_activation import resolve_still_v2_enabled


class StillCallerActivationError(RuntimeError):
    """PM requested while effective V2 is OFF."""


def resolve_still_caller_flags(
    *,
    v2_explicit: Optional[bool],
    pm_explicit: Optional[bool],
    novel: Any = None,
    seam: Any = None,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    v2 = resolve_still_v2_enabled(
        v2_explicit, novel=novel, seam=seam, environ=environ
    )
    pm = resolve_activation(
        explicit=pm_explicit, environ=environ, novel=novel, seam=seam
    )
    if pm["enabled"] and not v2["enabled"]:
        raise StillCallerActivationError(
            "promo_master_enabled requires V2; will not master a legacy image"
        )
    return {
        "v2_enabled": bool(v2["enabled"]),
        "v2_source": v2["source"],
        "pm_enabled": bool(pm["enabled"]),
        "pm_source": pm["source"],
        "pm_explicit": pm_explicit,
    }


def promo_master_generate_kwargs(act: Dict[str, Any]) -> Dict[str, Any]:
    """Pass already-resolved PM decision into generate_promo_image_v2. No second consume."""
    if act.get("pm_explicit") is not None:
        return {"promo_master_enabled": act["pm_explicit"]}
    if act.get("pm_enabled") and act.get("pm_source") == "bounded_rollout":
        return {
            "promo_master_enabled": True,
            "promo_master_activation_source": "bounded_rollout",
        }
    return {}
