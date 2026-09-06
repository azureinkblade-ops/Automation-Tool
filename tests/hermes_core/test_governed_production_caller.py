"""EA-4E.29 fake-only caller-to-runtime integration qualification."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tools.hermes_core.governed_bound_executor import GovernedBoundExecutorResolver
from tools.hermes_core.governed_production_caller import (
    GovernedProductionCaller,
    GovernedProductionCallerRequest,
    compute_ea4e29_caller_contract_id,
)
from tools.hermes_core.governed_production_runtime import (
    GovernedProductionRuntime,
    GovernedProductionRuntimeRequest,
)
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
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.production_invocation_authorization import ProductionInvocationAuthorization
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-01-01T00:00:00Z"


class FakeExecutor:
    def __init__(self, receiver_id):
        self.receiver_id = receiver_id
        self.executor_id = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
        self.call_count = 0

    def execute(self, request):
        self.call_count += 1
        marker = (
            "EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK"
            if self.receiver_id == "kilo-cli-agent"
            else "EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK"
        )
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output=marker,
            reason="FAKE_EXECUTION",
        )


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    hits = {"executor": 0, "adapter": 0, "process": 0}

    def tripwire(category):
        def reject(*args, **kwargs):
            hits[category] += 1
            raise AssertionError(f"EA4E29_REAL_{category.upper()}_TRIPWIRE")
        return reject

    monkeypatch.setattr(RealKiloProductionExecutor, "__init__", tripwire("executor"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "__init__", tripwire("executor"))
    monkeypatch.setattr(KiloAdapter, "execute", tripwire("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", tripwire("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", tripwire("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", tripwire("process"))
    yield hits
    assert hits == {"executor": 0, "adapter": 0, "process": 0}


@pytest.fixture
def system():
    clock = BindingClock(now=NOW)
    registry = ExecutorRegistry()
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=clock), clock=clock
    )
    runtime = GovernedProductionRuntime(
        clock=ClockCollaborator(now=NOW),
        executor_registry=registry,
        binding_controller=controller,
    )
    caller = GovernedProductionCaller(
        resolver=GovernedBoundExecutorResolver(
            binding_controller=controller, executor_registry=registry, clock=clock
        ),
        issuer=ProductionInvocationAuthorizationIssuer(clock=clock),
        runtime=runtime,
    )
    return caller, controller, registry, clock


def bind(system, receiver_id):
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
        request_nonce=f"binding-nonce-{receiver_id}",
    )
    fake = FakeExecutor(receiver_id)
    handle = controller.bind(enablement, ExecutorRegistry(), executor_factory=lambda: fake)
    registry.register(receiver_id, fake)
    return fake, handle


def caller_request(receiver_id="kilo-cli-agent", request_id="request-001", handle=None):
    receiver = QUALIFIED_RECEIVERS[receiver_id]
    runtime_request = GovernedProductionRuntimeRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=receiver["transport_contract_id"],
        model_binding_id=receiver["model_binding_id"],
    )
    issue_request = ProductionInvocationAuthorizationIssueRequest(
        issue_request_id=f"issue-{request_id}",
        execution_request_id=request_id,
        receiver_id=receiver_id,
        binding_id=handle.binding_id if handle else f"binding-{receiver_id}",
        enablement_id=handle.enablement_id if handle else f"enablement-{receiver_id}",
        nonce=f"nonce-{request_id}",
    )
    return GovernedProductionCallerRequest(runtime_request, issue_request)


@pytest.mark.parametrize(
    ("receiver_id", "marker"),
    [
        ("kilo-cli-agent", "EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK"),
        ("opencode-cli-agent", "EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK"),
    ],
)
def test_full_fake_caller_path(system, receiver_id, marker):
    fake, handle = bind(system, receiver_id)
    result = system[0].invoke(caller_request(receiver_id, handle=handle))
    assert result.caller_decision == "EXECUTED"
    assert result.resolution_decision == "RESOLVED"
    assert result.issuance_decision == "ALLOW"
    assert result.runtime_result.execution_output == marker
    assert fake.call_count == 1


def test_missing_issue_request_denies(system):
    request = caller_request()
    result = system[0].invoke(replace(request, authorization_issue_request=None))
    assert result.caller_reason == "AUTHORIZATION_ISSUE_REQUEST_REQUIRED"


def test_prepopulated_authorization_denies(system):
    request = caller_request()
    fake_auth = ProductionInvocationAuthorization(
        invocation_authorization_id="prepopulated",
        receiver_id="kilo-cli-agent",
        binding_id="binding-kilo-cli-agent",
        enablement_id="enablement-kilo-cli-agent",
        execution_request_id="request-001",
        attempt_number=1,
        issued_at=NOW,
        expires_at="2026-01-01T00:05:00Z",
        runtime_scope="production",
        delegation_class="governed",
        nonce="prepopulated",
    )
    request = replace(
        request,
        runtime_request=replace(request.runtime_request, invocation_authorization=fake_auth),
    )
    assert system[0].invoke(request).caller_reason == "AMBIGUOUS_AUTHORIZATION_SOURCE"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("execution_request_id", "different", "EXECUTION_REQUEST_ID_MISMATCH"),
        ("receiver_id", "opencode-cli-agent", "RECEIVER_ID_MISMATCH"),
    ],
)
def test_envelope_identity_mismatch_denies(system, field, value, reason):
    request = caller_request()
    issue = replace(request.authorization_issue_request, **{field: value})
    assert system[0].invoke(replace(request, authorization_issue_request=issue)).caller_reason == reason


def test_no_binding_denies_before_issuance(system):
    result = system[0].invoke(caller_request())
    assert result.caller_reason == "RESOLUTION_REJECTED:EXECUTOR_NOT_BOUND"
    assert result.issuance_decision == "NOT_EVALUATED"


def test_issuer_rejection_does_not_call_runtime(system):
    fake, handle = bind(system, "kilo-cli-agent")
    request = caller_request(handle=handle)
    issue = replace(request.authorization_issue_request, requested_ttl_seconds=301)
    result = system[0].invoke(replace(request, authorization_issue_request=issue))
    assert result.caller_reason == "ISSUANCE_REJECTED:INVALID_AUTHORIZATION_TTL"
    assert fake.call_count == 0


def test_identical_replay_is_denied_as_consumed(system):
    fake, handle = bind(system, "kilo-cli-agent")
    request = caller_request(handle=handle)
    assert system[0].invoke(request).caller_decision == "EXECUTED"
    second = system[0].invoke(request)
    assert second.caller_decision == "DENY"
    assert second.runtime_result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"
    assert fake.call_count == 1


def test_tripwires_remain_zero(system, real_path_tripwires):
    _, handle = bind(system, "kilo-cli-agent")
    assert system[0].invoke(caller_request(handle=handle)).caller_decision == "EXECUTED"
    assert real_path_tripwires == {"executor": 0, "adapter": 0, "process": 0}


def test_contract_is_deterministic_sha256():
    first = compute_ea4e29_caller_contract_id()
    assert first == compute_ea4e29_caller_contract_id()
    assert len(first) == 64
