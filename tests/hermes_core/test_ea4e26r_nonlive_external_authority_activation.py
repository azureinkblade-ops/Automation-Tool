from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.hermes_core.durable_auth_test_support import (
    QualificationDurablePolicy,
    qualification_store,
)
from tests.hermes_core.ea4e26r_test_support import (
    QUALIFICATION_CLOCK,
    external_authority_and_activation,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.governed_production_caller import GovernedProductionCallerResult
from tools.hermes_core.governed_production_runtime import (
    GovernedProductionRuntime,
    GovernedProductionRuntimeRequest,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_adapter import PINNED_KILO_PATH
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import PINNED_OPENCODE_PATH
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_activation import build_production_activation
from tools.hermes_core.production_app_adapter import ProductionAppAdapter
from tools.hermes_core.production_app_binding import (
    ProductionAppBindingProvisioner,
    ProductionAppBindingRequest,
)
from tools.hermes_core.production_app_callsite import ProductionAppCallSite
from tools.hermes_core.production_app_user_action import (
    ProductionAppUserAction,
    ProductionAppUserActionRequest,
)
from tools.hermes_core.production_application_caller import ProductionApplicationCaller
from tools.hermes_core.production_entrypoint import (
    ProductionEntryPoint,
    ProductionEntryPointRequest,
    ProductionEntryPointResult,
)
from tools.hermes_core.production_execution import ProductionExecutorResult
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import (
    ClockCollaborator,
    ProductionIssuancePolicy,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthorityScope,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id, get_default_router


class FakeExecutor:
    def __init__(self, receiver_id: str) -> None:
        self.receiver_id = receiver_id
        self.executor_id = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output=f"EA4E26R_{self.receiver_id}_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


def _system(tmp_path, receiver_id: str, request_id: str):
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    binding_clock = BindingClock(now=QUALIFICATION_CLOCK)
    registry = ExecutorRegistry()
    fake = FakeExecutor(receiver_id)
    registry.register(receiver_id, fake)
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=binding_clock),
        clock=binding_clock,
    )
    qualified = QUALIFIED_RECEIVERS[receiver_id]
    executor = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    binding = ProductionAppBindingProvisioner(controller, registry).bind(
        ProductionAppBindingRequest(
            enablement_id=f"enablement-{request_id}",
            receiver_id=receiver_id,
            executor_id=executor["executor_identity"],
            executor_factory=executor["executor_factory"],
            transport_contract_id=qualified["transport_contract_id"],
            model_binding_id=qualified["model_binding_id"],
            runtime_scope="production",
            issued_at=binding_clock.now_iso(),
            expires_at=binding_clock.now_plus_seconds(3600),
            requested_ttl_seconds=3600,
            request_nonce=f"binding-{request_id}",
            delegation_class="governed",
        )
    )
    assert binding.binding_decision == "BOUND"
    assert binding.handle is not None
    policy = QualificationDurablePolicy(
        clock=clock,
        store=qualification_store(tmp_path, f"{receiver_id}-{request_id}.sqlite3"),
    )
    runtime = GovernedProductionRuntime(
        clock=clock,
        executor_registry=registry,
        binding_controller=controller,
        invocation_authorization_policy=policy,
    )
    authority, activation = external_authority_and_activation(
        receiver_id, request_id, clock=clock
    )
    authorization = ProductionInvocationAuthorization(
        invocation_authorization_id=f"invocation-{request_id}",
        receiver_id=receiver_id,
        binding_id=binding.handle.binding_id,
        enablement_id=binding.handle.enablement_id,
        execution_request_id=request_id,
        attempt_number=1,
        issued_at=QUALIFICATION_CLOCK,
        expires_at="2026-01-01T00:05:00Z",
        runtime_scope="production",
        delegation_class="governed",
        nonce=f"invocation-{request_id}",
    )
    request = GovernedProductionRuntimeRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=qualified["transport_contract_id"],
        model_binding_id=qualified["model_binding_id"],
        invocation_authorization=authorization,
        execution_authority=authority,
        activation=activation,
    )
    return runtime, request, fake


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_external_authority_and_activation_reach_fake_executor(tmp_path, receiver_id):
    runtime, request, fake = _system(tmp_path, receiver_id, f"positive-{receiver_id}")
    result = runtime.execute(request)
    assert result.ea4e26_disposition == "PASS"
    assert result.issuance_policy_decision == "EXTERNAL_AUTHORITY"
    assert result.authority_valid is True
    assert result.activation_valid is True
    assert result.executor_called is True
    assert fake.calls == 1


def _request_without_execution(receiver_id="kilo-cli-agent", request_id="matrix"):
    qualified = QUALIFIED_RECEIVERS[receiver_id]
    authority, activation = external_authority_and_activation(receiver_id, request_id)
    return GovernedProductionRuntimeRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=qualified["transport_contract_id"],
        model_binding_id=qualified["model_binding_id"],
        execution_authority=authority,
        activation=activation,
    )


def _rebuilt_authority(request, **changes):
    authority = request.execution_authority
    fields = {
        "receiver_id": authority.receiver_id,
        "transport_contract_id": authority.transport_contract_id,
        "model_binding_id": authority.model_binding_id,
        "router_contract_id": authority.router_contract_id,
        "scope": authority.scope,
        "delegation_class": authority.delegation_class,
        "decision": authority.decision,
        "issued_at": authority.issued_at,
        "expires_at": authority.expires_at,
        "nonce": authority.nonce,
    }
    fields.update(changes)
    return build_dispatch_authority(**fields)


def _rebuilt_activation(request, **changes):
    activation = request.activation
    fields = {
        "receiver_id": activation.receiver_id,
        "router_contract_id": activation.router_contract_id,
        "authority_contract_id": activation.authority_contract_id,
        "transport_contract_id": activation.transport_contract_id,
        "model_binding_id": activation.model_binding_id,
        "activation_mode": activation.activation_mode,
        "execution_scope": activation.execution_scope,
        "delegation_class": activation.delegation_class,
    }
    fields.update(changes)
    return build_production_activation(**fields)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda request: replace(request, execution_authority=None), "EXECUTION_AUTHORITY_MISSING"),
        (lambda request: replace(request, execution_authority=object()), "MALFORMED_AUTHORITY"),
        (
            lambda request: replace(
                request,
                execution_authority=replace(request.execution_authority, decision="DENIED"),
            ),
            "EXECUTION_AUTHORITY_DENIED",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=external_authority_and_activation(
                    "opencode-cli-agent", "cross-authority"
                )[0],
            ),
            "AUTHORITY_RECEIVER_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=replace(
                    request.execution_authority, transport_contract_id="wrong"
                ),
            ),
            "TRANSPORT_CONTRACT_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=replace(
                    request.execution_authority, model_binding_id="wrong"
                ),
            ),
            "MODEL_BINDING_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=replace(
                    request.execution_authority, router_contract_id="wrong"
                ),
            ),
            "ROUTER_CONTRACT_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=_rebuilt_authority(
                    request, expires_at="2025-12-31T23:59:59Z"
                ),
            ),
            "AUTHORITY_EXPIRED",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=_rebuilt_authority(
                    request,
                    scope=DispatchAuthorityScope(
                        operation="different-operation",
                        receiver_id=request.receiver_id,
                        attempt_limit=request.requested_attempt_limit,
                    ),
                ),
            ),
            "AUTHORITY_OPERATION_SCOPE_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=_rebuilt_authority(
                    request,
                    scope=DispatchAuthorityScope(
                        operation=request.requested_operation,
                        receiver_id=request.receiver_id,
                        attempt_limit=2,
                    ),
                ),
            ),
            "AUTHORITY_ATTEMPT_SCOPE_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                execution_authority=_rebuilt_authority(
                    request, delegation_class="different-delegation"
                ),
            ),
            "AUTHORITY_DELEGATION_CLASS_MISMATCH",
        ),
    ],
)
def test_authority_fail_closed_matrix(tmp_path, mutation, reason):
    runtime, _, _ = _system(tmp_path, "kilo-cli-agent", f"authority-{reason}")
    request = mutation(_request_without_execution(request_id=f"authority-{reason}"))
    result = runtime.execute(request)
    assert result.ea4e26_disposition == "FAIL"
    assert reason in result.reason
    assert result.executor_called is False


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda request: replace(request, activation=None), "PRODUCTION_ACTIVATION_MISSING"),
        (lambda request: replace(request, activation=object()), "MALFORMED_ACTIVATION"),
        (
            lambda request: replace(
                request,
                activation=build_production_activation(
                    receiver_id=request.receiver_id,
                    router_contract_id=request.router_contract_id,
                    authority_contract_id=compute_ea4e7_authority_contract_id(),
                    transport_contract_id=request.transport_contract_id,
                    model_binding_id=request.model_binding_id,
                    activation_mode="DISABLED",
                    execution_scope=request.requested_execution_scope,
                    delegation_class=request.delegation_class,
                ),
            ),
            "PRODUCTION_ACTIVATION_DISABLED",
        ),
        (
            lambda request: replace(
                request,
                activation=external_authority_and_activation(
                    "opencode-cli-agent", "cross-activation"
                )[1],
            ),
            "ACTIVATION_RECEIVER_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                activation=_rebuilt_activation(
                    request, execution_scope="different-scope"
                ),
            ),
            "ACTIVATION_EXECUTION_SCOPE_MISMATCH",
        ),
        (
            lambda request: replace(
                request,
                activation=_rebuilt_activation(
                    request, delegation_class="different-delegation"
                ),
            ),
            "ACTIVATION_DELEGATION_CLASS_MISMATCH",
        ),
    ],
)
def test_activation_fail_closed_matrix(tmp_path, mutation, reason):
    runtime, _, _ = _system(tmp_path, "kilo-cli-agent", f"activation-{reason}")
    request = mutation(_request_without_execution(request_id=f"activation-{reason}"))
    result = runtime.execute(request)
    assert result.ea4e26_disposition == "FAIL"
    assert reason in result.reason
    assert result.executor_called is False


def test_valid_authority_and_activation_are_passed_by_reference(tmp_path, monkeypatch):
    runtime, request, _ = _system(tmp_path, "kilo-cli-agent", "reference")
    seen = {}
    original = runtime._boundary.execute

    def capture(**kwargs):
        seen.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(runtime._boundary, "execute", capture)
    assert runtime.execute(request).ea4e26_disposition == "PASS"
    assert seen["authority"] is request.execution_authority
    assert seen["activation"] is request.activation


class RecordingEntryPoint:
    master_enable = "ENABLED"

    def __init__(self):
        self.request = None

    def handle(self, request):
        self.request = request
        return ProductionEntryPointResult("ALLOW", "RECORDED")


def test_application_layers_pass_external_artifacts_without_mutation():
    authority, activation = external_authority_and_activation("kilo-cli-agent", "layers")
    leaf = RecordingEntryPoint()
    action = ProductionAppUserAction(
        ProductionAppCallSite(
            ProductionAppAdapter(ProductionApplicationCaller(leaf)),
            feature_gate="ENABLED",
        )
    )
    result = action.submit(
        ProductionAppUserActionRequest(
            request_id="layers",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
            execution_authority=authority,
            activation=activation,
        )
    )
    assert result.user_action_decision == "ALLOW"
    assert leaf.request.execution_authority is authority
    assert leaf.request.activation is activation


class RecordingCaller:
    def __init__(self):
        self.request = None

    def invoke(self, request):
        self.request = request
        return GovernedProductionCallerResult("DENY", "RECORDED")


def test_entrypoint_passes_external_artifacts_to_runtime_request():
    authority, activation = external_authority_and_activation("kilo-cli-agent", "entry")
    caller = RecordingCaller()
    composition = SimpleNamespace(
        config=SimpleNamespace(
            master_enable="ENABLED",
            default_receiver="NONE",
            kilo_executable_path=PINNED_KILO_PATH,
            opencode_executable_path=PINNED_OPENCODE_PATH,
        ),
        router=get_default_router(),
        binding_controller=SimpleNamespace(
            get_binding_for_receiver=lambda receiver_id: object()
        ),
        caller=caller,
    )
    entrypoint = ProductionEntryPoint(composition)
    entrypoint.handle(
        ProductionEntryPointRequest(
            request_id="entry",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
            authorization_issue_request=ProductionInvocationAuthorizationIssueRequest(
                issue_request_id="issue-entry",
                execution_request_id="entry",
                receiver_id="kilo-cli-agent",
                binding_id="binding-entry",
                enablement_id="enablement-entry",
                nonce="nonce-entry",
            ),
            execution_authority=authority,
            activation=activation,
        )
    )
    assert caller.request.runtime_request.execution_authority is authority
    assert caller.request.runtime_request.activation is activation


def test_runtime_source_has_no_authority_or_activation_creation():
    source = Path("tools/hermes_core/governed_production_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "ProductionIssuancePolicy" not in source
    assert "ProductionIssuanceRequest" not in source
    assert "build_dispatch_authority" not in source
    assert "build_production_activation" not in source


def test_runtime_tripwires_stay_quiet_after_external_artifacts_exist(
    tmp_path, monkeypatch
):
    runtime, request, fake = _system(tmp_path, "kilo-cli-agent", "tripwires")

    def forbidden(*args, **kwargs):
        raise AssertionError("EA4E26R_FORBIDDEN_RUNTIME_CAPABILITY")

    monkeypatch.setattr(ProductionIssuancePolicy, "evaluate", forbidden)
    monkeypatch.setattr(ProductionInvocationAuthorizationIssuer, "issue", forbidden)
    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", forbidden)
    monkeypatch.setattr(ProductionExecutorBindingController, "bind", forbidden)
    monkeypatch.setattr(KiloProcessController, "start", forbidden)
    monkeypatch.setattr(OpenCodeLiveProcess, "start", forbidden)
    monkeypatch.setattr(KiloAdapter, "execute", forbidden)
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", forbidden)
    monkeypatch.setattr(RealKiloProductionExecutor, "execute", forbidden)
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "execute", forbidden)

    result = runtime.execute(request)
    assert result.ea4e26_disposition == "PASS"
    assert fake.calls == 1


def test_runtime_input_mapping_is_deterministic():
    first = _request_without_execution(request_id="deterministic")
    second = _request_without_execution(request_id="deterministic")
    assert first == second
    assert sha256_payload(first.execution_authority.to_canonical_dict()) == sha256_payload(
        second.execution_authority.to_canonical_dict()
    )


@pytest.mark.parametrize("candidate", [None, object()])
def test_missing_or_malformed_runtime_request_fails_closed(tmp_path, candidate):
    runtime, _, fake = _system(tmp_path, "kilo-cli-agent", "missing-request")
    result = runtime.execute(candidate)
    assert result.reason == "MISSING_OR_MALFORMED_RUNTIME_REQUEST"
    assert result.ea4e26_disposition == "FAIL"
    assert fake.calls == 0


@pytest.mark.parametrize("receiver_id", ["", "codex-cli-agent", "grok", "xai"])
def test_missing_or_unsupported_receiver_fails_before_execution(tmp_path, receiver_id):
    runtime, request, fake = _system(tmp_path, "kilo-cli-agent", "bad-receiver")
    result = runtime.execute(replace(request, receiver_id=receiver_id))
    assert result.reason.startswith("ROUTING_REJECTED:")
    assert result.ea4e26_disposition == "FAIL"
    assert fake.calls == 0


@pytest.mark.parametrize(
    ("request_receiver", "artifact_receiver"),
    [
        ("kilo-cli-agent", "opencode-cli-agent"),
        ("opencode-cli-agent", "kilo-cli-agent"),
    ],
)
def test_cross_receiver_authority_is_rejected_both_directions(
    tmp_path, request_receiver, artifact_receiver
):
    runtime, request, fake = _system(tmp_path, request_receiver, "cross-receiver")
    authority, _ = external_authority_and_activation(
        artifact_receiver, "cross-receiver"
    )
    result = runtime.execute(replace(request, execution_authority=authority))
    assert "AUTHORITY_RECEIVER_MISMATCH" in result.reason
    assert result.ea4e26_disposition == "FAIL"
    assert fake.calls == 0
