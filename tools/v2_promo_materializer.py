"""Image Pipeline V2 - production materializer (application runtime owner).

Single concrete production owner for V2 promo materialization. It delegates to
the already-qualified B3 execution stack (tools.image_pipeline_v2_execution) and
does NOT reimplement VRAM preflight, Ollama contention handling, submission
protection, output validation, /free semantics, or cleanup verification.

The HttpComfyUIExecutionClient is constructed lazily (only when a V2 execution is
actually requested), so importing this module or app.py performs no ComfyUI
contact and no GPU allocation.

B4 provenance ownership remains in app.generate_promo_image_v2 (which persists the
returned V2ExecutionResult via persist_v2_provenance); this module does not
reimplement provenance.

Ordinary production materialization uses the B3 default (cold) preflight and
cleanup_mode="auto". Warm/resident preflight and deferred cleanup are task-owned
concerns reserved for a future explicit multi-replica task owner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from tools.image_pipeline_v2_execution import (
    CLEANUP_MODE_AUTO,
    HttpComfyUIExecutionClient,
    PREFLIGHT_COLD,
    execute_v2,
)


def materialize_v2_promo(
    profile: str,
    resolution: Any,
    target: Any,
    *,
    client: Optional[Any] = None,
    cleanup_mode: str = CLEANUP_MODE_AUTO,
    preflight: str = PREFLIGHT_COLD,
) -> Any:
    """Production V2 materializer (3-arg contract used by app.generate_promo_image_v2).

    Lazily constructs the local ComfyUI HTTP client (when not injected) and
    executes the resolved V2 request through the qualified B3 execute_v2
    contract. Returns the V2ExecutionResult so the caller applies B4 provenance
    and fail-closed semantics.
    """
    target_path = Path(target)
    if client is None:
        # Local-only client, constructed on demand (never at import time).
        client = HttpComfyUIExecutionClient()
    return execute_v2(
        profile,
        resolution,
        target_path,
        client=client,
        cleanup_mode=cleanup_mode,
        preflight=preflight,
    )
