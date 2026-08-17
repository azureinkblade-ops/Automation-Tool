"""EA-4D.3E-B: LOCAL_WORKER_ADAPTER construction, protocol parsing, and the
worker-owned idempotency registry / reconciliation logic.

This module implements the real-runtime adapter boundary UP TO the process
spawn. It constructs the exact future argv/environment/cwd/request payload,
parses the frozen acknowledgement contract, and owns a worker-owned SQLite
idempotency registry whose reconciliation logic is fully exercised here. It
does NOT call ``subprocess.Popen`` / ``subprocess.run`` or create any process;
crossing the spawn boundary requires the separate EA-4D.3E REAL EXECUTION
authorization.

Implemented against the frozen EA-4D.3C contracts: ``RuntimeLaunchAdapter``,
``RuntimeLaunchResult``, ``RuntimeLookupResult`` and their frozen outcomes. No
frozen 3A-3D production artifact is modified.

Controlling invariant (frozen):
    LAUNCH_ATTEMPT_RECORDED != WORKER STARTED
No ``ExecutionStartResult`` persistence and no ``EXECUTING`` transition are
introduced here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt,
    WorkerRuntimeBinding,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeAdapterConflictError,
    RuntimeAdapterError,
    RuntimeAdapterLookupError,
    RuntimeAdapterProtocolError,
    RuntimeAdapterValidationError,
    RuntimeLaunchAdapter,
    RuntimeLaunchOutcome,
    RuntimeLaunchResult,
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)
from tools.hermes_core.local_worker_runtime_config import (
    LocalWorkerConfigError,
    LocalWorkerLaunchConfig,
    TrustedLocalWorkerConfigRegistry,
)


# --------------------------------------------------------------------------- #
# No-spawn boundary
# --------------------------------------------------------------------------- #
class RuntimeAdapterExecutionNotAuthorizedError(RuntimeAdapterError):
    """Raised at the spawn boundary when 3E-C real execution is not authorized.

    The adapter validates and constructs the full launch command (dry run) but
    must not invoke a process. This error makes the no-spawn boundary explicit
    and testable; it is NEVER silently swallowed into STARTED/FAILED/UNKNOWN.
    """


# --------------------------------------------------------------------------- #
# Dry-run command construction (no process created)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LaunchCommand:
    """Fully-resolved, ready-to-exec process boundary (constructed, not run)."""

    executable: str
    argv: tuple
    cwd: Optional[str]
    environment: tuple          # allowlisted (name, value) pairs
    request_payload_json: str
    idempotency_key: str
    shell: bool = False         # always False; never a shell string

    def assert_no_shell(self) -> None:
        if self.shell is not False:
            raise RuntimeAdapterProtocolError("shell execution is prohibited")
        if isinstance(self.argv, str):
            raise RuntimeAdapterProtocolError(
                "argv must be a list/tuple, never a shell string")


# Fields the task/request may populate as DATA only (never command structure).
_PERMITTED_REQUEST_FIELDS = (
    "launch_attempt_id",
    "reservation_id",
    "route_id",
    "worker_id",
    "worker_version",
    "operation",
    "input_hash",
    "idempotency_key",
)


def build_launch_command(
    *,
    launch_attempt: ExecutionLaunchAttempt,
    binding: WorkerRuntimeBinding,
    config: LocalWorkerLaunchConfig,
) -> LaunchCommand:
    """Construct the exact future launch command (dry run). No process created.

    The argv structure comes entirely from the trusted config; the task
    contributes only immutable launch-identity DATA values into the canonical
    request payload, never into executable/argv/cwd/environment structure.
    """
    if not isinstance(config, LocalWorkerLaunchConfig):
        raise RuntimeAdapterValidationError(
            "config is not a trusted LocalWorkerLaunchConfig")

    # Canonical request payload (frozen hermes-local-worker-v1 request contract).
    request = {
        "protocol_version": config.acknowledgement_mode,
        "launch_attempt_id": launch_attempt.launch_attempt_id,
        "reservation_id": launch_attempt.reservation_id,
        "route_id": launch_attempt.route_id,
        "worker_id": binding.worker_id,
        "worker_version": binding.worker_version,
        "operation": launch_attempt.operation,
        "input_hash": launch_attempt.input_hash,
        "idempotency_key": launch_attempt.idempotency_key,
    }
    request_json = json.dumps(request, sort_keys=True, separators=(",", ":"))

    # Trusted argv: executable + trusted template. Task input never alters it.
    argv = (config.executable,) + tuple(config.argv_template)
    # Allowlisted environment (names only; values taken from current process env
    # or empty string when absent -- no task-controlled env injection).
    environment = tuple(
        (name, os.environ.get(name, "")) for name in config.environment_allowlist
    )
    return LaunchCommand(
        executable=config.executable,
        argv=argv,
        cwd=config.cwd,
        environment=environment,
        request_payload_json=request_json,
        idempotency_key=launch_attempt.idempotency_key,
        shell=False,
    )


# --------------------------------------------------------------------------- #
# Acknowledgement protocol parsing (hermes-local-worker-v1)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParsedAcknowledgement:
    protocol_version: str
    idempotency_key: str
    launch_attempt_id: str
    runtime_run_id: str
    state: str


class UnusableAcknowledgement(RuntimeAdapterError):
    """Acknowledgement text could not be validated after possible delivery.

    Per the frozen packet, an unusable acknowledgement must NOT become FAILED
    merely because it is unusable; it normalizes to UNKNOWN (post-delivery
    ambiguity). This class lets the 3E-C adapter distinguish definitive
    pre-delivery failure from post-delivery ambiguity.
    """


def parse_acknowledgement(text: str) -> ParsedAcknowledgement:
    """Parse + validate a hermes-local-worker-v1 STARTED acknowledgement.

    Raises ``UnusableAcknowledgement`` (-> normalize to UNKNOWN) when any
    required field is missing, the protocol version is wrong, the
    runtime_run_id is empty, or the state is not a recognizable value.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise UnusableAcknowledgement(f"acknowledgement is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise UnusableAcknowledgement("acknowledgement is not a JSON object")
    if data.get("protocol_version") != "hermes-local-worker-v1":
        raise UnusableAcknowledgement("unsupported acknowledgement protocol version")
    idem = data.get("idempotency_key")
    if not idem:
        raise UnusableAcknowledgement("acknowledgement missing idempotency_key")
    attempt_id = data.get("launch_attempt_id")
    if not attempt_id:
        raise UnusableAcknowledgement("acknowledgement missing launch_attempt_id")
    run_id = data.get("runtime_run_id")
    if not run_id:
        raise UnusableAcknowledgement("acknowledgement missing non-empty runtime_run_id")
    state = data.get("state")
    if state != "STARTED":
        raise UnusableAcknowledgement(f"acknowledgement state is not STARTED: {state!r}")
    return ParsedAcknowledgement(
        protocol_version=data["protocol_version"],
        idempotency_key=idem,
        launch_attempt_id=attempt_id,
        runtime_run_id=run_id,
        state=state,
    )


# --------------------------------------------------------------------------- #
# Worker-owned idempotency registry (file-backed SQLite, outside child memory)
# --------------------------------------------------------------------------- #
REGISTRY_SCHEMA_VERSION = 1
_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS local_worker_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    launch_attempt_id TEXT NOT NULL,
    runtime_run_id TEXT NOT NULL,
    state TEXT NOT NULL,
    recorded_at REAL NOT NULL
);
"""


class LocalWorkerIdempotencyRegistry:
    """Worker-owned durable idempotency registry (authoritative reconciliation).

    Idempotency state lives in a file-backed SQLite database OUTSIDE transient
    child process memory, so authoritative ``lookup()`` survives coordinator
    reconstruction (Crash-D / Crash-F). ``lookup()`` is strictly read-only and
    creates no logical work.

    Authoritative absence (NOT_FOUND_AUTHORITATIVE) requires ALL of:
        - the registry file opens and validates,
        - the expected schema is present,
        - the lookup executes successfully,
        - no matching row exists.
    Any failure to establish those predicates yields UNKNOWN (or fail-closed),
    never authoritative absence.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None: the registry controls its own transactions.
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_validated(self, conn: sqlite3.Connection) -> None:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "local_worker_idempotency" not in tables:
            raise RuntimeAdapterLookupError("idempotency registry schema absent")

    def record_acceptance(
        self,
        *,
        idempotency_key: str,
        launch_attempt_id: str,
        runtime_run_id: str,
    ) -> None:
        """Atomically register acceptance. Same key + conflicting lineage -> fail
        closed (no second run, no silent overwrite)."""
        conn = self._connect()
        try:
            self._ensure_validated(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT launch_attempt_id, runtime_run_id, state "
                "FROM local_worker_idempotency WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                prev_attempt, prev_run, _prev_state = existing
                if prev_attempt != launch_attempt_id or prev_run != runtime_run_id:
                    conn.execute("ROLLBACK")
                    raise RuntimeAdapterConflictError(
                        "idempotency_key reused with conflicting lineage; "
                        "fail closed")
                # Idempotent re-acceptance of the same logical identity.
                return
            conn.execute(
                "INSERT INTO local_worker_idempotency "
                "(idempotency_key, launch_attempt_id, runtime_run_id, state, recorded_at) "
                "VALUES (?, ?, ?, 'STARTED', ?)",
                (idempotency_key, launch_attempt_id, runtime_run_id, time.time()),
            )
            conn.execute("COMMIT")
        finally:
            conn.close()

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        """Authoritative reconciliation by canonical idempotency key.

        Read-only; creates no logical work. Unreadable/corrupt/wrong-schema
        registries yield UNKNOWN, never NOT_FOUND_AUTHORITATIVE.
        """
        conn = None
        try:
            conn = self._connect()
            self._ensure_validated(conn)
            row = conn.execute(
                "SELECT launch_attempt_id, runtime_run_id, state "
                "FROM local_worker_idempotency WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                return RuntimeLookupResult(
                    outcome=RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)
            _attempt, run_id, state = row
            if state == "STARTED":
                return RuntimeLookupResult(
                    outcome=RuntimeLookupOutcome.FOUND_STARTED, runtime_run_id=run_id)
            if state == "FAILED":
                return RuntimeLookupResult(
                    outcome=RuntimeLookupOutcome.FOUND_FAILED)
            return RuntimeLookupResult(outcome=RuntimeLookupOutcome.UNKNOWN)
        except RuntimeAdapterLookupError:
            return RuntimeLookupResult(outcome=RuntimeLookupOutcome.UNKNOWN)
        except (sqlite3.Error, OSError):
            # Unreadable/corrupt/wrong-schema registry: NOT authoritative.
            return RuntimeLookupResult(outcome=RuntimeLookupOutcome.UNKNOWN)
        finally:
            if conn is not None:
                conn.close()

    def initialize(self) -> None:
        """Create the registry schema (idempotency owner side). No spawn."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_REGISTRY_DDL)
            conn.execute("COMMIT")
        finally:
            conn.close()


# --------------------------------------------------------------------------- #
# Adapter (boundary only; spawn deferred to 3E-C)
# --------------------------------------------------------------------------- #
class LocalWorkerRuntimeAdapter:
    """Real LOCAL_WORKER_ADAPTER implementation, up to the spawn boundary.

    Implements the frozen ``RuntimeLaunchAdapter`` contract. ``launch()``
    performs all pre-delivery validation and dry-run command construction, then
    raises ``RuntimeAdapterExecutionNotAuthorizedError`` because 3E-C real
    execution is not authorized in this slice. ``lookup()`` is fully
    implemented against the worker-owned registry.
    """

    def __init__(
        self,
        *,
        config_registry: TrustedLocalWorkerConfigRegistry,
        idempotency_registry: LocalWorkerIdempotencyRegistry,
    ) -> None:
        self._config_registry = config_registry
        self._idempotency_registry = idempotency_registry

    # -- pre-delivery validation (definitive -> FAILED, not UNKNOWN) ---------- #
    def _validate_pre_delivery(
        self,
        *,
        binding: WorkerRuntimeBinding,
        launch_attempt: ExecutionLaunchAttempt,
        idempotency_key: str,
    ) -> LocalWorkerLaunchConfig:
        if binding.adapter_kind.name != "LOCAL_WORKER_ADAPTER":
            raise RuntimeAdapterValidationError(
                f"adapter kind {binding.adapter_kind!r} not resolvable by "
                f"LocalWorkerRuntimeAdapter")
        if not binding.enabled:
            raise RuntimeAdapterValidationError("binding is disabled")
        if not binding.supports_idempotency:
            raise RuntimeAdapterValidationError("binding does not support idempotency")
        if launch_attempt.operation not in binding.allowed_operations:
            raise RuntimeAdapterValidationError(
                f"operation {launch_attempt.operation!r} not allowed by binding")
        if binding.runtime_binding_id != launch_attempt.runtime_binding_id:
            raise RuntimeAdapterValidationError(
                "binding identity does not match the admitted LaunchAttempt snapshot")
        if binding.runtime_binding_version != launch_attempt.runtime_binding_version:
            raise RuntimeAdapterValidationError(
                "binding version does not match the admitted LaunchAttempt snapshot")
        if binding.artifact_hash != launch_attempt.runtime_binding_hash:
            raise RuntimeAdapterValidationError(
                "binding hash does not match the admitted LaunchAttempt snapshot")
        if launch_attempt.worker_id != binding.worker_id:
            raise RuntimeAdapterValidationError("worker_id mismatch")
        if launch_attempt.worker_version != binding.worker_version:
            raise RuntimeAdapterValidationError("worker_version mismatch")
        if launch_attempt.worker_class != binding.worker_class:
            raise RuntimeAdapterValidationError("worker_class mismatch")
        if idempotency_key != launch_attempt.idempotency_key:
            raise RuntimeAdapterValidationError(
                "idempotency_key does not equal the admitted LaunchAttempt key")
        try:
            config = self._config_registry.resolve(binding)
        except LocalWorkerConfigError as exc:
            raise RuntimeAdapterValidationError(f"config resolution failed: {exc}")
        if not config._is_absolute(config.executable):
            raise RuntimeAdapterValidationError("executable is not an absolute path")
        return config

    # -- RuntimeLaunchAdapter contract ------------------------------------- #
    def launch(
        self,
        *,
        binding: WorkerRuntimeBinding,
        launch_attempt: ExecutionLaunchAttempt,
        idempotency_key: str,
    ) -> RuntimeLaunchResult:
        # Full pre-delivery validation (definitive failure -> FAILED cause).
        config = self._validate_pre_delivery(
            binding=binding, launch_attempt=launch_attempt, idempotency_key=idempotency_key)
        # Dry-run command construction (no process created).
        command = build_launch_command(
            launch_attempt=launch_attempt, binding=binding, config=config)
        command.assert_no_shell()
        # Spawn boundary: 3E-C real execution is NOT authorized in this slice.
        raise RuntimeAdapterExecutionNotAuthorizedError(
            "EA-4D.3E-C real execution not authorized; spawn boundary reached "
            "after full dry-run validation")

    def lookup(self, idempotency_key: str) -> RuntimeLookupResult:
        return self._idempotency_registry.lookup(idempotency_key)
