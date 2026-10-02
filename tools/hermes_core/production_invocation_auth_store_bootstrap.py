"""EA-4E.47 explicit deployment bootstrap for invocation-auth storage.

Bootstrap is an operator-invoked filesystem step. It is not application
construction, startup, authorization issuance, claim, consumption, or execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.hermes_core.durable_invocation_authorization_store import (
    AUTH_STORE_SCHEMA_ID,
    AUTH_STORE_SCHEMA_VERSION,
    DurableAuthorizationStoreError,
    DurableInvocationAuthorizationStore,
)


@dataclass(frozen=True)
class ProductionInvocationAuthStoreBootstrapRequest:
    store_path: str | Path | None
    anchor_path: str | Path | None
    bootstrap_explicit: bool | None


@dataclass(frozen=True)
class ProductionInvocationAuthStoreBootstrapResult:
    bootstrap_decision: str
    bootstrap_reason: str
    requested_store_path: str | None = None
    requested_anchor_path: str | None = None
    canonical_store_path: str | None = None
    canonical_anchor_path: str | None = None
    schema_id: str | None = None
    schema_version: str | None = None
    store_instance_id: str | None = None
    store_generation: int | None = None
    error_detail: str | None = None


class ProductionInvocationAuthStoreBootstrapper:
    """Stateless explicit bootstrap boundary around the qualified store."""

    def bootstrap(
        self,
        request: ProductionInvocationAuthStoreBootstrapRequest | None,
    ) -> ProductionInvocationAuthStoreBootstrapResult:
        if request is None:
            return self._deny("MISSING_REQUEST")
        if not isinstance(request, ProductionInvocationAuthStoreBootstrapRequest):
            return self._deny("MALFORMED_REQUEST")

        requested_store = self._requested_value(request.store_path)
        requested_anchor = self._requested_value(request.anchor_path)
        if requested_store is None:
            return self._deny("MISSING_STORE_PATH")
        if requested_anchor is None:
            return self._deny(
                "MISSING_ANCHOR_PATH", requested_store_path=requested_store
            )
        if request.bootstrap_explicit is not True:
            return self._deny(
                "EXPLICIT_BOOTSTRAP_INTENT_REQUIRED",
                requested_store_path=requested_store,
                requested_anchor_path=requested_anchor,
            )

        try:
            store_path = self._canonicalize(requested_store)
            anchor_path = self._canonicalize(requested_anchor)
        except (OSError, RuntimeError, ValueError) as exc:
            return self._deny(
                "INVALID_PATH",
                requested_store_path=requested_store,
                requested_anchor_path=requested_anchor,
                error_detail=str(exc),
            )

        preserved = {
            "requested_store_path": requested_store,
            "requested_anchor_path": requested_anchor,
            "canonical_store_path": str(store_path),
            "canonical_anchor_path": str(anchor_path),
        }
        if store_path.name.casefold() == "automation_state.db":
            return self._deny("AUTOMATION_STATE_DB_FORBIDDEN", **preserved)
        if store_path == anchor_path:
            return self._deny("STORE_AND_ANCHOR_PATHS_MUST_DIFFER", **preserved)
        if store_path.exists() and store_path.is_dir():
            return self._deny("EXISTING_DIRECTORY_TARGET", **preserved)
        if anchor_path.exists() and anchor_path.is_dir():
            return self._deny("EXISTING_DIRECTORY_ANCHOR", **preserved)
        if not store_path.parent.is_dir():
            return self._deny("STORE_PARENT_DIRECTORY_REQUIRED", **preserved)
        if not anchor_path.parent.is_dir():
            return self._deny("ANCHOR_PARENT_DIRECTORY_REQUIRED", **preserved)

        store_exists = store_path.exists()
        anchor_exists = anchor_path.exists()
        if store_exists != anchor_exists:
            reason = (
                "EXISTING_STORE_MISSING_ANCHOR"
                if store_exists
                else "ORPHAN_ANCHOR_WITHOUT_STORE"
            )
            return self._deny(reason, **preserved)

        if store_exists:
            try:
                store = DurableInvocationAuthorizationStore(
                    store_path, anchor_path=anchor_path
                )
                return self._success("ALREADY_INITIALIZED", store, **preserved)
            except DurableAuthorizationStoreError as exc:
                return self._deny(
                    "EXISTING_INVALID_STORE",
                    error_detail=str(exc),
                    **preserved,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                return self._deny(
                    "EXISTING_STORE_VALIDATION_FAILED",
                    error_detail=str(exc),
                    **preserved,
                )

        try:
            store = DurableInvocationAuthorizationStore.initialize(
                store_path, anchor_path=anchor_path
            )
            return self._success("INITIALIZED", store, **preserved)
        except DurableAuthorizationStoreError as exc:
            return self._deny(
                "STORE_INITIALIZATION_DENIED",
                error_detail=str(exc),
                **preserved,
            )
        except Exception as exc:
            return self._deny(
                f"INITIALIZER_EXCEPTION:{type(exc).__name__}",
                error_detail=str(exc),
                **preserved,
            )

    @staticmethod
    def _requested_value(value: str | Path | None) -> str | None:
        if not isinstance(value, (str, Path)):
            return None
        rendered = str(value)
        return rendered if rendered.strip() else None

    @staticmethod
    def _canonicalize(value: str) -> Path:
        if value.lstrip().startswith("~"):
            raise ValueError("home-relative paths are not accepted")
        return Path(value).resolve(strict=False)

    @staticmethod
    def _success(
        decision: str,
        store: DurableInvocationAuthorizationStore,
        **paths: str,
    ) -> ProductionInvocationAuthStoreBootstrapResult:
        try:
            instance_id = store.store_instance_id
            generation = store.store_generation
        except Exception as exc:
            return ProductionInvocationAuthStoreBootstrapResult(
                bootstrap_decision="DENY",
                bootstrap_reason="SCHEMA_VALIDATION_FAILURE",
                schema_id=AUTH_STORE_SCHEMA_ID,
                schema_version=AUTH_STORE_SCHEMA_VERSION,
                error_detail=str(exc),
                **paths,
            )
        return ProductionInvocationAuthStoreBootstrapResult(
            bootstrap_decision=decision,
            bootstrap_reason=(
                "STORE_CREATED_AND_SCHEMA_VALIDATED"
                if decision == "INITIALIZED"
                else "ESTABLISHED_STORE_VALIDATED_WITHOUT_REINITIALIZATION"
            ),
            schema_id=AUTH_STORE_SCHEMA_ID,
            schema_version=AUTH_STORE_SCHEMA_VERSION,
            store_instance_id=instance_id,
            store_generation=generation,
            **paths,
        )

    @staticmethod
    def _deny(
        reason: str,
        *,
        requested_store_path: str | None = None,
        requested_anchor_path: str | None = None,
        canonical_store_path: str | None = None,
        canonical_anchor_path: str | None = None,
        error_detail: str | None = None,
    ) -> ProductionInvocationAuthStoreBootstrapResult:
        return ProductionInvocationAuthStoreBootstrapResult(
            bootstrap_decision="DENY",
            bootstrap_reason=reason,
            requested_store_path=requested_store_path,
            requested_anchor_path=requested_anchor_path,
            canonical_store_path=canonical_store_path,
            canonical_anchor_path=canonical_anchor_path,
            error_detail=error_detail,
        )
