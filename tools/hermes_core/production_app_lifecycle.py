"""In-process lifecycle ownership for one governed production request.

The owner requires an existing explicit binding, delegates once to the
qualified host action, and tears down that exact binding in ``finally``.
It does not bind, issue authority, activate production, retry, or select a
fallback receiver.
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Mapping

from tools.hermes_core.production_app_host import (
    ProductionAppHostAction,
    ProductionAppHostResult,
)
from tools.hermes_core.production_executor_binding import (
    ProductionExecutorBindingController,
)


class ProductionRequestAdmissionController:
    """Fail closed when another request owns the single lifecycle slot."""

    def __init__(self) -> None:
        self._state_lock = Lock()
        self._owner_request_id: str | None = None

    def acquire(self, request_id: str) -> bool:
        with self._state_lock:
            if self._owner_request_id is not None:
                return False
            self._owner_request_id = request_id
            return True

    def release(self, request_id: str) -> bool:
        with self._state_lock:
            if self._owner_request_id != request_id:
                return False
            self._owner_request_id = None
            return True

    @property
    def owner_request_id(self) -> str | None:
        with self._state_lock:
            return self._owner_request_id


class ProductionAppRequestLifecycleOwner:
    """Own one already-bound governed request through in-process teardown."""

    def __init__(
        self,
        governed_action: ProductionAppHostAction | None,
        binding_controller: ProductionExecutorBindingController | None,
        admission_controller: ProductionRequestAdmissionController | None = None,
    ) -> None:
        self._governed_action = governed_action
        self._binding_controller = binding_controller
        self._admission_controller = (
            admission_controller
            if admission_controller is not None
            else ProductionRequestAdmissionController()
        )

    def submit(self, payload: Mapping[str, Any] | None) -> ProductionAppHostResult:
        if self._governed_action is None or self._binding_controller is None:
            return self._deny("MISSING_REQUEST_LIFECYCLE_DEPENDENCY")

        if not isinstance(payload, Mapping):
            return self._governed_action.submit(payload)

        receiver_id = payload.get("receiver_id")
        if not isinstance(receiver_id, str) or not receiver_id.strip():
            return self._governed_action.submit(payload)

        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            return self._deny("MISSING_REQUEST_ID")

        if not self._admission_controller.acquire(request_id):
            return self._deny("PRODUCTION_REQUEST_CONCURRENCY_LIMIT")

        try:
            return self._submit_admitted(payload, receiver_id)
        finally:
            self._admission_controller.release(request_id)

    def _submit_admitted(
        self,
        payload: Mapping[str, Any],
        receiver_id: str,
    ) -> ProductionAppHostResult:
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
