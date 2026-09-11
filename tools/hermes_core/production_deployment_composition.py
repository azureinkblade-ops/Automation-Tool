"""Explicit non-live deployment composition for EA-4E.64A.

Provisioning stores and bindings is not authorization, activation, or execution.
Nothing in this module runs at import or application startup.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable
from uuid import uuid4

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.kilo_adapter import (
    PINNED_KILO_PATH,
    PINNED_KILO_SHA256,
    PINNED_KILO_VERSION,
)
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.kilo_successor_binding import (
    KILO_EXECUTABLE_SUCCESSOR_BINDING_ID,
)
from tools.hermes_core.production_activation_authorization_store import (
    ProductionActivationAuthStoreBootstrapper,
    ProductionActivationAuthorizationStore,
)
from tools.hermes_core.production_app_binding import (
    ProductionAppBindingProvisioner,
    ProductionAppBindingRequest,
)
from tools.hermes_core.production_app_config import (
    DEFAULT_LOCAL_OPERATOR_ID,
    ProductionAppRuntimeConfig,
)
from tools.hermes_core.production_credential_preflight import (
    ProductionCredentialReadinessPreflight,
)
from tools.hermes_core.production_executor_binding import (
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    parse_iso_timestamp,
)
from tools.hermes_core.production_invocation_auth_store_bootstrap import (
    ProductionInvocationAuthStoreBootstrapRequest,
    ProductionInvocationAuthStoreBootstrapper,
)
from tools.hermes_core.production_issuance import (
    ALLOWED_DELEGATION_CLASS,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.production_wiring import (
    DEFAULT_PRODUCTION_AUTH_ANCHOR_PATH,
    DEFAULT_PRODUCTION_AUTH_STORE_PATH,
    ProductionWiringConfig,
)


DEPLOYMENT_BINDING_SCHEMA_VERSION = "1"
KILO_RECEIVER_ID = "kilo-cli-agent"
_RUNTIME_ROOT = Path(
    os.environ.get("LOCALAPPDATA", r"C:\Users\David\AppData\Local")
) / "Hermes" / "runtime" / "ea4e" / "production"
DEFAULT_ACTIVATION_STORE_PATH = _RUNTIME_ROOT / "activation-authorization.sqlite3"
DEFAULT_ACTIVATION_ANCHOR_PATH = _RUNTIME_ROOT / "activation-authorization.anchor.json"
DEFAULT_BINDING_STATE_PATH = _RUNTIME_ROOT / "executor-binding.sqlite3"


class ProductionDeploymentCompositionError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DeploymentClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def now_plus_seconds(self, seconds: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


@dataclass(frozen=True)
class ProductionDeploymentPaths:
    invocation_store_path: Path = DEFAULT_PRODUCTION_AUTH_STORE_PATH
    invocation_anchor_path: Path = DEFAULT_PRODUCTION_AUTH_ANCHOR_PATH
    activation_store_path: Path = DEFAULT_ACTIVATION_STORE_PATH
    activation_anchor_path: Path = DEFAULT_ACTIVATION_ANCHOR_PATH
    binding_state_path: Path = DEFAULT_BINDING_STATE_PATH


class ProductionDeploymentBindingStore:
    """Integrity-check one process-reconstructable binding descriptor."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ProductionDeploymentCompositionError("BINDING_STATE_STORE_MISSING")
        self._verify()

    @classmethod
    def initialize(cls, path: str | Path) -> "ProductionDeploymentBindingStore":
        target = Path(path)
        if target.exists():
            raise ProductionDeploymentCompositionError("BINDING_STATE_STORE_ALREADY_EXISTS")
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(target))) as connection, connection:
            connection.execute(
                "CREATE TABLE binding_store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO binding_store_metadata VALUES ('schema_version', ?)",
                (DEPLOYMENT_BINDING_SCHEMA_VERSION,),
            )
            connection.execute(
                """CREATE TABLE production_executor_binding_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL
                )"""
            )
        return cls(target)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _verify(self) -> None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT value FROM binding_store_metadata WHERE key='schema_version'"
                ).fetchone()
                if row is None or row["value"] != DEPLOYMENT_BINDING_SCHEMA_VERSION:
                    raise ProductionDeploymentCompositionError(
                        "BINDING_STATE_STORE_SCHEMA_MISMATCH"
                    )
        except sqlite3.Error as exc:
            raise ProductionDeploymentCompositionError(
                "BINDING_STATE_STORE_INVALID"
            ) from exc

    def load(self) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json, payload_hash FROM production_executor_binding_state WHERE singleton=1"
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProductionDeploymentCompositionError(
                "BINDING_STATE_PAYLOAD_INVALID"
            ) from exc
        if row["payload_hash"] != sha256_payload(payload):
            raise ProductionDeploymentCompositionError("BINDING_STATE_HASH_MISMATCH")
        return payload

    def save_once(self, payload: dict[str, Any]) -> None:
        rendered = canonical_json(payload)
        digest = sha256_payload(payload)
        with closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT payload_json, payload_hash FROM production_executor_binding_state WHERE singleton=1"
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != rendered or existing["payload_hash"] != digest:
                    raise ProductionDeploymentCompositionError(
                        "BINDING_STATE_ALREADY_PROVISIONED"
                    )
                return
            connection.execute(
                "INSERT INTO production_executor_binding_state VALUES (1, ?, ?)",
                (rendered, digest),
            )
            connection.commit()

    def replace_successor(
        self, *, expected_binding_id: str, payload: dict[str, Any]
    ) -> None:
        """Atomically replace one exact predecessor with its qualified successor."""
        rendered = canonical_json(payload)
        digest = sha256_payload(payload)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT payload_json, payload_hash FROM production_executor_binding_state WHERE singleton=1"
            ).fetchone()
            if row is None:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_PREDECESSOR_MISSING"
                )
            try:
                existing = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_PAYLOAD_INVALID"
                ) from exc
            if row["payload_hash"] != sha256_payload(existing):
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_HASH_MISMATCH"
                )
            if existing.get("binding_id") != expected_binding_id:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_PREDECESSOR_MISMATCH"
                )
            connection.execute(
                "UPDATE production_executor_binding_state SET payload_json=?, payload_hash=? WHERE singleton=1",
                (rendered, digest),
            )

    def replace_expired(
        self,
        *,
        expected_binding_id: str,
        expected_expires_at: str,
        now: str,
        payload: dict[str, Any],
    ) -> None:
        """Atomically replace one exact expired binding descriptor."""
        rendered = canonical_json(payload)
        digest = sha256_payload(payload)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT payload_json, payload_hash FROM production_executor_binding_state WHERE singleton=1"
            ).fetchone()
            if row is None:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_PREDECESSOR_MISSING"
                )
            try:
                existing = json.loads(row["payload_json"])
                existing_expires_at = existing["enablement"]["expires_at"]
            except (TypeError, json.JSONDecodeError, KeyError) as exc:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_PAYLOAD_INVALID"
                ) from exc
            if row["payload_hash"] != sha256_payload(existing):
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_HASH_MISMATCH"
                )
            if existing.get("binding_id") != expected_binding_id:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_PREDECESSOR_MISMATCH"
                )
            if existing_expires_at != expected_expires_at:
                raise ProductionDeploymentCompositionError(
                    "BINDING_STATE_EXPIRY_MISMATCH"
                )
            if parse_iso_timestamp(existing_expires_at) > parse_iso_timestamp(now):
                raise ProductionDeploymentCompositionError(
                    "PERSISTED_KILO_BINDING_NOT_EXPIRED"
                )
            connection.execute(
                "UPDATE production_executor_binding_state SET payload_json=?, payload_hash=? WHERE singleton=1",
                (rendered, digest),
            )


@dataclass
class ProductionDeploymentCompositionOwner:
    paths: ProductionDeploymentPaths
    governing_commit: str
    clock: Any
    activation_store: ProductionActivationAuthorizationStore
    binding_store: ProductionDeploymentBindingStore
    registry: ExecutorRegistry
    binding_controller: ProductionExecutorBindingController
    credential_preflight: Any
    binding_handle: Any
    configured_components: Any = None

    @classmethod
    def provision(
        cls,
        *,
        paths: ProductionDeploymentPaths,
        governing_commit: str,
        provision_explicit: bool,
        clock: Any | None = None,
        credential_preflight: Any | None = None,
        executor_factory: Callable[[], Any] | None = None,
        successor_roll_explicit: bool = False,
        expired_binding_renewal_explicit: bool = False,
    ) -> "ProductionDeploymentCompositionOwner":
        if provision_explicit is not True:
            raise ProductionDeploymentCompositionError("EXPLICIT_PROVISIONING_REQUIRED")
        if not isinstance(governing_commit, str) or not governing_commit.strip():
            raise ProductionDeploymentCompositionError("GOVERNING_COMMIT_MISSING")
        for path in (
            paths.invocation_store_path,
            paths.invocation_anchor_path,
            paths.activation_store_path,
            paths.activation_anchor_path,
            paths.binding_state_path,
        ):
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        invocation_result = ProductionInvocationAuthStoreBootstrapper().bootstrap(
            ProductionInvocationAuthStoreBootstrapRequest(
                store_path=paths.invocation_store_path,
                anchor_path=paths.invocation_anchor_path,
                bootstrap_explicit=True,
            )
        )
        if invocation_result.bootstrap_decision not in {"INITIALIZED", "ALREADY_INITIALIZED"}:
            raise ProductionDeploymentCompositionError(
                f"INVOCATION_STORE_{invocation_result.bootstrap_reason}"
            )

        activation_exists = Path(paths.activation_store_path).exists()
        anchor_exists = Path(paths.activation_anchor_path).exists()
        if activation_exists != anchor_exists:
            raise ProductionDeploymentCompositionError("ACTIVATION_STORE_PAIR_INCOMPLETE")
        if activation_exists:
            activation_store = ProductionActivationAuthorizationStore(
                paths.activation_store_path, paths.activation_anchor_path
            )
        else:
            activation_store = ProductionActivationAuthStoreBootstrapper().bootstrap(
                paths.activation_store_path,
                bootstrap_explicit=True,
                anchor_path=paths.activation_anchor_path,
            )

        binding_store = (
            ProductionDeploymentBindingStore(paths.binding_state_path)
            if Path(paths.binding_state_path).exists()
            else ProductionDeploymentBindingStore.initialize(paths.binding_state_path)
        )
        active_clock = clock or DeploymentClock()
        binding_clock = active_clock
        registry = ExecutorRegistry()
        factory = executor_factory or (
            lambda: RealKiloProductionExecutor(kilo_executable=PINNED_KILO_PATH)
        )
        executor = factory()
        if getattr(executor, "executor_id", None) != "RealKiloProductionExecutor":
            raise ProductionDeploymentCompositionError("KILO_EXECUTOR_IDENTITY_MISMATCH")
        registry.register(KILO_RECEIVER_ID, executor)
        controller = ProductionExecutorBindingController(
            policy=ProductionExecutorBindingPolicy(clock=binding_clock),
            clock=binding_clock,
        )
        preflight = credential_preflight or ProductionCredentialReadinessPreflight()
        existing = binding_store.load()
        spec = QUALIFIED_RECEIVERS[KILO_RECEIVER_ID]
        impl = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[KILO_RECEIVER_ID]
        predecessor_binding_id = None
        expired_predecessor_expires_at = None
        if existing is not None:
            prior_enablement = existing.get("enablement", {})
            successor_matches = (
                existing.get("executable_binding_id")
                == KILO_EXECUTABLE_SUCCESSOR_BINDING_ID
                and prior_enablement.get("receiver_id") == KILO_RECEIVER_ID
                and prior_enablement.get("transport_contract_id")
                == spec["transport_contract_id"]
                and prior_enablement.get("model_binding_id")
                == spec["model_binding_id"]
                and prior_enablement.get("executor_identity")
                == impl["executor_identity"]
            )
            if not successor_matches:
                if successor_roll_explicit is not True:
                    raise ProductionDeploymentCompositionError(
                        "PERSISTED_KILO_BINDING_IDENTITY_MISMATCH"
                    )
                predecessor_binding_id = existing.get("binding_id")
                if not isinstance(predecessor_binding_id, str):
                    raise ProductionDeploymentCompositionError(
                        "BINDING_STATE_PREDECESSOR_MISSING"
                    )
                existing = None
            else:
                try:
                    persisted_expires_at = str(prior_enablement["expires_at"])
                    binding_expired = parse_iso_timestamp(
                        persisted_expires_at
                    ) <= parse_iso_timestamp(active_clock.now_iso())
                except (KeyError, TypeError, ValueError) as exc:
                    raise ProductionDeploymentCompositionError(
                        "BINDING_STATE_PAYLOAD_INVALID"
                    ) from exc
                if binding_expired:
                    if expired_binding_renewal_explicit is not True:
                        raise ProductionDeploymentCompositionError(
                            "PERSISTED_KILO_BINDING_EXPIRED"
                        )
                    predecessor_binding_id = existing.get("binding_id")
                    if not isinstance(predecessor_binding_id, str):
                        raise ProductionDeploymentCompositionError(
                            "BINDING_STATE_PREDECESSOR_MISSING"
                        )
                    expired_predecessor_expires_at = persisted_expires_at
                    existing = None
                elif expired_binding_renewal_explicit is True:
                    raise ProductionDeploymentCompositionError(
                        "PERSISTED_KILO_BINDING_NOT_EXPIRED"
                    )
        if existing is None:
            issued_at = active_clock.now_iso()
            expires_at = active_clock.now_plus_seconds(3600)
            enablement_id = f"deployment-enable-{uuid4()}"
            request_nonce = f"deployment-binding-{uuid4()}"
            result = ProductionAppBindingProvisioner(
                controller, registry, preflight=preflight
            ).bind(
                ProductionAppBindingRequest(
                    enablement_id=enablement_id,
                    receiver_id=KILO_RECEIVER_ID,
                    executor_id=impl["executor_identity"],
                    executor_factory=impl["executor_factory"],
                    transport_contract_id=spec["transport_contract_id"],
                    model_binding_id=spec["model_binding_id"],
                    runtime_scope="production",
                    issued_at=issued_at,
                    expires_at=expires_at,
                    requested_ttl_seconds=3600,
                    request_nonce=request_nonce,
                    delegation_class=ALLOWED_DELEGATION_CLASS,
                )
            )
            if result.binding_decision != "BOUND" or result.handle is None:
                raise ProductionDeploymentCompositionError(
                    f"KILO_BINDING_{result.binding_reason}"
                )
            handle = result.handle
            request_payload = {
                "enablement_id": enablement_id,
                "receiver_id": KILO_RECEIVER_ID,
                "transport_contract_id": spec["transport_contract_id"],
                "model_binding_id": spec["model_binding_id"],
                "executor_identity": impl["executor_identity"],
                "executor_factory": impl["executor_factory"],
                "runtime_scope": "production",
                "issued_at": issued_at,
                "expires_at": expires_at,
                "delegation_class": ALLOWED_DELEGATION_CLASS,
                "requested_ttl_seconds": "3600",
                "max_bound_executors": 1,
                "enabled": True,
                "request_nonce": request_nonce,
            }
            original = ProductionExecutorBindingEnablement(**request_payload)
            payload = {
                "binding_id": handle.binding_id,
                "bound_at": handle.bound_at,
                "executable_binding_id": KILO_EXECUTABLE_SUCCESSOR_BINDING_ID,
                "binary_path": PINNED_KILO_PATH,
                "binary_sha256": PINNED_KILO_SHA256,
                "binary_version": PINNED_KILO_VERSION,
                "enablement": original.to_canonical_dict(),
            }
            if predecessor_binding_id is None:
                binding_store.save_once(payload)
            elif expired_predecessor_expires_at is not None:
                binding_store.replace_expired(
                    expected_binding_id=predecessor_binding_id,
                    expected_expires_at=expired_predecessor_expires_at,
                    now=active_clock.now_iso(),
                    payload=payload,
                )
            else:
                binding_store.replace_successor(
                    expected_binding_id=predecessor_binding_id,
                    payload=payload,
                )
        else:
            enablement = ProductionExecutorBindingEnablement(**existing["enablement"])
            handle = controller.restore(
                enablement,
                binding_id=existing["binding_id"],
                bound_at=existing["bound_at"],
                registry=registry,
                executor_factory=factory,
            )

        return cls(
            paths=paths,
            governing_commit=governing_commit,
            clock=active_clock,
            activation_store=activation_store,
            binding_store=binding_store,
            registry=registry,
            binding_controller=controller,
            credential_preflight=preflight,
            binding_handle=handle,
        )

    def runtime_config(self) -> ProductionAppRuntimeConfig:
        return ProductionAppRuntimeConfig(
            wiring=ProductionWiringConfig(
                master_enable="DISABLED",
                production_activation_default="DISABLED",
                default_receiver="NONE",
                receiver_id=None,
                auth_store_path=self.paths.invocation_store_path,
                auth_anchor_path=self.paths.invocation_anchor_path,
            ),
            clock=self.clock,
            callsite_feature_gate="ENABLED",
            executor_registry=self.registry,
            register_real_executors=False,
            credential_preflight=self.credential_preflight,
            activation_authorization_store=self.activation_store,
            activation_authorization_governing_commit=self.governing_commit,
            activation_authorization_readiness_status="PASS",
            activation_authorization_operator_id=DEFAULT_LOCAL_OPERATOR_ID,
            binding_controller=self.binding_controller,
        )

    def configure(self, configure_action: Callable[[ProductionAppRuntimeConfig], Any]) -> Any:
        self.configured_components = configure_action(self.runtime_config())
        return self.configured_components

    def status(self) -> dict[str, Any]:
        store_id, store_epoch = self.activation_store.lineage()
        return {
            "store_id": store_id,
            "store_epoch": store_epoch,
            "binding_id": self.binding_handle.binding_id,
            "binding_receiver_id": self.binding_handle.receiver_id,
            "binding_expires_at": self.binding_handle.expires_at,
            "composition_configured": self.configured_components is not None,
            "authorization_issued": 0,
            "production_activated": False,
            "receiver_executed": False,
            "model_invoked": False,
        }
