"""EA-4E.28 deterministic, non-live issuer qualification."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingHandle,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
    ProductionInvocationAuthorizationIssuer,
    compute_ea4e28_issuer_contract_id,
)


NOW = "2026-01-01T00:00:00Z"


class FakeExecutor:
    executor_id = "RealKiloProductionExecutor"

    def execute(self, request):
        raise AssertionError("EA4E28_MUST_NOT_EXECUTE")


def resolved(receiver_id="kilo-cli-agent", expires_at="2026-01-01T01:00:00Z"):
    identity = (
        "RealKiloProductionExecutor"
        if receiver_id == "kilo-cli-agent"
        else "RealOpenCodeProductionExecutor"
    )
    handle = ProductionExecutorBindingHandle(
        binding_id=f"binding-{receiver_id}",
        enablement_id=f"enablement-{receiver_id}",
        receiver_id=receiver_id,
        executor_identity=identity,
        bound_at=NOW,
        expires_at=expires_at,
        registry=ExecutorRegistry(),
    )
    executor = FakeExecutor()
    executor.executor_id = identity
    return GovernedExecutorResolution.success(executor, handle)


def issue_request(receiver_id="kilo-cli-agent", **changes):
    values = {
        "issue_request_id": "issue-001",
        "execution_request_id": "execution-001",
        "receiver_id": receiver_id,
        "binding_id": f"binding-{receiver_id}",
        "enablement_id": f"enablement-{receiver_id}",
        "nonce": "nonce-001",
        "requested_ttl_seconds": 300,
    }
    values.update(changes)
    return ProductionInvocationAuthorizationIssueRequest(**values)


@pytest.fixture
def issuer():
    return ProductionInvocationAuthorizationIssuer(clock=BindingClock(now=NOW))


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_issues_for_each_explicit_receiver(issuer, receiver_id):
    result = issuer.issue(issue_request(receiver_id), resolved(receiver_id))
    assert result.policy_decision == "ALLOW"
    assert result.authorization.receiver_id == receiver_id
    assert result.authorization.execution_request_id == "execution-001"


def test_authorization_identity_is_deterministic(issuer):
    first = issuer.issue(issue_request(), resolved())
    second = issuer.issue(issue_request(), resolved())
    assert second.idempotent_replay is True
    assert second.authorization == first.authorization


def test_same_issue_id_with_changed_material_denies(issuer):
    assert issuer.issue(issue_request(), resolved()).policy_decision == "ALLOW"
    result = issuer.issue(issue_request(execution_request_id="different"), resolved())
    assert (result.policy_decision, result.policy_reason) == (
        "DENY", "ISSUE_REQUEST_ID_COLLISION"
    )


def test_identical_replay_revalidates_current_resolution(issuer):
    request = issue_request()
    assert issuer.issue(request, resolved()).policy_decision == "ALLOW"
    replay = issuer.issue(request, GovernedExecutorResolution.reject("BINDING_EXPIRED"))
    assert (replay.policy_decision, replay.policy_reason) == (
        "DENY", "BOUND_EXECUTOR_NOT_RESOLVED"
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("issue_request_id", "", "REQUIRED_IDENTITY_MISSING"),
        ("execution_request_id", "", "REQUIRED_IDENTITY_MISSING"),
        ("receiver_id", "", "REQUIRED_IDENTITY_MISSING"),
        ("binding_id", "", "REQUIRED_IDENTITY_MISSING"),
        ("enablement_id", "", "REQUIRED_IDENTITY_MISSING"),
        ("nonce", "", "REQUIRED_IDENTITY_MISSING"),
        ("attempt_number", 2, "INVALID_ATTEMPT_NUMBER"),
        ("requested_ttl_seconds", 0, "INVALID_AUTHORIZATION_TTL"),
        ("requested_ttl_seconds", 301, "INVALID_AUTHORIZATION_TTL"),
        ("runtime_scope", "development", "UNSUPPORTED_RUNTIME_SCOPE"),
        ("delegation_class", "ambient", "UNSUPPORTED_DELEGATION_CLASS"),
    ],
)
def test_invalid_request_denies(issuer, field, value, reason):
    result = issuer.issue(replace(issue_request(), **{field: value}), resolved())
    assert (result.policy_decision, result.policy_reason) == ("DENY", reason)
    assert result.authorization is None


def test_rejected_resolution_denies(issuer):
    result = issuer.issue(
        issue_request(), GovernedExecutorResolution.reject("EXECUTOR_NOT_BOUND")
    )
    assert result.policy_reason == "BOUND_EXECUTOR_NOT_RESOLVED"


def test_missing_handle_denies(issuer):
    result = issuer.issue(
        issue_request(),
        GovernedExecutorResolution(
            resolution_decision="RESOLVED", resolution_reason="INVALID"
        ),
    )
    assert result.policy_reason == "BINDING_HANDLE_MISSING"


def test_missing_resolved_executor_denies(issuer):
    resolution = resolved()
    result = issuer.issue(issue_request(), replace(resolution, executor=None))
    assert result.policy_reason == "RESOLVED_EXECUTOR_MISSING"


def test_unsupported_receiver_denies(issuer):
    request = issue_request(receiver_id="unknown")
    result = issuer.issue(request, resolved())
    assert result.policy_reason == "UNSUPPORTED_RECEIVER"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"receiver_id": "opencode-cli-agent"}, "RECEIVER_RESOLUTION_MISMATCH"),
        ({"binding_id": "wrong"}, "BINDING_ID_MISMATCH"),
        ({"enablement_id": "wrong"}, "ENABLEMENT_ID_MISMATCH"),
    ],
)
def test_resolution_identity_mismatch_denies(issuer, changes, reason):
    result = issuer.issue(issue_request(**changes), resolved())
    assert result.policy_reason == reason


def test_expired_binding_denies():
    issuer = ProductionInvocationAuthorizationIssuer(
        clock=BindingClock(now="2026-01-01T01:00:00Z")
    )
    result = issuer.issue(issue_request(), resolved(expires_at="2026-01-01T01:00:00Z"))
    assert result.policy_reason == "BINDING_EXPIRED"


def test_authorization_cannot_outlive_binding(issuer):
    result = issuer.issue(
        issue_request(requested_ttl_seconds=300),
        resolved(expires_at="2026-01-01T00:04:59Z"),
    )
    assert result.policy_reason == "AUTHORIZATION_OUTLIVES_BINDING"


def test_issuer_does_not_execute_fake(issuer):
    result = issuer.issue(issue_request(), resolved())
    assert result.policy_decision == "ALLOW"


def test_contract_is_deterministic_sha256():
    first = compute_ea4e28_issuer_contract_id()
    assert first == compute_ea4e28_issuer_contract_id()
    assert len(first) == 64
