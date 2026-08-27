"""EA-4D.4F constrained Regional Hand Repair ComfyUI adapter.

This is a workload-specific adapter, NOT a generic ComfyUI gateway.
It enforces endpoint, node, template, and asset allowlists.

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
    .hermes/handoffs/ea4d4f/step-1-workflow-manifest.md

Authority limits:
    CPU-only construction. No default live transport.
    Real transport must be injected explicitly in a future/live-runtime slice.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Optional, Tuple

from tools.regional_hand_repair_workflow import (
    ALLOWED_NODE_CLASSES,
    REQUIRED_NODE_CLASSES,
    FROZEN_TEMPLATE_HASH,
    WorkflowValidationError,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Frozen endpoint allowlist
# ---------------------------------------------------------------------------

ALLOWED_SCHEME = "http"
ALLOWED_HOST = "127.0.0.1"
ALLOWED_PORT = 8188

# Allowed ComfyUI API operations
ALLOWED_API_OPERATIONS: FrozenSet[str] = frozenset({
    "POST /prompt",
    "GET /history",
    "GET /view",
    "POST /free",
})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AdapterError(Exception):
    """Base class for adapter errors."""


class EndpointNotAllowedError(AdapterError):
    """The endpoint is not in the allowlist."""


class WorkflowNotAllowedError(AdapterError):
    """The workflow is not in the allowlist."""


class TransportNotConfiguredError(AdapterError):
    """No transport has been configured."""


# ---------------------------------------------------------------------------
# Transport protocol
# ---------------------------------------------------------------------------


class ComfyUITransport:
    """Abstract transport for ComfyUI API operations."""

    def submit_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a workflow and return the response."""
        raise NotImplementedError

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get history for a prompt ID."""
        raise NotImplementedError

    def get_view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        """Get an image by filename."""
        raise NotImplementedError

    def free_memory(self, unload_models: bool = True, free_memory: bool = True) -> Dict[str, Any]:
        """Free GPU memory."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Constrained adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Endpoint:
    """A trusted runtime endpoint."""
    scheme: str
    host: str
    port: int

    def url(self, path: str) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{path}"

    def is_allowed(self) -> bool:
        return (
            self.scheme == ALLOWED_SCHEME
            and self.host == ALLOWED_HOST
            and self.port == ALLOWED_PORT
        )


class RegionalHandRepairComfyUIAdapter:
    """Workload-specific adapter for Regional Hand Repair.

    This adapter is NOT a generic ComfyUI gateway. It is constrained to:
    - One endpoint (127.0.0.1:8188)
    - One workflow template (regional_hand_repair_inpaint)
    - One node allowlist
    - One worker class
    """

    def __init__(
        self,
        *,
        transport: Optional[ComfyUITransport] = None,
        endpoint: Optional[Endpoint] = None,
    ) -> None:
        self._transport = transport
        self._endpoint = endpoint or Endpoint(
            scheme=ALLOWED_SCHEME,
            host=ALLOWED_HOST,
            port=ALLOWED_PORT,
        )

        if not self._endpoint.is_allowed():
            raise EndpointNotAllowedError(
                f"endpoint {self._endpoint.scheme}://{self._endpoint.host}:{self._endpoint.port} "
                f"is not in the allowlist"
            )

    @property
    def endpoint(self) -> Endpoint:
        return self._endpoint

    @property
    def has_transport(self) -> bool:
        return self._transport is not None

    def _require_transport(self) -> ComfyUITransport:
        if self._transport is None:
            raise TransportNotConfiguredError(
                "no transport configured; inject a transport for live execution"
            )
        return self._transport

    def validate_workflow_envelope(self, workflow: Dict[str, Any]) -> None:
        """Validate a workflow against the frozen repair contract.

        Raises:
            WorkflowNotAllowedError: if the workflow fails validation.
        """
        result = validate_workflow(workflow)
        if not result.valid:
            raise WorkflowNotAllowedError(
                f"workflow validation failed: {'; '.join(result.errors)}"
            )

        if result.template_hash != FROZEN_TEMPLATE_HASH:
            raise WorkflowNotAllowedError(
                f"template hash mismatch: expected {FROZEN_TEMPLATE_HASH[:16]}..., "
                f"got {result.template_hash[:16]}..."
            )

    def submit_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a validated workflow to ComfyUI.

        Args:
            workflow: The workflow dict to submit.

        Returns:
            The ComfyUI response dict.

        Raises:
            WorkflowNotAllowedError: if the workflow fails validation.
            TransportNotConfiguredError: if no transport is configured.
        """
        self.validate_workflow_envelope(workflow)
        transport = self._require_transport()
        return transport.submit_workflow(workflow)

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get history for a prompt ID."""
        transport = self._require_transport()
        return transport.get_history(prompt_id)

    def get_view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        """Get an image by filename."""
        transport = self._require_transport()
        return transport.get_view(filename, subfolder, type_)

    def free_memory(self, unload_models: bool = True, free_memory: bool = True) -> Dict[str, Any]:
        """Free GPU memory."""
        transport = self._require_transport()
        return transport.free_memory(unload_models, free_memory)


# ---------------------------------------------------------------------------
# Fake transport for tests
# ---------------------------------------------------------------------------


class FakeComfyUITransport(ComfyUITransport):
    """In-memory fake transport for CPU-only tests."""

    def __init__(self) -> None:
        self.submissions: list[Dict[str, Any]] = []
        self.history: Dict[str, Dict[str, Any]] = {}
        self.images: Dict[str, bytes] = {}
        self.free_calls: list[Dict[str, bool]] = []
        self._counter = 0

    def submit_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        self.submissions.append(workflow)
        self._counter += 1
        prompt_id = f"fake-prompt-{self._counter}"
        response = {"prompt_id": prompt_id, "number": self._counter}
        self.history[prompt_id] = {
            "outputs": {
                "R9": {
                    "images": [
                        {"filename": f"regional_hand_repair_{self._counter:05d}.png",
                         "subfolder": "", "type": "output"}
                    ]
                }
            }
        }
        return response

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        return self.history.get(prompt_id, {})

    def get_view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        if filename not in self.images:
            # Generate a deterministic fake image
            self.images[filename] = b"fake-image-bytes"
        return self.images[filename]

    def free_memory(self, unload_models: bool = True, free_memory: bool = True) -> Dict[str, Any]:
        self.free_calls.append({"unload_models": unload_models, "free_memory": free_memory})
        return {"status": "ok"}
