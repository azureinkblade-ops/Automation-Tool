"""Prepare and execute the one authorized EA-4D.4F-R12E Codex proof.

Preparation is non-live. Execution is one-shot and refuses to run after an
evidence record exists. Runtime artifacts live under ignored ``.hermes/runtime``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from tools.hermes_core.codex_adapter import (
    PINNED_ADAPTER_VERSION,
    PINNED_CODEX_PATH,
    PINNED_CODEX_SHA256,
    PINNED_CODEX_VERSION,
    CodexReceiverAdapter,
    CodexReplayConflictError,
    default_trusted_config,
    qualify_codex_result_schema_file,
)
from tools.hermes_core.codex_live_process import CodexLiveProcess
from tools.hermes_core.codex_result_schema import (
    STRUCTURAL_POLICY_ID,
    CodexResultSchemaLineage,
    build_instance_bound_result_schema,
    qualify_instance_bound_result_schema_file,
)
from tools.hermes_core.delegated_task import (
    build_delegated_capability_lease,
    build_delegated_task_envelope,
)
from tools.hermes_core.delegation_delivery import build_delegation_receipt
from tools.hermes_core.delegation_result import build_delegation_result
from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
)
from tools.hermes_core.execution_state_projector import ExecutionStateProjector
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService,
    RuntimeStartLookup,
)
from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionOrchestrator,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)
from tools.hermes_core.sqlite_delegation_result_store import (
    SQLiteDelegationResultStore,
)
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore
from tools.hermes_core.hashing import canonical_json, sha256_payload
from tests.hermes_core.test_execution_launch_admission import (
    _build_canonical_chain,
    _launcher_actor,
    _make_binding_registry,
    _make_reservation,
    _persist_canonical_chain,
    _persist_reservation,
    admit_execution_launch_attempt,
)


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".hermes" / "runtime" / "ea4d4f" / "r12e"
AUTHORITY_DB = RUNTIME / "authority.sqlite3"
START_DB = RUNTIME / "start.sqlite3"
TRANSPORT_DB = RUNTIME / "codex-transport.sqlite3"
SCHEMA_FILE = RUNTIME / "hermes-result-v1.schema.json"
SPOOL = RUNTIME / "spool"
STDIN_FILE = RUNTIME / "canonical-stdin.json"
PREFLIGHT_FILE = RUNTIME / "preflight.json"
PREFLIGHT_HASH_FILE = RUNTIME / "preflight.sha256"
EVIDENCE_FILE = RUNTIME / "live-proof-evidence.json"
FROZEN_R11_SHA256 = "79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70"
R11_FILE = ROOT / ".hermes" / "handoffs" / "ea4d4f" / "EA-4D.4F-R11-AGENT-TO-AGENT-GOVERNED-DELEGATION-DESIGN.md"
RESULT_SCHEMA_ID = "hermes.delegation_result/v1"
ORIGINATOR = "hermes-primary-agent"
RECEIVER = "codex-cli-agent"
DEADLINE = "2026-08-30T23:59:59Z"
SOURCE_FILES = (
    ROOT / "tools" / "hermes_core" / "codex_adapter.py",
    ROOT / "tools" / "hermes_core" / "codex_result_schema.py",
    ROOT / "tools" / "hermes_core" / "codex_live_process.py",
    ROOT / "tools" / "hermes_core" / "delegation_result.py",
    ROOT / "tools" / "hermes_core" / "sqlite_delegation_result_store.py",
    ROOT / "tests" / "hermes_core" / "run_r12e_live_proof.py",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    dotgit = ROOT / ".git"
    if dotgit.is_file():
        line = dotgit.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir: "):
            raise RuntimeError("unsupported worktree .git file")
        gitdir = Path(line.removeprefix("gitdir: "))
    else:
        gitdir = dotgit
    value = (gitdir / "HEAD").read_text(encoding="ascii").strip()
    if value.startswith("ref: "):
        ref = value.removeprefix("ref: ")
        ref_path = gitdir / ref
        if not ref_path.exists() and (gitdir / "commondir").exists():
            common = (gitdir / (gitdir / "commondir").read_text(encoding="ascii").strip()).resolve()
            ref_path = common / ref
        value = ref_path.read_text(encoding="ascii").strip()
    if len(value) != 40:
        raise RuntimeError("could not resolve exact repository HEAD")
    return value


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _source_hashes() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): _file_hash(path)
        for path in SOURCE_FILES
    }


def _trusted_config(task_input_hash: str, receipt_hash: str):
    base = default_trusted_config()
    schema = qualify_codex_result_schema_file(SCHEMA_FILE)
    lineage = CodexResultSchemaLineage(task_input_hash, receipt_hash)
    instance = qualify_instance_bound_result_schema_file(
        SCHEMA_FILE,
        lineage=lineage,
        binary_sha256=PINNED_CODEX_SHA256,
        binary_version=PINNED_CODEX_VERSION,
        cli_contract_id=base.expected_cli_contract_id,
        expected_structural_policy_id=STRUCTURAL_POLICY_ID,
    )
    return replace(
        base,
        output_schema_file=str(SCHEMA_FILE),
        spool_directory=str(SPOOL),
        registry_path=str(TRANSPORT_DB),
        timeout_seconds=120,
        expected_schema_sha256=schema.schema_sha256,
        require_instance_schema_qualification=True,
        expected_structural_policy_id=STRUCTURAL_POLICY_ID,
        expected_instance_schema_qualification_id=instance.qualification_id,
        expected_task_input_hash=task_input_hash,
        expected_receiver_receipt_hash=receipt_hash,
    )


def _schema(task_input_hash: str, receipt_hash: str) -> dict:
    return build_instance_bound_result_schema(
        CodexResultSchemaLineage(task_input_hash, receipt_hash)
    )


def _stdin(envelope, lease, receipt) -> dict:
    return {
        "artifact_type": "hermes.r12e_qualification_request",
        "artifact_version": "1",
        "delegated_task": envelope.to_canonical_dict(),
        "capability_lease": lease.to_canonical_dict(),
        "receiver_acceptance": receipt.to_canonical_dict(),
        "instruction": (
            "Return only the schema-constrained JSON result. Perform no tool, "
            "filesystem, network, browser, image, shell, plugin, app, hook, or "
            "sub-agent action. Copy the exact constants required by the schema."
        ),
    }


def _resume_preflight() -> dict:
    """Finish a non-live preparation interrupted after durable PREPARED state."""
    required = (AUTHORITY_DB, START_DB, TRANSPORT_DB, SCHEMA_FILE, STDIN_FILE)
    if not all(path.exists() for path in required) or PREFLIGHT_FILE.exists():
        raise RuntimeError("R12E runtime state is not a recoverable partial preflight")
    delegation = SQLiteDelegationStore(AUTHORITY_DB)
    with sqlite3.connect(AUTHORITY_DB) as connection:
        delegation_id = connection.execute(
            "SELECT delegation_id FROM delegations"
        ).fetchone()[0]
        lease_id = connection.execute(
            "SELECT lease_id FROM capability_leases"
        ).fetchone()[0]
        message_id = connection.execute(
            "SELECT message_id FROM agent_mailbox_messages WHERE message_type='DELEGATION'"
        ).fetchone()[0]
        receipt_id, attempt_id = connection.execute(
            "SELECT receipt_id,attempt_id FROM delegation_receipts"
        ).fetchone()
    with sqlite3.connect(START_DB) as connection:
        reservation_id = connection.execute(
            "SELECT reservation_id FROM execution_launch_attempts"
        ).fetchone()[0]
    envelope = delegation.get_delegation(delegation_id)
    lease = delegation.get_lease(lease_id)
    receipt = delegation.get_receipt(attempt_id)
    start = SQLiteExecutionStartStore(db_path=str(START_DB))
    try:
        launch = start.get_launch_attempt(reservation_id)
        reservation = start.get_reservation(reservation_id)
    finally:
        start.close()
    config = _trusted_config(envelope.task_input_hash, receipt.artifact_hash)
    adapter = CodexReceiverAdapter(config=config)
    record = adapter.registry.get(launch.idempotency_key)
    if (
        record is None or record.start_state != "PREPARED"
        or record.terminal_state is not None or record.pid is not None
    ):
        raise RuntimeError("partial preflight is not safely resumable before live start")
    binary = adapter.verify_binary()
    argv = adapter.build_argv(record.runtime_run_id)
    stdin_payload = json.loads(STDIN_FILE.read_text(encoding="utf-8"))
    packet = {
        "artifact_type": "hermes.ea4d4f_r12e_preflight",
        "artifact_version": "1",
        "prepared_at": _now(),
        "repository_head": _git_head(),
        "source_sha256": _source_hashes(),
        "frozen_r11_sha256": FROZEN_R11_SHA256,
        "delegation_id": envelope.delegation_id,
        "task_input_hash": envelope.task_input_hash,
        "receipt_hash": receipt.artifact_hash,
        "lease_id": lease.lease_id,
        "mailbox_message_id": message_id,
        "receipt_id": receipt_id,
        "authorization_id": lease.authorization_id,
        "claim_id": reservation.claim_id,
        "attempt_id": lease.attempt_id,
        "route_id": lease.route_id,
        "launch_attempt_id": launch.launch_attempt_id,
        "launch_attempt_hash": launch.artifact_hash,
        "reservation_id": reservation_id,
        "launch_idempotency_key": launch.idempotency_key,
        "runtime_run_id": record.runtime_run_id,
        "binary_path": binary.executable,
        "binary_sha256": binary.sha256,
        "binary_version": binary.version,
        "argv": argv.to_list(),
        "argv_hash": record.argv_hash,
        "cwd": argv.cwd,
        "environment_names": [name for name, _ in argv.env],
        "timeout_seconds": config.timeout_seconds,
        "result_schema_id": RESULT_SCHEMA_ID,
        "schema_file": str(SCHEMA_FILE),
        "schema_sha256": _file_hash(SCHEMA_FILE),
        "schema_contract_sha256": adapter.qualify_schema_contract().schema_sha256,
        "schema_qualification_id": adapter.qualify_schema_contract().qualification_id,
        "structural_schema_policy_id": STRUCTURAL_POLICY_ID,
        "instance_schema_qualification_id": (
            adapter.qualify_instance_schema_contract().qualification_id
        ),
        "instance_lineage_hash": (
            adapter.qualify_instance_schema_contract().instance_lineage_hash
        ),
        "stdin_file": str(STDIN_FILE),
        "stdin_sha256": sha256_payload(stdin_payload),
        "live_invocations_authorized": 1,
        "definitive_starts": 0,
        "remaining": 1,
    }
    _write_json(PREFLIGHT_FILE, packet)
    preflight_hash = _file_hash(PREFLIGHT_FILE)
    PREFLIGHT_HASH_FILE.write_text(preflight_hash + "\n", encoding="ascii")
    return {"preflight_sha256": preflight_hash, **packet}


def prepare() -> dict:
    if EVIDENCE_FILE.exists():
        raise RuntimeError("R12E evidence already exists; live proof cannot be prepared again")
    if any(path.exists() for path in (AUTHORITY_DB, START_DB, TRANSPORT_DB, PREFLIGHT_FILE)):
        return _resume_preflight()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if _file_hash(R11_FILE) != FROZEN_R11_SHA256:
        raise RuntimeError("frozen R11 hash mismatch")

    envelope = build_delegated_task_envelope(
        delegation_revision=0,
        originator_request_id="ea4d4f-r12e-one-shot",
        task_id="task-ea4d4f-r12e",
        parent_task_id=None,
        originator_agent_id=ORIGINATOR,
        requested_target_agent_id=RECEIVER,
        operation="return_bounded_qualification_result",
        objective="Return the exact deterministic R12E qualification result.",
        instructions="Use no tools and return only the required structured result.",
        input_manifest=[],
        scope={
            "read_paths": [], "write_paths": [], "allowed_tools": [],
            "network_policy": "deny", "approved_hosts": [],
            "time_budget_seconds": 120,
        },
        expected_result_schema_id=RESULT_SCHEMA_ID,
        expected_evidence=[{
            "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
        }],
        requested_at="2026-08-29T00:00:00Z",
        expires_at=DEADLINE,
        redelegation_allowed=False,
    )
    chain = _build_canonical_chain(
        seed="ea4d4f-r12e",
        deadline=DEADLINE,
        operation=envelope.operation,
        worker_class=RECEIVER,
        input_hash=envelope.artifact_hash,
        worker_id=RECEIVER,
    )
    authority = SQLiteExecutionAuthorizationStore(db_path=str(AUTHORITY_DB))
    start = SQLiteExecutionStartStore(db_path=str(START_DB))
    try:
        _persist_canonical_chain(authority, chain)
        reservation = _make_reservation(chain, launcher_actor=_launcher_actor())
        _persist_reservation(
            start, reservation, now=reservation.reserved_at,
            must_start_by=reservation.must_start_by,
        )
        binding_registry = _make_binding_registry(chain)
        launch = admit_execution_launch_attempt(
            authority_store=authority,
            start_store=start,
            binding_registry=binding_registry,
            reservation_id=reservation.reservation_id,
            launcher_actor=_launcher_actor(),
        )
    finally:
        start.close()
        authority.close()

    receiver_descriptor_hash = sha256_payload({
        "agent_id": RECEIVER,
        "adapter": "codex-cli",
        "adapter_version": PINNED_ADAPTER_VERSION,
        "binary_sha256": PINNED_CODEX_SHA256,
    })
    lease = build_delegated_capability_lease(
        delegation_id=envelope.delegation_id,
        delegated_task_hash=envelope.artifact_hash,
        authorization_id=chain.authorization.authorization_id,
        authorization_hash=chain.authorization.artifact_hash,
        attempt_id=chain.attempt.attempt_id,
        attempt_hash=chain.attempt.artifact_hash,
        route_id=chain.route.route_id,
        route_hash=chain.route.artifact_hash,
        recipient_agent_id=RECEIVER,
        worker_descriptor_hash=receiver_descriptor_hash,
        allowed_operation=envelope.operation,
        allowed_tools=[], prohibited_tools=[
            "shell", "network", "browser", "image_generation", "multi_agent",
        ],
        permitted_read_paths=[], permitted_write_paths=[],
        network_policy="deny", approved_hosts=[], max_runtime_seconds=120,
        expected_result_schema_id=RESULT_SCHEMA_ID,
        expected_evidence=envelope.expected_evidence,
        issued_at="2026-08-29T00:00:01Z",
        not_before="2026-08-29T00:00:01Z",
        expires_at=DEADLINE,
        redelegation_allowed=False,
    )
    delegation = SQLiteDelegationStore(AUTHORITY_DB)
    delegation.create_delegation(envelope)
    delegation.issue_lease(lease)
    message = delegation.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-29T00:00:02Z",
    )
    delegation.claim_message(
        message.message_id, recipient_agent_id=RECEIVER,
        claim_token="r12e-receiver-claim",
        claimed_at="2026-08-29T00:00:03Z",
        claim_expires_at=DEADLINE,
    )

    runtime_run_id = "codex-run-" + hashlib.sha256(
        launch.idempotency_key.encode("utf-8")
    ).hexdigest()[:32]
    receipt = build_delegation_receipt(
        delegation_id=envelope.delegation_id,
        delegated_task_hash=envelope.artifact_hash,
        capability_lease_id=lease.lease_id,
        capability_lease_hash=lease.artifact_hash,
        authorization_id=chain.authorization.authorization_id,
        authorization_hash=chain.authorization.artifact_hash,
        attempt_id=chain.attempt.attempt_id,
        attempt_hash=chain.attempt.artifact_hash,
        route_id=chain.route.route_id,
        route_hash=chain.route.artifact_hash,
        launch_attempt_id=launch.launch_attempt_id,
        launch_attempt_hash=launch.artifact_hash,
        receiver_agent_id=RECEIVER,
        receiver_descriptor_hash=receiver_descriptor_hash,
        receiver_implementation="codex-cli-agent",
        receiver_version=PINNED_CODEX_VERSION,
        runtime_run_id=runtime_run_id,
        outcome="ACCEPTED", reason_code=None, reason_summary=None,
        received_at="2026-08-29T00:00:04Z",
        decided_at="2026-08-29T00:00:05Z",
    )
    delegation.record_receipt(receipt, source_message_id=message.message_id)
    _write_json(SCHEMA_FILE, _schema(envelope.task_input_hash, receipt.artifact_hash))
    stdin_payload = _stdin(envelope, lease, receipt)
    _write_json(STDIN_FILE, stdin_payload)
    stdin_data = canonical_json(stdin_payload)

    config = _trusted_config(envelope.task_input_hash, receipt.artifact_hash)
    adapter = CodexReceiverAdapter(config=config)
    record, argv, replayed = adapter.prepare_invocation(
        idempotency_key=launch.idempotency_key,
        launch_attempt_id=launch.launch_attempt_id,
        delegation_id=envelope.delegation_id,
        stdin_data=stdin_data,
    )
    if replayed or record.runtime_run_id != runtime_run_id:
        raise RuntimeError("final transport preparation identity mismatch")
    binary = adapter.verify_binary()
    head = _git_head()
    packet = {
        "artifact_type": "hermes.ea4d4f_r12e_preflight",
        "artifact_version": "1",
        "prepared_at": _now(),
        "repository_head": head,
        "source_sha256": _source_hashes(),
        "frozen_r11_sha256": FROZEN_R11_SHA256,
        "delegation_id": envelope.delegation_id,
        "task_input_hash": envelope.task_input_hash,
        "receipt_hash": receipt.artifact_hash,
        "lease_id": lease.lease_id,
        "mailbox_message_id": message.message_id,
        "receipt_id": receipt.receipt_id,
        "authorization_id": chain.authorization.authorization_id,
        "claim_id": chain.claim.claim_id,
        "attempt_id": chain.attempt.attempt_id,
        "route_id": chain.route.route_id,
        "launch_attempt_id": launch.launch_attempt_id,
        "launch_attempt_hash": launch.artifact_hash,
        "reservation_id": reservation.reservation_id,
        "launch_idempotency_key": launch.idempotency_key,
        "runtime_run_id": record.runtime_run_id,
        "binary_path": binary.executable,
        "binary_sha256": binary.sha256,
        "binary_version": binary.version,
        "argv": argv.to_list(),
        "argv_hash": record.argv_hash,
        "cwd": argv.cwd,
        "environment_names": [name for name, _ in argv.env],
        "timeout_seconds": config.timeout_seconds,
        "result_schema_id": RESULT_SCHEMA_ID,
        "schema_file": str(SCHEMA_FILE),
        "schema_sha256": _file_hash(SCHEMA_FILE),
        "schema_contract_sha256": adapter.qualify_schema_contract().schema_sha256,
        "schema_qualification_id": adapter.qualify_schema_contract().qualification_id,
        "structural_schema_policy_id": STRUCTURAL_POLICY_ID,
        "instance_schema_qualification_id": (
            adapter.qualify_instance_schema_contract().qualification_id
        ),
        "instance_lineage_hash": (
            adapter.qualify_instance_schema_contract().instance_lineage_hash
        ),
        "stdin_file": str(STDIN_FILE),
        "stdin_sha256": sha256_payload(stdin_payload),
        "live_invocations_authorized": 1,
        "definitive_starts": 0,
        "remaining": 1,
    }
    _write_json(PREFLIGHT_FILE, packet)
    preflight_hash = _file_hash(PREFLIGHT_FILE)
    PREFLIGHT_HASH_FILE.write_text(preflight_hash + "\n", encoding="ascii")
    return {"preflight_sha256": preflight_hash, **packet}


def refreeze() -> dict:
    """Bind an untouched PREPARED invocation to the current committed source."""
    if EVIDENCE_FILE.exists() or not PREFLIGHT_FILE.exists():
        raise RuntimeError("R12E preflight is not eligible for source refreeze")
    packet = json.loads(PREFLIGHT_FILE.read_text(encoding="utf-8"))
    adapter = CodexReceiverAdapter(config=_trusted_config(
        packet["task_input_hash"], packet["receipt_hash"]
    ))
    record = adapter.registry.get(packet["launch_idempotency_key"])
    if (
        record is None or record.start_state != "PREPARED"
        or record.terminal_state is not None or record.pid is not None
    ):
        raise RuntimeError("live start evidence exists; preflight refreeze forbidden")
    packet["repository_head"] = _git_head()
    packet["source_sha256"] = _source_hashes()
    packet["refrozen_at"] = _now()
    packet["definitive_starts"] = 0
    packet["remaining"] = 1
    _write_json(PREFLIGHT_FILE, packet)
    preflight_hash = _file_hash(PREFLIGHT_FILE)
    PREFLIGHT_HASH_FILE.write_text(preflight_hash + "\n", encoding="ascii")
    return {"preflight_sha256": preflight_hash, **packet}


class _StartedLookup(RuntimeStartLookup):
    def __init__(self, runtime_run_id):
        self.runtime_run_id = runtime_run_id
    def lookup(self, idempotency_key):
        return RuntimeLookupResult(
            outcome=RuntimeLookupOutcome.FOUND_STARTED,
            runtime_run_id=self.runtime_run_id,
            error_code=None,
            error_summary=None,
        )


def execute(expected_preflight_hash: str) -> dict:
    if EVIDENCE_FILE.exists():
        raise RuntimeError("R12E live evidence already exists; second execution forbidden")
    if _file_hash(PREFLIGHT_FILE) != expected_preflight_hash:
        raise RuntimeError("preflight hash mismatch")
    packet = json.loads(PREFLIGHT_FILE.read_text(encoding="utf-8"))
    if _file_hash(R11_FILE) != packet["frozen_r11_sha256"]:
        raise RuntimeError("frozen R11 changed after preflight")
    if _file_hash(SCHEMA_FILE) != packet["schema_sha256"]:
        raise RuntimeError("trusted result schema changed after preflight")
    config = _trusted_config(packet["task_input_hash"], packet["receipt_hash"])
    schema_adapter = CodexReceiverAdapter(config=config)
    schema = schema_adapter.qualify_schema_contract()
    if schema.schema_sha256 != packet["schema_contract_sha256"]:
        raise RuntimeError("qualified result schema changed after preflight")
    if schema.qualification_id != packet["schema_qualification_id"]:
        raise RuntimeError("result schema qualification identity changed after preflight")
    instance_schema = schema_adapter.qualify_instance_schema_contract()
    if instance_schema.structural_policy_id != packet["structural_schema_policy_id"]:
        raise RuntimeError("structural schema policy changed after preflight")
    if instance_schema.qualification_id != packet["instance_schema_qualification_id"]:
        raise RuntimeError("instance schema qualification changed after preflight")
    if instance_schema.instance_lineage_hash != packet["instance_lineage_hash"]:
        raise RuntimeError("instance schema lineage changed after preflight")
    if _source_hashes() != packet["source_sha256"]:
        raise RuntimeError("R12E source changed after preflight")
    stdin_payload = json.loads(STDIN_FILE.read_text(encoding="utf-8"))
    if sha256_payload(stdin_payload) != packet["stdin_sha256"]:
        raise RuntimeError("canonical stdin changed after preflight")
    head = _git_head()
    if head != packet["repository_head"]:
        raise RuntimeError("repository HEAD changed after preflight")

    delegation = SQLiteDelegationStore(AUTHORITY_DB)
    envelope = delegation.get_delegation(packet["delegation_id"])
    lease = delegation.get_lease(packet["lease_id"])
    receipt = delegation.get_receipt(packet["attempt_id"])
    if (
        envelope.task_input_hash != packet["task_input_hash"]
        or receipt.artifact_hash != packet["receipt_hash"]
    ):
        raise RuntimeError("durable task/receipt lineage differs from preflight")
    launch_store = SQLiteExecutionStartStore(db_path=str(START_DB))
    authority_store = SQLiteExecutionAuthorizationStore(db_path=str(AUTHORITY_DB))
    evidence = {
        "artifact_type": "hermes.ea4d4f_r12e_live_proof_evidence",
        "artifact_version": "1",
        "preflight_sha256": expected_preflight_hash,
        "started_at": _now(),
        "definitive_starts": 0,
        "remaining": 1,
    }
    try:
        launch = launch_store.get_launch_attempt(packet["reservation_id"])
        if launch is None or launch.artifact_hash != packet["launch_attempt_hash"]:
            raise RuntimeError("durable launch attempt does not match preflight")
        process = CodexLiveProcess()
        adapter = CodexReceiverAdapter(config=config, process_impl=process)
        outcome = adapter.execute(
            idempotency_key=launch.idempotency_key,
            launch_attempt_id=launch.launch_attempt_id,
            delegation_id=envelope.delegation_id,
            stdin_data=canonical_json(stdin_payload),
        )
        evidence.update({
            "definitive_starts": 1 if outcome.process_started else 0,
            "remaining": 0 if outcome.process_started else 1,
            "process_started": outcome.process_started,
            "replayed": outcome.replayed,
            "transport_record": outcome.record.__dict__,
            "verified_result": None if outcome.verified_result is None else outcome.verified_result.__dict__,
        })
        if not outcome.process_started:
            raise RuntimeError("live Codex process did not definitively start")
        if outcome.verified_result is None or not outcome.verified_result.valid:
            raise RuntimeError("live Codex result did not verify")

        post_launch = PostLaunchExecutionOrchestrator(
            start_result_service=ExecutionStartResultService(
                launch_store, _StartedLookup(outcome.record.runtime_run_id)
            ),
            projection_orchestrator=ExecutionStateProjectionOrchestrator(
                projector=ExecutionStateProjector(launch_store, authority_store),
                enabled=True,
            ),
        ).run_post_launch(launch.launch_attempt_id)
        payload = outcome.verified_result.payload
        result = build_delegation_result(
            delegation_id=envelope.delegation_id,
            delegated_task_hash=envelope.artifact_hash,
            authorization_id=lease.authorization_id,
            authorization_hash=lease.authorization_hash,
            attempt_id=lease.attempt_id,
            attempt_hash=lease.attempt_hash,
            launch_attempt_id=launch.launch_attempt_id,
            launch_attempt_hash=launch.artifact_hash,
            receipt_id=receipt.receipt_id,
            receipt_hash=receipt.artifact_hash,
            receiver_agent_id=receipt.receiver_agent_id,
            receiver_descriptor_hash=receipt.receiver_descriptor_hash,
            runtime_run_id=outcome.record.runtime_run_id,
            outcome=payload["outcome"],
            result_payload=payload["result_payload"],
            output_manifest=payload["output_manifest"],
            evidence_manifest=payload["evidence_manifest"],
            started_at=evidence["started_at"],
            completed_at=_now(),
            error_code=payload["error_code"],
            error_summary=payload["error_summary"],
        )
        result_store = SQLiteDelegationResultStore(AUTHORITY_DB)
        durable_result, delivery, result_message_id = result_store.record_verified_result_and_delivery(
            result,
            validated_result_schema_id=RESULT_SCHEMA_ID,
            delivered_at=_now(),
        )

        # Simulate lost launch acknowledgement: a fresh adapter must recover the
        # terminal registry row and must not call its fresh process controller.
        replay_process = CodexLiveProcess()
        replay = CodexReceiverAdapter(
            config=config, process_impl=replay_process
        ).execute(
            idempotency_key=launch.idempotency_key,
            launch_attempt_id=launch.launch_attempt_id,
            delegation_id=envelope.delegation_id,
            stdin_data=canonical_json(stdin_payload),
        )
        if not replay.replayed or replay_process._owned:
            raise RuntimeError("exact replay attempted duplicate process execution")
        divergent_blocked = False
        try:
            CodexReceiverAdapter(config=config).prepare_invocation(
                idempotency_key=launch.idempotency_key,
                launch_attempt_id=launch.launch_attempt_id,
                delegation_id=envelope.delegation_id,
                stdin_data=canonical_json({**stdin_payload, "divergent": True}),
            )
        except CodexReplayConflictError:
            divergent_blocked = True
        if not divergent_blocked:
            raise RuntimeError("divergent same-key replay did not fail closed")

        # Simulated originator restart retrieves and acknowledges the same result.
        originator = SQLiteDelegationStore(AUTHORITY_DB)
        message = originator.get_message(result_message_id)
        originator.claim_message(
            result_message_id, recipient_agent_id=ORIGINATOR,
            claim_token="r12e-originator-result-claim",
            claimed_at=_now(), claim_expires_at=DEADLINE,
        )
        originator.acknowledge_message(
            result_message_id, recipient_agent_id=ORIGINATOR,
            claim_token="r12e-originator-result-claim", acknowledged_at=_now(),
        )
        evidence.update({
            "completed_at": _now(),
            "execution_projection": post_launch.status.value,
            "result_id": durable_result.result_id,
            "result_hash": durable_result.artifact_hash,
            "result_delivery_id": delivery.result_delivery_id,
            "result_message_id": result_message_id,
            "result_delivery_state": originator.delivery_state(result_message_id),
            "delegation_projection": result_store.delegation_projection(envelope.delegation_id),
            "exact_replay_no_new_process": True,
            "divergent_replay_blocked": True,
            "originator_restart_verified": True,
        })
        return evidence
    except Exception as exc:
        evidence["completed_at"] = _now()
        evidence["error_type"] = type(exc).__name__
        evidence["error"] = str(exc)[:2000]
        raise
    finally:
        launch_store.close()
        authority_store.close()
        _write_json(EVIDENCE_FILE, evidence)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "refreeze", "execute"))
    parser.add_argument("--preflight-sha256")
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare()
    elif args.mode == "refreeze":
        result = refreeze()
    else:
        if not args.preflight_sha256:
            parser.error("execute requires --preflight-sha256")
        result = execute(args.preflight_sha256)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
