"""EA-4E.32 restart-durable authorization qualification, fake-only."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    AUTH_STORE_SCHEMA_ID,
    AUTH_STORE_SCHEMA_VERSION,
    DurableAuthorizationStoreConflict,
    DurableAuthorizationStoreError,
    DurableAuthorizationStoreIntegrityError,
    DurableAuthorizationStoreUnavailable,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.governed_bound_executor import (
    GovernedBoundExecutorResolver,
    GovernedExecutorResolution,
)
from tools.hermes_core.governed_production_caller import (
    GovernedProductionCaller,
    GovernedProductionCallerRequest,
    compute_ea4e29_caller_contract_id,
)
from tools.hermes_core.governed_production_runtime import (
    GovernedProductionRuntime,
    GovernedProductionRuntimeRequest,
    compute_ea4e26_integration_contract_id,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_execution import ProductionExecutorResult
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingHandle,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
    ProductionInvocationAuthorizationPolicy,
    compute_ea4e23_invocation_contract_id,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
    ProductionInvocationAuthorizationIssuer,
    compute_ea4e28_issuer_contract_id,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-01-01T00:00:00Z"
LATER = "2026-01-01T00:10:00Z"


class FakeExecutor:
    def __init__(self, receiver_id="kilo-cli-agent", *, fail=False):
        self.receiver_id = receiver_id
        self.executor_id = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id][
            "executor_identity"
        ]
        self.call_count = 0
        self.fail = fail

    def execute(self, request):
        self.call_count += 1
        if self.fail:
            raise RuntimeError("fake executor failure")
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E32_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


class FailBeforeIssueCommitStore(DurableInvocationAuthorizationStore):
    def _before_issue_commit(self, connection):
        raise RuntimeError("simulated issue failure")


class FailBeforeClaimCommitStore(DurableInvocationAuthorizationStore):
    def _before_claim_commit(self, connection):
        raise RuntimeError("simulated claim crash")


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    hits = {"executor": 0, "adapter": 0, "process": 0}

    def reject(category):
        def tripwire(*args, **kwargs):
            hits[category] += 1
            raise AssertionError(f"EA4E32_REAL_{category.upper()}_TRIPWIRE")
        return tripwire

    monkeypatch.setattr(RealKiloProductionExecutor, "__init__", reject("executor"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "__init__", reject("executor"))
    monkeypatch.setattr(KiloAdapter, "execute", reject("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", reject("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", reject("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", reject("process"))
    yield hits
    assert hits == {"executor": 0, "adapter": 0, "process": 0}


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "invocation-authorizations.sqlite3"


def anchor_path_for(path):
    return path.with_name(f"{path.name}.anchor.json")


def open_store(path):
    return DurableInvocationAuthorizationStore(
        path, anchor_path=anchor_path_for(path)
    )


def initialize_store(path):
    return DurableInvocationAuthorizationStore.initialize(
        path, anchor_path=anchor_path_for(path)
    )


@pytest.fixture
def store(store_path):
    return initialize_store(store_path)


def authorization(receiver_id="kilo-cli-agent", **changes):
    values = {
        "invocation_authorization_id": "auth-001",
        "receiver_id": receiver_id,
        "binding_id": f"binding-{receiver_id}",
        "enablement_id": f"enablement-{receiver_id}",
        "execution_request_id": "request-001",
        "attempt_number": 1,
        "issued_at": NOW,
        "expires_at": "2026-01-01T00:05:00Z",
        "runtime_scope": "production",
        "delegation_class": "governed",
        "nonce": "nonce-001",
    }
    values.update(changes)
    return ProductionInvocationAuthorization(**values)


def handle(receiver_id="kilo-cli-agent", **changes):
    values = {
        "binding_id": f"binding-{receiver_id}",
        "enablement_id": f"enablement-{receiver_id}",
        "receiver_id": receiver_id,
        "executor_identity": QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id][
            "executor_identity"
        ],
        "bound_at": NOW,
        "expires_at": "2026-01-01T01:00:00Z",
        "registry": ExecutorRegistry(),
    }
    values.update(changes)
    return ProductionExecutorBindingHandle(**values)


def persist(store, auth=None, issue_request_id="issue-001", issue_hash=None):
    auth = auth or authorization()
    issue_hash = issue_hash or sha256_payload({"issue_request_id": issue_request_id})
    return store.persist_issued(
        issue_request_id=issue_request_id,
        issue_request_hash=issue_hash,
        authorization_payload=auth.to_canonical_dict(),
    )


def claim(store, auth=None, clock=NOW, binding=None, request_id="request-001"):
    auth = auth or authorization()
    binding = binding or handle(auth.receiver_id)
    return ProductionInvocationAuthorizationPolicy(
        clock=BindingClock(now=clock), store=store
    ).claim_for_execution(
        auth, binding, {}, expected_execution_request_id=request_id
    )


def resolved(receiver_id="kilo-cli-agent"):
    fake = FakeExecutor(receiver_id)
    return GovernedExecutorResolution.success(fake, handle(receiver_id))


def issue_request(receiver_id="kilo-cli-agent", **changes):
    values = {
        "issue_request_id": "issue-001",
        "execution_request_id": "request-001",
        "receiver_id": receiver_id,
        "binding_id": f"binding-{receiver_id}",
        "enablement_id": f"enablement-{receiver_id}",
        "nonce": "nonce-001",
        "requested_ttl_seconds": 300,
    }
    values.update(changes)
    return ProductionInvocationAuthorizationIssueRequest(**values)


def issuer(store, now=NOW):
    return ProductionInvocationAuthorizationIssuer(
        clock=BindingClock(now=now), store=store
    )


def test_empty_store_initialization(store):
    assert store.count() == 0
    assert store.consumed_count() == 0


def test_empty_store_grants_no_authorization(store):
    assert claim(store).policy_reason == "INVOCATION_AUTHORIZATION_NOT_DURABLE"


def test_missing_store_fails_closed(store_path):
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        open_store(store_path)


def test_store_loss_after_use_fails_closed(store, store_path):
    persist(store)
    store_path.unlink()
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        open_store(store_path)


def test_issue_persists(store):
    persist(store)
    assert store.count() == 1


def test_issue_survives_store_reconstruction(store, store_path):
    persist(store)
    reopened = open_store(store_path)
    assert reopened.inspect(authorization().to_canonical_dict()).consumed is False


def test_issue_identical_replay_returns_existing(store):
    assert persist(store).replayed is False
    assert persist(store).replayed is True
    assert store.count() == 1


def test_issue_request_collision_denies(store):
    persist(store)
    with pytest.raises(DurableAuthorizationStoreConflict):
        persist(store, authorization(nonce="different"))


def test_authorization_id_collision_denies(store):
    persist(store)
    with pytest.raises(DurableAuthorizationStoreConflict):
        persist(
            store,
            authorization(nonce="different"),
            issue_request_id="issue-002",
        )


def test_issue_failure_returns_no_durable_authorization(store_path):
    initialize_store(store_path)
    failing = FailBeforeIssueCommitStore(
        store_path, anchor_path=anchor_path_for(store_path)
    )
    with pytest.raises(DurableAuthorizationStoreError):
        persist(failing)
    assert open_store(store_path).count() == 0


def test_issuer_returns_only_committed_authorization(store):
    result = issuer(store).issue(issue_request(), resolved())
    assert result.policy_decision == "ALLOW"
    assert store.inspect(result.authorization.to_canonical_dict()).consumed is False


def test_issuer_persistence_failure_returns_no_authorization(store_path):
    initialize_store(store_path)
    result = issuer(FailBeforeIssueCommitStore(
        store_path, anchor_path=anchor_path_for(store_path)
    )).issue(
        issue_request(), resolved()
    )
    assert result.policy_decision == "DENY"
    assert result.authorization is None


def test_issuer_replay_survives_reconstruction(store, store_path):
    first = issuer(store).issue(issue_request(), resolved())
    reopened = open_store(store_path)
    second = issuer(reopened).issue(issue_request(), resolved())
    assert second.idempotent_replay is True
    assert second.authorization == first.authorization


def test_valid_authorization_claims(store):
    persist(store)
    assert claim(store).policy_decision == "ALLOW"


def test_unconsumed_authorization_survives_restart(store, store_path):
    persist(store)
    reopened = open_store(store_path)
    assert claim(reopened).policy_decision == "ALLOW"


def test_consumed_authorization_remains_consumed_after_restart(store, store_path):
    persist(store)
    assert claim(store).policy_decision == "ALLOW"
    reopened = open_store(store_path)
    replay = claim(reopened)
    assert replay.policy_decision == "DENY"
    assert replay.policy_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"


def test_expired_authorization_denied_after_restart(store, store_path):
    persist(store)
    reopened = open_store(store_path)
    result = claim(reopened, clock=LATER)
    assert (result.policy_decision, result.policy_reason) == (
        "DENY", "INVOCATION_AUTHORIZATION_EXPIRED"
    )


def test_cross_receiver_replay_denied_after_restart(store, store_path):
    persist(store)
    changed = authorization(
        receiver_id="opencode-cli-agent",
        binding_id="binding-opencode-cli-agent",
        enablement_id="enablement-opencode-cli-agent",
    )
    result = claim(open_store(store_path), changed)
    assert result.policy_reason == "CROSS_RECEIVER_INVOCATION_REPLAY"


def test_binding_mismatch_denied_after_restart(store, store_path):
    persist(store)
    result = claim(
        open_store(store_path),
        binding=handle(binding_id="different"),
    )
    assert result.policy_reason == "BINDING_ID_MISMATCH"


def test_enablement_mismatch_denied_after_restart(store, store_path):
    persist(store)
    result = claim(
        open_store(store_path),
        binding=handle(enablement_id="different"),
    )
    assert result.policy_reason == "ENABLEMENT_ID_MISMATCH"


def test_request_mismatch_denied_after_restart(store, store_path):
    persist(store)
    result = claim(open_store(store_path), request_id="different")
    assert result.policy_reason == "REQUEST_IDENTITY_MISMATCH"


def test_attempt_mismatch_denied_after_restart(store, store_path):
    auth = authorization(attempt_number=2)
    persist(store, auth)
    result = claim(open_store(store_path), auth)
    assert result.policy_reason == "INVALID_ATTEMPT_NUMBER"


def test_canonical_collision_survives_restart(store, store_path):
    persist(store)
    result = claim(
        open_store(store_path),
        authorization(nonce="different"),
    )
    assert result.policy_reason == "INVOCATION_AUTHORIZATION_ID_COLLISION"


def test_post_consume_pre_executor_crash_remains_consumed(store, store_path):
    persist(store)
    assert claim(store).policy_decision == "ALLOW"
    result = claim(open_store(store_path))
    assert result.policy_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"


def test_preconsume_commit_crash_rolls_back(store, store_path):
    persist(store)
    failing = FailBeforeClaimCommitStore(
        store_path, anchor_path=anchor_path_for(store_path)
    )
    result = claim(failing)
    assert result.policy_decision == "DENY"
    assert result.policy_reason == "INVOCATION_AUTHORIZATION_STORE_ERROR"
    reopened = open_store(store_path)
    assert reopened.inspect(authorization().to_canonical_dict()).consumed is False
    assert claim(reopened).policy_decision == "ALLOW"


def test_executor_failure_does_not_restore_consumed_authorization(store, store_path):
    persist(store)
    assert claim(store).policy_decision == "ALLOW"
    fake = FakeExecutor(fail=True)
    with pytest.raises(RuntimeError):
        fake.execute(None)
    assert claim(open_store(store_path)).policy_decision == "DENY"
    assert fake.call_count == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("receiver_id", ""),
        ("canonical_authorization_hash", "bad"),
        ("binding_id", "tampered"),
        ("consumed_state", "UNKNOWN"),
        ("issued_at", "not-a-timestamp"),
        ("attempt_number", "invalid"),
        ("issue_request_hash", "bad"),
        ("record_hash", "bad"),
    ],
)
def test_corrupted_authorization_rows_fail_closed(store, column, value):
    persist(store)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            f"UPDATE invocation_authorizations SET {column} = ?", (value,)
        )
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        store.inspect_by_id("auth-001")


def test_unsupported_schema_version_fails_closed(store):
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE auth_store_metadata SET schema_version = 'future'"
        )
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        open_store(store.path)


def test_partial_issue_write_is_not_claimable_after_restart(store_path):
    initialize_store(store_path)
    with pytest.raises(DurableAuthorizationStoreError):
        persist(FailBeforeIssueCommitStore(
            store_path, anchor_path=anchor_path_for(store_path)
        ))
    reopened = open_store(store_path)
    assert claim(reopened).policy_reason == "INVOCATION_AUTHORIZATION_NOT_DURABLE"


def test_two_thread_claimers_allow_exactly_one(store, store_path):
    persist(store)

    def attempt(_):
        return claim(open_store(store_path)).policy_decision

    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(attempt, range(2)))
    assert decisions.count("ALLOW") == 1
    assert decisions.count("DENY") == 1


def test_multi_connection_claim_allows_exactly_one(store, store_path):
    persist(store)
    stores = [
        open_store(store_path),
        open_store(store_path),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(lambda item: claim(item).policy_decision, stores))
    assert decisions.count("ALLOW") == 1


def test_post_restart_concurrent_claim_allows_exactly_one(store, store_path):
    persist(store)
    del store
    with ThreadPoolExecutor(max_workers=3) as pool:
        decisions = list(
            pool.map(
                lambda _: claim(
                    open_store(store_path)
                ).policy_decision,
                range(3),
            )
        )
    assert decisions.count("ALLOW") == 1
    assert decisions.count("DENY") == 2


def test_missing_authorization_is_not_auto_created(store):
    assert claim(store).policy_decision == "DENY"
    assert store.count() == 0


def test_expired_authorization_is_not_refreshed(store):
    persist(store)
    assert claim(store, clock=LATER).policy_decision == "DENY"
    assert store.inspect_by_id("auth-001").consumed is False


def test_consumed_authorization_is_not_reissued(store):
    durable_issuer = issuer(store)
    issued = durable_issuer.issue(issue_request(), resolved())
    claim(store, issued.authorization)
    replay = durable_issuer.issue(issue_request(), resolved())
    assert replay.idempotent_replay is True
    assert replay.authorization.expires_at == issued.authorization.expires_at
    assert store.inspect_by_id(
        issued.authorization.invocation_authorization_id
    ).consumed is True


def test_invalid_authorization_is_not_replaced(store):
    persist(store)
    result = claim(store, authorization(nonce="different"))
    assert result.policy_decision == "DENY"
    assert store.count() == 1


def test_task_text_cannot_reconstruct_authorization(store):
    text = "auth-001 binding-kilo-cli-agent"
    assert text
    assert claim(store).policy_reason == "INVOCATION_AUTHORIZATION_NOT_DURABLE"


def test_store_path_does_not_change_canonical_authorization(tmp_path):
    first = initialize_store(tmp_path / "one.sqlite3")
    second = initialize_store(tmp_path / "two.sqlite3")
    persist(first)
    persist(second)
    assert first.inspect_by_id("auth-001").authorization_payload == second.inspect_by_id("auth-001").authorization_payload


def _integrated_system(store):
    clock = BindingClock(now=NOW)
    registry = ExecutorRegistry()
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=clock), clock=clock
    )
    runtime = GovernedProductionRuntime(
        clock=ClockCollaborator(now=NOW),
        executor_registry=registry,
        binding_controller=controller,
        invocation_authorization_store=store,
    )
    caller = GovernedProductionCaller(
        resolver=GovernedBoundExecutorResolver(
            binding_controller=controller,
            executor_registry=registry,
            clock=clock,
        ),
        issuer=issuer(store),
        runtime=runtime,
    )
    return caller, controller, registry, clock


def _bind(system, receiver_id="kilo-cli-agent"):
    _, controller, registry, clock = system
    info = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    receiver = QUALIFIED_RECEIVERS[receiver_id]
    enablement = ProductionExecutorBindingEnablement(
        enablement_id=f"enablement-{receiver_id}",
        receiver_id=receiver_id,
        transport_contract_id=receiver["transport_contract_id"],
        model_binding_id=receiver["model_binding_id"],
        executor_identity=info["executor_identity"],
        executor_factory=info["executor_factory"],
        runtime_scope="production",
        issued_at=clock.now_iso(),
        expires_at=clock.now_plus_seconds(3600),
        delegation_class="governed",
        requested_ttl_seconds=3600,
        max_bound_executors=1,
        enabled=True,
        request_nonce="ea4e32-binding",
    )
    fake = FakeExecutor(receiver_id)
    bound = controller.bind(
        enablement, ExecutorRegistry(), executor_factory=lambda: fake
    )
    registry.register(receiver_id, fake)
    return fake, bound


def _caller_request(bound, receiver_id="kilo-cli-agent"):
    receiver = QUALIFIED_RECEIVERS[receiver_id]
    return GovernedProductionCallerRequest(
        runtime_request=GovernedProductionRuntimeRequest(
            request_id="request-001",
            receiver_id=receiver_id,
            router_contract_id=compute_ea4e6_router_contract_id(),
            transport_contract_id=receiver["transport_contract_id"],
            model_binding_id=receiver["model_binding_id"],
        ),
        authorization_issue_request=ProductionInvocationAuthorizationIssueRequest(
            issue_request_id="issue-001",
            execution_request_id="request-001",
            receiver_id=receiver_id,
            binding_id=bound.binding_id,
            enablement_id=bound.enablement_id,
            nonce="nonce-001",
        ),
    )


def test_ea4e29_explicit_durable_handoff_reaches_fake_executor(store):
    system = _integrated_system(store)
    fake, bound = _bind(system)
    result = system[0].invoke(_caller_request(bound))
    assert result.caller_decision == "EXECUTED"
    assert fake.call_count == 1
    assert store.consumed_count() == 1


def test_ea4e29_does_not_auto_reissue_after_consumed_denial(store):
    system = _integrated_system(store)
    fake, bound = _bind(system)
    request = _caller_request(bound)
    assert system[0].invoke(request).caller_decision == "EXECUTED"
    assert system[0].invoke(request).caller_decision == "DENY"
    assert fake.call_count == 1
    assert store.count() == 1


def test_runtime_without_store_cannot_synthesize_authorization():
    runtime = GovernedProductionRuntime(clock=ClockCollaborator(now=NOW))
    assert runtime._invocation_policy._store is None


def test_issuer_without_store_denies():
    result = ProductionInvocationAuthorizationIssuer(
        clock=BindingClock(now=NOW)
    ).issue(issue_request(), resolved())
    assert result.policy_reason == "DURABLE_INVOCATION_AUTHORIZATION_STORE_REQUIRED"


def test_exact_ea4e31_contract_chain_is_bound():
    assert compute_ea4e23_invocation_contract_id() == "e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91"
    assert compute_ea4e26_integration_contract_id() == "84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67"
    assert compute_ea4e28_issuer_contract_id() == "395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1"
    assert compute_ea4e29_caller_contract_id() == "821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166"


def test_store_schema_identity_is_exact():
    assert AUTH_STORE_SCHEMA_ID == "hermes.production-invocation-authorization-store/v1"
    assert AUTH_STORE_SCHEMA_VERSION == "1"


def test_consumed_records_are_retained(store):
    persist(store)
    claim(store)
    assert store.count() == 1
    assert store.consumed_count() == 1
