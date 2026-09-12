"""Fake-only regression for the EA-4E.25 governed OpenCode qualification path.

The legacy filename identifies the production harness under test. This module
must never instantiate a real executor or reach an adapter or process boundary.
"""

from __future__ import annotations

from types import SimpleNamespace
from dataclasses import asdict

import pytest

from tools.hermes_core.opencode_invocation_authorized_live import (
    EXPECTED_LIVE_OUTPUT,
    LiveClock,
    OpenCodeInvocationAuthorizedLiveResult,
    run_opencode_invocation_authorized_live_qualification,
)
import tools.hermes_core.opencode_invocation_authorized_live as qualification_module
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_execution import ProductionExecutorResult
from tools.hermes_core.production_executor_binding import (
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.receiver_router import QUALIFIED_RECEIVERS

NONLIVE_REGRESSION_MODE = "FAKE_ONLY"


@pytest.fixture(autouse=True)
def fake_only_opencode_boundary(monkeypatch, tmp_path):
    """Keep the regression governed while making its terminal boundary non-live."""
    calls = {
        "fake_executor_instantiations": 0,
        "fake_executor_calls": 0,
        "real_executor_tripwire": 0,
        "real_adapter_tripwire": 0,
        "process_start_tripwire": 0,
    }

    from tools.hermes_core.durable_invocation_authorization_store import (
        DurableInvocationAuthorizationStore,
    )
    from tools.hermes_core.hashing import sha256_payload

    store = DurableInvocationAuthorizationStore.initialize(
        tmp_path / "invocation.sqlite3", anchor_path=tmp_path / "invocation.anchor.json",
    )
    authorization_type = qualification_module.ProductionInvocationAuthorization
    policy_type = qualification_module.ProductionInvocationAuthorizationPolicy
    issued_authorizations = []

    def persisted_test_authorization(**kwargs):
        authorization = authorization_type(**kwargs)
        payload = asdict(authorization)
        store.persist_issued(
            issue_request_id=f"test-issue-{authorization.invocation_authorization_id}",
            issue_request_hash=sha256_payload(payload),
            authorization_payload=payload,
        )
        issued_authorizations.append(authorization)
        return authorization

    def durable_test_policy(**kwargs):
        return policy_type(store=store, **kwargs)

    monkeypatch.setattr(qualification_module, "ProductionInvocationAuthorization", persisted_test_authorization)
    monkeypatch.setattr(qualification_module, "ProductionInvocationAuthorizationPolicy", durable_test_policy)

    def reject_real_executor(*args, **kwargs):
        calls["real_executor_tripwire"] += 1
        raise AssertionError("NONLIVE_REAL_EXECUTOR_TRIPWIRE")

    def reject_real_adapter(*args, **kwargs):
        calls["real_adapter_tripwire"] += 1
        raise AssertionError("NONLIVE_REAL_ADAPTER_TRIPWIRE")

    def reject_process_start(*args, **kwargs):
        calls["process_start_tripwire"] += 1
        raise AssertionError("NONLIVE_PROCESS_START_TRIPWIRE")

    class FakeOpenCodeProductionExecutor:
        executor_id = "RealOpenCodeProductionExecutor"

        def __init__(self):
            calls["fake_executor_instantiations"] += 1
            self.last_outcome = None

        def execute(self, request):
            calls["fake_executor_calls"] += 1
            self.last_outcome = SimpleNamespace(record=object(), process_started=True)
            return ProductionExecutorResult(
                executor_id=self.executor_id,
                execution_status="SUCCESS",
                output=EXPECTED_LIVE_OUTPUT,
                reason="FAKE_OPENCODE_EXECUTION_COMPLETE",
            )

    monkeypatch.setattr(RealOpenCodeProductionExecutor, "__init__", reject_real_executor)
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", reject_real_adapter)
    monkeypatch.setattr(OpenCodeLiveProcess, "start", reject_process_start)
    monkeypatch.setattr(
        qualification_module,
        "RealOpenCodeProductionExecutor",
        FakeOpenCodeProductionExecutor,
    )

    yield calls

    assert calls["real_executor_tripwire"] == 0
    assert calls["real_adapter_tripwire"] == 0
    assert calls["process_start_tripwire"] == 0
    if calls["fake_executor_calls"]:
        assert issued_authorizations
        assert all(store.inspect(asdict(auth)).consumed for auth in issued_authorizations)


class TestOpenCodeExecutorIdentity:
    """Verify OpenCode executor identity matches canonical EA-4E.21 identity."""

    def test_executor_id_matches_canonical(self):
        """Real OpenCode executor must report the canonical identity."""
        identity = RealOpenCodeProductionExecutor.executor_id.fget(SimpleNamespace())
        assert identity == "RealOpenCodeProductionExecutor"

    def test_canonical_identity_matches_contract(self):
        """EA-4E.21 canonical identity must match the real executor."""
        canonical = QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"]["executor_identity"]
        identity = RealOpenCodeProductionExecutor.executor_id.fget(SimpleNamespace())
        assert identity == canonical

    def test_no_identity_masking_wrapper(self):
        """No wrapper may relabel the executor identity."""
        identity = RealOpenCodeProductionExecutor.executor_id.fget(SimpleNamespace())
        # The executor_id must be the canonical one, not a masked version
        assert identity == "RealOpenCodeProductionExecutor"
        assert identity != "real-opencode-production-executor"

    def test_last_outcome_property_exists(self):
        """Executor must expose last_outcome for forensic accounting."""
        state = SimpleNamespace(_last_outcome=None)
        assert RealOpenCodeProductionExecutor.last_outcome.fget(state) is None


class TestLiveClock:
    """Verify live clock behavior."""

    def test_live_clock_returns_current_time(self):
        """Live clock must return actual runtime time."""
        clock = LiveClock()
        now = clock.now_iso()
        assert now is not None
        assert "2026" in now  # Should be current year

    def test_fixed_clock_returns_fixed_time(self):
        """Fixed clock must return the fixed qualification time."""
        clock = LiveClock(fixed="2026-01-01T00:00:00Z")
        assert clock.now_iso() == "2026-01-01T00:00:00Z"

    def test_live_clock_plus_seconds(self):
        """Live clock must compute expiry correctly."""
        clock = LiveClock()
        now = clock.now_iso()
        expires = clock.now_plus_seconds(300)
        assert expires > now

    def test_fixed_clock_plus_seconds(self):
        """Fixed clock must compute expiry from fixed time."""
        clock = LiveClock(fixed="2026-01-01T00:00:00Z")
        expires = clock.now_plus_seconds(300)
        assert expires == "2026-01-01T00:05:00+00:00"


class TestOpenCodeQualificationResult:
    """Verify result dataclass defaults."""

    def test_default_values(self):
        """Result must have safe defaults."""
        result = OpenCodeInvocationAuthorizedLiveResult()
        assert result.live_result == "NOT_RUN"
        assert result.ea4e25_disposition == "HOLD"
        assert result.router_bypassed is True
        assert result.issuance_bypassed is True
        assert result.authority_validation_bypassed is True
        assert result.activation_validation_bypassed is True
        assert result.ea4e21_binding_controller_bypassed is True
        assert result.ea4e22_resolver_bypassed is True
        assert result.ea4e23_invocation_authorization_bypassed is True
        assert result.ea4e23_atomic_claim_bypassed is True
        assert result.production_execution_boundary_bypassed is True
        assert result.opencode_adapter_bypassed is True

    def test_zero_live_accounting(self):
        """Result must start with zero live accounting."""
        result = OpenCodeInvocationAuthorizedLiveResult()
        assert result.new_opencode_tasks == 0
        assert result.new_kilo_tasks == 0
        assert result.new_model_invoke_attempts == 0
        assert result.new_receiver_processes == 0
        assert result.real_opencode_executor_calls == 0
        assert result.real_kilo_executor_calls == 0


class TestOpenCodeQualificationNonLive:
    """Non-live tests for the OpenCode qualification harness."""

    def test_expected_output_constant(self):
        """Expected output must match the authorized task."""
        assert EXPECTED_LIVE_OUTPUT == "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_regression_mode_is_explicitly_fake_only(self):
        assert NONLIVE_REGRESSION_MODE == "FAKE_ONLY"

    def test_qualified_receivers_has_opencode(self):
        """OpenCode must be in qualified receivers."""
        assert "opencode-cli-agent" in QUALIFIED_RECEIVERS
        oc = QUALIFIED_RECEIVERS["opencode-cli-agent"]
        assert oc["transport_contract_id"] == "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f"
        assert oc["model_binding_id"] == "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371"

    def test_qualified_executors_has_opencode(self):
        """OpenCode must be in qualified executors."""
        assert "opencode-cli-agent" in QUALIFIED_EXECUTOR_IMPLEMENTATIONS
        oc = QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"]
        assert oc["executor_identity"] == "RealOpenCodeProductionExecutor"

    def test_opencode_transport_contract_unchanged(self):
        """OpenCode transport contract must remain frozen."""
        oc = QUALIFIED_RECEIVERS["opencode-cli-agent"]
        assert oc["transport_contract_id"] == "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f"

    def test_opencode_model_binding_unchanged(self):
        """OpenCode model binding must remain frozen."""
        oc = QUALIFIED_RECEIVERS["opencode-cli-agent"]
        assert oc["model_binding_id"] == "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371"


class TestOpenCodeGovernedFakeQualification:
    """Exercise the complete governance path with a fake terminal executor."""

    def test_governed_qualification_passes_with_fake_executor(self):
        """Governed qualification must pass with the fake terminal executor."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.live_result == "PASS"
        assert result.output_exact_match is True
        assert result.normalized_output == EXPECTED_LIVE_OUTPUT

    def test_fake_qualification_exact_output(self):
        """Fake qualification must produce the exact expected output."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.normalized_output == "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_governance_path_not_bypassed(self):
        """All governance components must be exercised (not bypassed)."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.router_bypassed is False
        assert result.issuance_bypassed is False
        assert result.authority_validation_bypassed is False
        assert result.activation_validation_bypassed is False
        assert result.ea4e21_binding_controller_bypassed is False
        assert result.ea4e22_resolver_bypassed is False
        assert result.ea4e23_invocation_authorization_bypassed is False
        assert result.ea4e23_atomic_claim_bypassed is False
        assert result.production_execution_boundary_bypassed is False
        assert result.opencode_adapter_bypassed is False

    def test_exactly_one_opencode_boundary_event(self):
        """Exactly one terminal boundary event must be represented."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.opencode_real_executor_call_count == 1
        assert result.real_opencode_executor_calls == 1

    def test_exactly_one_adapter_spy_event(self):
        """Exactly one adapter event must be represented by the fake outcome."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.opencode_adapter_live_call_count == 1
        assert result.real_opencode_adapter_calls == 1

    def test_exactly_one_process_start_spy_event(self):
        """Exactly one process-start event must be represented by the fake outcome."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.opencode_receiver_process_start_count == 1

    def test_exactly_one_model_invocation_spy_event(self):
        """Exactly one model-invocation event must be represented by the spy."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.model_invocation_count == 1

    def test_authorization_consumed(self):
        """Authorization must be consumed after execution."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.live_authorization_consumed is True

    def test_second_claim_rejected(self):
        """Second claim with same authorization must be rejected."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.second_claim_result == "DENY"

    def test_second_claim_no_executor_call(self):
        """Second claim must not call executor."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.second_claim_real_executor_called is False
        assert result.second_claim_opencode_adapter_called is False
        assert result.second_claim_process_started is False
        assert result.second_claim_model_invoked is False

    def test_binding_teardown(self):
        """Binding must be torn down after execution."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.opencode_binding_teardown_attempted is True
        assert result.opencode_binding_teardown_result == "SUCCESS"
        assert result.post_teardown_opencode_binding_count == 0

    def test_no_persistent_binding(self):
        """No persistent binding must remain after teardown."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.persistent_opencode_binding_present is False
        assert result.persistent_kilo_binding_present is False

    def test_no_kilo_activity(self):
        """No Kilo activity must occur during OpenCode qualification."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.new_kilo_tasks == 0
        assert result.real_kilo_executor_calls == 0
        assert result.real_kilo_adapter_calls == 0
        assert result.kilo_real_executor_instantiations == 0
        assert result.kilo_real_executor_calls == 0
        assert result.kilo_receiver_processes_started == 0

    def test_exact_boundary_accounting(self):
        """Boundary accounting must match the authorized single attempt."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.new_opencode_tasks == 1
        assert result.new_kilo_tasks == 0
        assert result.new_model_invoke_attempts == 1
        assert result.new_receiver_processes == 1
        assert result.real_opencode_executor_calls == 1
        assert result.real_kilo_executor_calls == 0
        assert result.real_opencode_adapter_calls == 1
        assert result.real_kilo_adapter_calls == 0
        assert result.live_bindings_created == 1
        assert result.live_invocation_authorizations_issued == 1
        assert result.live_invocation_authorization_claims_granted == 1
        assert result.live_dispatch_executions == 1
        assert result.production_execution_boundary_real_executions == 1

    def test_no_retry_no_fallback_no_failover(self):
        """No retry, fallback, or failover must occur."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.automatic_retry_attempts == 0
        assert result.fallback_attempts == 0
        assert result.failover_attempts == 0

    def test_ea4e25_disposition_pass(self):
        """EA-4E.25 disposition must be PASS on success."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.ea4e25_disposition == "PASS"


class TestOpenCodeFakeEventAccounting:
    """Verify accounting from the explicitly injected execution spy."""

    def test_adapter_call_count_from_fake_event(self):
        """Adapter call count must come from the injected outcome record."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        real_executor = getattr(result, "_real_executor", None)
        assert real_executor is not None
        assert real_executor.last_outcome is not None
        # Adapter call count is derived from the fake outcome record.
        assert result.opencode_adapter_live_call_count == 1

    def test_process_start_count_from_fake_event(self):
        """Process start count must come from the injected outcome flag."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        real_executor = getattr(result, "_real_executor", None)
        assert real_executor is not None
        outcome = real_executor.last_outcome
        assert outcome is not None
        assert outcome.process_started is True
        assert result.opencode_receiver_process_start_count == 1

    def test_outcome_record_drives_boundary_counts(self):
        """The fake executor outcome, not an external process, drives counts."""
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        # The accounting must come from actual events, not wrapper guesses
        real_executor = getattr(result, "_real_executor", None)
        assert real_executor is not None
        assert real_executor.last_outcome is not None

    def test_fake_executor_is_the_only_terminal_execution(self, fake_only_opencode_boundary):
        result = run_opencode_invocation_authorized_live_qualification(use_live_clock=False)
        assert result.live_result == "PASS"
        assert fake_only_opencode_boundary["fake_executor_instantiations"] == 1
        assert fake_only_opencode_boundary["fake_executor_calls"] == 1
        assert fake_only_opencode_boundary["real_executor_tripwire"] == 0
        assert fake_only_opencode_boundary["real_adapter_tripwire"] == 0
        assert fake_only_opencode_boundary["process_start_tripwire"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
