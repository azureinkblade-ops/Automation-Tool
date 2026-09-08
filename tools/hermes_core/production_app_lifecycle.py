"""In-process lifecycle ownership for one governed production request.

The owner requires an existing explicit binding, delegates once to the
qualified host action, and tears down that exact binding in ``finally``.
It does not bind, issue authority, activate production, retry, or select a
fallback receiver.
"""

from __future__ import annotations

from typing import Any, Mapping

from tools.hermes_core.production_app_host import (
    ProductionAppHostAction,
    ProductionAppHostResult,
)
from tools.hermes_core.production_executor_binding import (
    ProductionExecutorBindingController,
)


class ProductionAppRequestLifecycleOwner:
    """Own one already-bound governed request through in-process teardown."""

    def __init__(
        self,
        governed_action: ProductionAppHostAction | None,
        binding_controller: ProductionExecutorBindingController | None,
    ) -> None:
        self._governed_action = governed_action
        self._binding_controller = binding_controller

    def submit(self, payload: Mapping[str, Any] | None) -> ProductionAppHostResult:
        if self._governed_action is None or self._binding_controller is None:
            return self._deny("MISSING_REQUEST_LIFECYCLE_DEPENDENCY")

        if not isinstance(payload, Mapping):
            return self._governed_action.submit(payload)

        receiver_id = payload.get("receiver_id")
        if not isinstance(receiver_id, str) or not receiver_id.strip():
            return self._governed_action.submit(payload)

        binding = self._binding_controller.get_binding_for_receiver(receiver_id)
        if binding is None:
            return self._deny("MISSING_EXPLICIT_BINDING")

        result: ProductionAppHostResult | None = None
        action_error: Exception | None = None
        cleanup_error: str | None = None
        try:
            result = self._governed_action.submit(payload)
        except Exception as exc:
            action_error = exc
        finally:
            try:
                if not self._binding_controller.teardown(binding):
                    cleanup_error = "BINDING_TEARDOWN_NOT_CONFIRMED"
            except Exception as exc:
                cleanup_error = f"BINDING_TEARDOWN_EXCEPTION:{type(exc).__name__}"

        if cleanup_error is not None:
            return self._deny(cleanup_error)
        if action_error is not None:
            return self._deny(f"GOVERNED_ACTION_EXCEPTION:{type(action_error).__name__}")
        if result is None:
            return self._deny("MISSING_GOVERNED_ACTION_RESULT")
        return result

    @staticmethod
    def _deny(reason: str) -> ProductionAppHostResult:
        return ProductionAppHostResult(decision="DENY", reason=reason)
