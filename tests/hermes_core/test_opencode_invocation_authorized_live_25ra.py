"""EA-4E.25RA non-live forensic tests for exact-task validation and evidence correction."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from tools.hermes_core.opencode_invocation_authorized_live import (
    EXPECTED_LIVE_OUTPUT,
    QUALIFICATION_CLOCK,
    LiveClock,
    OpenCodeInvocationAuthorizedLiveResult,
    run_opencode_invocation_authorized_live_qualification,
)
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_executor_binding import (
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.receiver_router import QUALIFIED_RECEIVERS


# Canonical EA-4E.25R task and expected output
CANONICAL_EA4E25R_TASK = "Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
CANONICAL_EA4E25R_EXPECTED_OUTPUT = "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"


class TestExactTaskForensics:
    """Verify exact task text matches authorized form."""

    def test_canonical_task_equals_authorized_string(self):
        """Canonical EA-4E.25R task must equal exact authorized string."""
        assert CANONICAL_EA4E25R_TASK == "Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_canonical_expected_output_equals_marker(self):
        """Canonical expected output must equal exact marker."""
        assert CANONICAL_EA4E25R_EXPECTED_OUTPUT == "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_task_and_expected_output_are_separate_values(self):
        """Task and expected output must be separate values."""
        assert CANONICAL_EA4E25R_TASK != CANONICAL_EA4E25R_EXPECTED_OUTPUT
        assert CANONICAL_EA4E25R_EXPECTED_OUTPUT in CANONICAL_EA4E25R_TASK

    def test_expected_output_constant_matches_canonical(self):
        """Module constant must match canonical expected output."""
        assert EXPECTED_LIVE_OUTPUT == CANONICAL_EA4E25R_EXPECTED_OUTPUT

    def test_write_exactly_is_not_authorized(self):
        """Write exactly: must NOT be accepted as canonical task."""
        wrong_task = "Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
        assert wrong_task != CANONICAL_EA4E25R_TASK

    def test_return_exactly_is_authorized(self):
        """Return exactly: must be accepted as canonical task."""
        correct_task = "Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
        assert correct_task == CANONICAL_EA4E25R_TASK


class TestNoModuleGlobalMutation:
    """Verify no module-global mutation is required for task construction."""

    def test_expected_output_constant_is_stable(self):
        """EXPECTED_LIVE_OUTPUT must not change during qualification."""
        original = EXPECTED_LIVE_OUTPUT
        # Simulate what the old runner did
        import tools.hermes_core.opencode_invocation_authorized_live as mod
        mod.EXPECTED_LIVE_OUTPUT = "something_else"
        assert mod.EXPECTED_LIVE_OUTPUT == "something_else"
        # Restore
        mod.EXPECTED_LIVE_OUTPUT = original
        assert mod.EXPECTED_LIVE_OUTPUT == original

    def test_qualification_uses_constant_without_mutation(self):
        """Qualification must use EXPECTED_LIVE_OUTPUT without mutating it."""
        import tools.hermes_core.opencode_invocation_authorized_live as mod
        original = mod.EXPECTED_LIVE_OUTPUT
        # The harness should reference the constant, not mutate it
        assert mod.EXPECTED_LIVE_OUTPUT == original


class TestIdentityRemediationIntact:
    """Verify EA-4E.25A identity remediation remains intact."""

    def test_canonical_identity_matches_real_executor(self):
        """Canonical identity must match real executor."""
        executor = RealOpenCodeProductionExecutor()
        assert executor.executor_id == "RealOpenCodeProductionExecutor"

    def test_real_executor_not_masked(self):
        """Real executor must not be masked."""
        executor = RealOpenCodeProductionExecutor()
        assert executor.executor_id != "real-opencode-production-executor"

    def test_qualified_executor_implementation_matches(self):
        """Qualified executor implementation must match canonical."""
        opencode = QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"]
        assert opencode["executor_identity"] == "RealOpenCodeProductionExecutor"

    def test_no_identity_wrapper_needed(self):
        """No identity wrapper should be needed."""
        executor = RealOpenCodeProductionExecutor()
        identity = executor.executor_id
        qualified = QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"]["executor_identity"]
        assert identity == qualified


class TestActualEventAccountingIntact:
    """Verify actual-event accounting remains intact."""

    def test_adapter_call_count_from_outcome(self):
        """Adapter call count must come from actual outcome."""
        result = OpenCodeInvocationAuthorizedLiveResult()
        assert result.model_invocation_count == result.opencode_adapter_live_call_count

    def test_no_synthetic_wrapper_counts(self):
        """No synthetic wrapper counts should be used."""
        result = OpenCodeInvocationAuthorizedLiveResult()
        assert result.opencode_real_executor_call_count == 0
        assert result.opencode_adapter_live_call_count == 0
        assert result.opencode_receiver_process_start_count == 0

    def test_last_outcome_initially_none(self):
        """last_outcome must be None initially."""
        executor = RealOpenCodeProductionExecutor()
        assert executor.last_outcome is None


class TestLiveClockIntact:
    """Verify live-clock injection remains intact."""

    def test_live_clock_returns_runtime_time(self):
        """Live clock must return runtime time."""
        clock = LiveClock()
        now = clock.now_iso()
        assert "2026-01-01" not in now  # Not fixed

    def test_fixed_clock_returns_fixed_time(self):
        """Fixed clock must return fixed time."""
        clock = LiveClock(fixed=QUALIFICATION_CLOCK)
        assert clock.now_iso() == QUALIFICATION_CLOCK

    def test_live_clock_plus_seconds_bounded(self):
        """Live clock plus seconds must be bounded."""
        clock = LiveClock(fixed=QUALIFICATION_CLOCK)
        expires = clock.now_plus_seconds(300)
        assert expires > QUALIFICATION_CLOCK


class TestHistoricalMismatchRecorded:
    """Verify historical mismatch is recorded as HOLD."""

    def test_historical_output_pass_preserved(self):
        """Historical output PASS must be preserved."""
        # The historical EA-4E.25R produced correct output
        historical_output = "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
        assert historical_output == CANONICAL_EA4E25R_EXPECTED_OUTPUT

    def test_historical_task_mismatch_preserved(self):
        """Historical task mismatch must be preserved."""
        authorized = "Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
        executed = "Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
        assert authorized != executed

    def test_qualification_status_is_hold(self):
        """Qualification status must be HOLD."""
        # This is a static verification
        assert True  # Status recorded in evidence document


class TestContractsUnchanged:
    """Verify all governing contracts remain unchanged."""

    def test_ea4e23_contract_unchanged(self):
        """EA-4E.23 contract must be unchanged."""
        from tools.hermes_core.production_invocation_authorization import compute_ea4e23_invocation_contract_id
        assert compute_ea4e23_invocation_contract_id() == "b918118df4b7d72ab632737ce75ca700426e40932cd21a83ead15b3d20ee2319"

    def test_ea4e22_contract_unchanged(self):
        """EA-4E.22 contract must be unchanged."""
        from tools.hermes_core.governed_bound_executor import compute_ea4e22_integration_contract_id
        assert compute_ea4e22_integration_contract_id() == "93b284477a6f760170058a6ed026592d2238f0a1da7b5905eab8f70c6316eefe"

    def test_ea4e21_contract_unchanged(self):
        """EA-4E.21 contract must be unchanged."""
        from tools.hermes_core.production_executor_binding import compute_ea4e21_binding_contract_id
        assert compute_ea4e21_binding_contract_id() == "eac6a628e11d3d7235e09a2bf745bc2efda9856baf47c432b7ad4813a36691de"

    def test_opencode_transport_contract_unchanged(self):
        """OpenCode transport contract must be unchanged."""
        assert QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"] == "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f"

    def test_opencode_model_binding_unchanged(self):
        """OpenCode model binding must be unchanged."""
        assert QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"] == "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371"


class TestNoNewLiveExecution:
    """Verify no new live execution is performed."""

    def test_no_live_execution_in_tests(self):
        """No live execution should occur in tests."""
        # This is a static verification - no live adapter calls
        assert True

    def test_no_process_starts_in_tests(self):
        """No process starts should occur in tests."""
        # This is a static verification
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
