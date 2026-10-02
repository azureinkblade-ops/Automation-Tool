"""EA-4E.46 strict non-live issue-request provisioning qualification."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.production_app_invocation_authorization import (
    ProductionAppInvocationAuthorizationProvisioner,
    ProductionAppInvocationAuthorizationRequest,
)
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingHandle,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ProductionIssuancePolicy
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthorityScope,
    build_dispatch_authority,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)


NOW = "2026-01-01T00:00:00+00:00"
AUTHORITY_EXPIRY = "2026-01-01T00:05:00+00:00"
BINDING_EXPIRY = "2026-01-01T00:10:00+00:00"
TRIPWIRE_HITS = {"issuer": 0, "store": 0, "binding": 0, "authority": 0}


@pytest.fixture(autouse=True)
def nonlive_tripwires(monkeypatch):
    for key in TRIPWIRE_HITS:
        TRIPWIRE_HITS[key] = 0

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E46_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(ProductionInvocationAuthorizationIssuer, "issue", trip("issuer"))
    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", trip("store"))
    monkeypatch.setattr(ProductionExecutorBindingController, "bind", trip("binding"))
    monkeypatch.setattr(ProductionIssuancePolicy, "evaluate", trip("authority"))
    yield
    assert TRIPWIRE_HITS == {"issuer": 0, "store": 0, "binding": 0, "authority": 0}


def authority(receiver_id: str = "kilo-cli-agent", **changes):
    spec = QUALIFIED_RECEIVERS[receiver_id]
    fields = {
        "receiver_id": receiver_id,
        "transport_contract_id": spec["transport_contract_id"],
        "model_binding_id": spec["model_binding_id"],
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "scope": DispatchAuthorityScope(
            operation="receiver-dispatch", receiver_id=receiver_id, attempt_limit=1
        ),
        "delegation_class": "governed",
        "decision": "GRANTED",
        "issued_at": NOW,
        "expires_at": AUTHORITY_EXPIRY,
        "nonce": f"authority-{receiver_id}",
    }
    fields.update(changes)
    return build_dispatch_authority(**fields)


def binding(receiver_id: str = "kilo-cli-agent", **changes):
    fields = {
        "binding_id": f"binding-{receiver_id}",
        "enablement_id": f"enablement-{receiver_id}",
        "receiver_id": receiver_id,
        "executor_identity": QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id][
            "executor_identity"
        ],
        "bound_at": NOW,
        "expires_at": BINDING_EXPIRY,
        "registry": ExecutorRegistry(),
    }
    fields.update(changes)
    return ProductionExecutorBindingHandle(**fields)


def request(receiver_id: str = "kilo-cli-agent", **changes):
    spec = QUALIFIED_RECEIVERS.get(receiver_id, {})
    fields = {
        "issue_request_id": f"issue-{receiver_id}",
        "execution_request_id": f"execution-{receiver_id}",
        "receiver_id": receiver_id,
        "execution_authority": authority(receiver_id)
        if receiver_id in QUALIFIED_RECEIVERS
        else None,
        "binding_handle": binding(receiver_id)
        if receiver_id in QUALIFIED_RECEIVERS
        else None,
        "transport_contract_id": spec.get("transport_contract_id", "unknown"),
        "model_binding_id": spec.get("model_binding_id", "unknown"),
        "runtime_scope": "production",
        "requested_operation": "receiver-dispatch",
        "requested_ttl_seconds": 60,
        "attempt_number": 1,
        "nonce": f"invocation-{receiver_id}",
        "delegation_class": "governed",
    }
    fields.update(changes)
    return ProductionAppInvocationAuthorizationRequest(**fields)


def provisioner(now: str = NOW):
    return ProductionAppInvocationAuthorizationProvisioner(BindingClock(now=now))


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_positive_request_is_provisioned_and_preserved(receiver_id):
    source = request(receiver_id)
    result = provisioner().provision(source)
    issue = result.issue_request
    assert result.provisioning_decision == "PROVISIONED"
    assert result.provisioning_reason == "EXPLICIT_ISSUE_REQUEST_PROVISIONED"
    assert issue is not None
    assert issue.issue_request_id == source.issue_request_id
    assert issue.execution_request_id == source.execution_request_id
    assert issue.receiver_id == receiver_id
    assert issue.binding_id == source.binding_handle.binding_id
    assert issue.enablement_id == source.binding_handle.enablement_id
    assert issue.runtime_scope == source.runtime_scope
    assert issue.requested_ttl_seconds == source.requested_ttl_seconds
    assert issue.attempt_number == source.attempt_number
    assert issue.nonce == source.nonce
    assert issue.delegation_class == source.delegation_class
    assert result.execution_authority_id == source.execution_authority.authority_id
    assert result.transport_contract_id == source.transport_contract_id
    assert result.model_binding_id == source.model_binding_id
    assert result.requested_operation == source.requested_operation


def test_missing_clock_dependency():
    result = ProductionAppInvocationAuthorizationProvisioner(None).provision(request())
    assert result.provisioning_reason == "MISSING_CLOCK_DEPENDENCY"


def test_missing_request():
    assert provisioner().provision(None).provisioning_reason == "MISSING_REQUEST"


def test_malformed_request():
    assert provisioner().provision(object()).provisioning_reason == "MALFORMED_REQUEST"


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("issue_request_id", "MISSING_ISSUE_REQUEST_ID"),
        ("execution_request_id", "MISSING_EXECUTION_REQUEST_ID"),
        ("transport_contract_id", "MISSING_TRANSPORT_CONTRACT_ID"),
        ("model_binding_id", "MISSING_MODEL_BINDING_ID"),
        ("runtime_scope", "MISSING_RUNTIME_SCOPE"),
        ("requested_operation", "MISSING_REQUESTED_OPERATION"),
        ("nonce", "MISSING_NONCE"),
        ("delegation_class", "MISSING_DELEGATION_CLASS"),
    ],
)
def test_missing_explicit_string_field(field, reason):
    assert provisioner().provision(request(**{field: ""})).provisioning_reason == reason


@pytest.mark.parametrize("receiver_id", [None, "codex-cli-agent", "grok"])
def test_missing_or_unsupported_receiver(receiver_id):
    result = provisioner().provision(request(receiver_id=receiver_id))
    assert result.provisioning_decision == "DENY"
    assert result.provisioning_reason in {"MISSING_RECEIVER", "UNSUPPORTED_RECEIVER"}


def test_missing_execution_authority():
    assert provisioner().provision(
        request(execution_authority=None)
    ).provisioning_reason == "MISSING_EXECUTION_AUTHORITY"


def test_missing_binding_handle():
    assert provisioner().provision(
        request(binding_handle=None)
    ).provisioning_reason == "MISSING_BINDING_HANDLE"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("execution_authority", object(), "MALFORMED_EXECUTION_AUTHORITY"),
        ("binding_handle", object(), "MALFORMED_BINDING_HANDLE"),
    ],
)
def test_malformed_parent(field, value, reason):
    assert provisioner().provision(request(**{field: value})).provisioning_reason == reason


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("requested_ttl_seconds", "MISSING_REQUESTED_TTL_SECONDS"),
        ("attempt_number", "MISSING_ATTEMPT_NUMBER"),
    ],
)
def test_missing_numeric_field(field, reason):
    assert provisioner().provision(request(**{field: None})).provisioning_reason == reason


def test_denied_authority():
    denied = authority(decision="DENIED")
    assert provisioner().provision(
        request(execution_authority=denied)
    ).provisioning_reason == "EXECUTION_AUTHORITY_NOT_GRANTED"


def test_tampered_authority_hash():
    tampered = replace(authority(), artifact_hash="0" * 64)
    assert provisioner().provision(
        request(execution_authority=tampered)
    ).provisioning_reason == "EXECUTION_AUTHORITY_HASH_INVALID"


@pytest.mark.parametrize(
    ("receiver_id", "parent", "reason"),
    [
        ("kilo-cli-agent", "authority", "RECEIVER_AUTHORITY_MISMATCH"),
        ("kilo-cli-agent", "binding", "RECEIVER_BINDING_MISMATCH"),
        ("opencode-cli-agent", "authority", "RECEIVER_AUTHORITY_MISMATCH"),
        ("opencode-cli-agent", "binding", "RECEIVER_BINDING_MISMATCH"),
    ],
)
def test_cross_receiver_parent_mismatch(receiver_id, parent, reason):
    other = "opencode-cli-agent" if receiver_id == "kilo-cli-agent" else "kilo-cli-agent"
    changes = {
        "execution_authority": authority(other)
        if parent == "authority"
        else authority(receiver_id),
        "binding_handle": binding(other) if parent == "binding" else binding(receiver_id),
    }
    result = provisioner().provision(request(receiver_id, **changes))
    assert result.provisioning_reason == reason


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
@pytest.mark.parametrize("identity", ["transport", "model"])
def test_cross_receiver_sealed_identity_mismatch(receiver_id, identity):
    other = "opencode-cli-agent" if receiver_id == "kilo-cli-agent" else "kilo-cli-agent"
    field = "transport_contract_id" if identity == "transport" else "model_binding_id"
    result = provisioner().provision(
        request(receiver_id, **{field: QUALIFIED_RECEIVERS[other][field]})
    )
    expected = "TRANSPORT_CONTRACT_MISMATCH" if identity == "transport" else "MODEL_BINDING_MISMATCH"
    assert result.provisioning_reason == expected


def test_authority_transport_mismatch():
    wrong = authority(
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"][
            "transport_contract_id"
        ]
    )
    assert provisioner().provision(
        request(execution_authority=wrong)
    ).provisioning_reason == "AUTHORITY_TRANSPORT_MISMATCH"


def test_authority_model_mismatch():
    wrong = authority(
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"]
    )
    assert provisioner().provision(
        request(execution_authority=wrong)
    ).provisioning_reason == "AUTHORITY_MODEL_BINDING_MISMATCH"


def test_binding_executor_identity_mismatch():
    wrong = binding(executor_identity="RealOpenCodeProductionExecutor")
    assert provisioner().provision(
        request(binding_handle=wrong)
    ).provisioning_reason == "BINDING_EXECUTOR_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"runtime_scope": "lab"}, "UNSUPPORTED_RUNTIME_SCOPE"),
        ({"delegation_class": "ungoverned"}, "UNSUPPORTED_DELEGATION_CLASS"),
        ({"attempt_number": 2}, "INVALID_ATTEMPT_NUMBER"),
        ({"requested_ttl_seconds": 0}, "INVALID_AUTHORIZATION_TTL"),
        ({"requested_ttl_seconds": 301}, "INVALID_AUTHORIZATION_TTL"),
    ],
)
def test_scope_and_bound_failures(changes, reason):
    assert provisioner().provision(request(**changes)).provisioning_reason == reason


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"requested_ttl_seconds": "60"}, "INVALID_AUTHORIZATION_TTL"),
        ({"attempt_number": "1"}, "INVALID_ATTEMPT_NUMBER"),
    ],
)
def test_non_integer_policy_values_fail_closed(changes, reason):
    assert provisioner().provision(request(**changes)).provisioning_reason == reason


def test_operation_scope_mismatch():
    assert provisioner().provision(
        request(requested_operation="other")
    ).provisioning_reason == "OPERATION_SCOPE_MISMATCH"


def test_attempt_scope_mismatch():
    wrong = authority(scope=DispatchAuthorityScope("receiver-dispatch", "kilo-cli-agent", 2))
    assert provisioner().provision(
        request(execution_authority=wrong)
    ).provisioning_reason == "ATTEMPT_SCOPE_MISMATCH"


def test_authority_delegation_class_mismatch():
    wrong = authority(delegation_class="other")
    assert provisioner().provision(
        request(execution_authority=wrong)
    ).provisioning_reason == "AUTHORITY_DELEGATION_CLASS_MISMATCH"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"execution_authority": authority(expires_at=NOW)}, "EXECUTION_AUTHORITY_EXPIRED"),
        ({"binding_handle": binding(expires_at=NOW)}, "BINDING_EXPIRED"),
        (
            {"execution_authority": authority(expires_at="2026-01-01T00:00:30+00:00")},
            "AUTHORIZATION_OUTLIVES_EXECUTION_AUTHORITY",
        ),
        (
            {"binding_handle": binding(expires_at="2026-01-01T00:00:30+00:00")},
            "AUTHORIZATION_OUTLIVES_BINDING",
        ),
    ],
)
def test_parent_expiry_and_ttl_bounds(changes, reason):
    assert provisioner().provision(request(**changes)).provisioning_reason == reason


def test_invalid_clock_timestamp():
    assert provisioner("not-a-time").provision(request()).provisioning_reason == "INVALID_TIMESTAMP"


def test_mapping_is_deterministic_and_order_irrelevant():
    first = request()
    reordered = ProductionAppInvocationAuthorizationRequest(
        **dict(reversed(list(first.__dict__.items())))
    )
    one = provisioner().provision(first)
    two = provisioner().provision(reordered)
    assert one == two
    assert one.issue_request.to_canonical_dict() == two.issue_request.to_canonical_dict()


def test_module_has_no_issuer_store_or_runtime_capability():
    source = Path(
        "tools/hermes_core/production_app_invocation_authorization.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        ".issue(",
        ".initialize(",
        ".claim(",
        ".consume(",
        "subprocess",
        "automation_state.db",
        "app.py",
        "ComfyUI",
    )
    assert all(token not in source for token in forbidden)


def test_exact_existing_issue_request_schema_is_emitted():
    payload = provisioner().provision(request()).issue_request.to_canonical_dict()
    assert tuple(payload) == (
        "issue_request_id",
        "execution_request_id",
        "receiver_id",
        "binding_id",
        "enablement_id",
        "nonce",
        "requested_ttl_seconds",
        "attempt_number",
        "runtime_scope",
        "delegation_class",
    )
