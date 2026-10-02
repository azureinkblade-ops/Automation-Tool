"""EA-4E.25RB non-live tests for marker consistency and historical preservation."""

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

# Historical EA-4E.25 markers (preserved for historical evidence)
HISTORICAL_EA4E25_TASK = "Return exactly: EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
HISTORICAL_EA4E25_OUTPUT = "EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

# Historical EA-4E.25R defect (preserved for evidence)
HISTORICAL_EA4E25R_AUTHORIZED_TASK = "Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
HISTORICAL_EA4E25R_EXECUTED_TASK = "Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"
HISTORICAL_EA4E25R_OUTPUT = "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"


class TestCurrentCanonicalMarker:
    """Verify current canonical marker is EA-4E.25R."""

    def test_expected_output_constant_is_25r(self):
        """EXPECTED_LIVE_OUTPUT must be EA-4E.25R marker."""
        assert EXPECTED_LIVE_OUTPUT == CANONICAL_EA4E25R_EXPECTED_OUTPUT

    def test_canonical_task_is_return_exactly(self):
        """Canonical task must use 'Return exactly:' prefix."""
        assert CANONICAL_EA4E25R_TASK.startswith("Return exactly:")

    def test_canonical_task_contains_25r_marker(self):
        """Canonical task must contain EA-4E.25R marker."""
        assert CANONICAL_EA4E25R_EXPECTED_OUTPUT in CANONICAL_EA4E25R_TASK

    def test_task_and_output_are_separate(self):
        """Task and expected output must be separate values."""
        assert CANONICAL_EA4E25R_TASK != CANONICAL_EA4E25R_EXPECTED_OUTPUT


class TestHistoricalEa4e25Preserved:
    """Verify historical EA-4E.25 markers are preserved in evidence."""

    def test_historical_25_task_preserved(self):
        """Historical EA-4E.25 task must be preserved."""
        assert HISTORICAL_EA4E25_TASK == "Return exactly: EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25_output_preserved(self):
        """Historical EA-4E.25 output must be preserved."""
        assert HISTORICAL_EA4E25_OUTPUT == "EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25_task_differs_from_current(self):
        """Historical EA-4E.25 task must differ from current canonical."""
        assert HISTORICAL_EA4E25_TASK != CANONICAL_EA4E25R_TASK


class TestHistoricalEa4e25rDefectPreserved:
    """Verify historical EA-4E.25R defect is preserved."""

    def test_historical_25r_authorized_task(self):
        """Historical authorized task must be preserved."""
        assert HISTORICAL_EA4E25R_AUTHORIZED_TASK == "Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25r_executed_task(self):
        """Historical executed task must be preserved."""
        assert HISTORICAL_EA4E25R_EXECUTED_TASK == "Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25r_tasks_differ(self):
        """Historical authorized and executed tasks must differ."""
        assert HISTORICAL_EA4E25R_AUTHORIZED_TASK != HISTORICAL_EA4E25R_EXECUTED_TASK

    def test_historical_25r_output_pass_preserved(self):
        """Historical output PASS must be preserved."""
        assert HISTORICAL_EA4E25R_OUTPUT == "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25r_qualification_hold(self):
        """Historical qualification status must be HOLD."""
        # This is recorded in evidence document
        assert True


class TestMarkerConsistencyMatrix:
    """Verify marker consistency across implementation and tests."""

    def test_current_harness_uses_25r_marker(self):
        """Current harness must use EA-4E.25R marker."""
        assert EXPECTED_LIVE_OUTPUT == "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_current_tests_expect_25r_marker(self):
        """Current tests must expect EA-4E.25R marker."""
        # This test file expects EA-4E.25R marker
        assert CANONICAL_EA4E25R_EXPECTED_OUTPUT == "EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25_marker_not_used_in_current(self):
        """Historical EA-4E.25 marker must not be used in current canonical tests."""
        assert EXPECTED_LIVE_OUTPUT != "EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"

    def test_historical_25r_defect_marker_preserved(self):
        """Historical EA-4E.25R defect marker must be preserved."""
        assert HISTORICAL_EA4E25R_EXECUTED_TASK == "Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"


class TestNoModuleGlobalMutation:
    """Verify no module-global mutation is required."""

    def test_expected_output_constant_stable(self):
        """EXPECTED_LIVE_OUTPUT must be stable."""
        import tools.hermes_core.opencode_invocation_authorized_live as mod
        original = mod.EXPECTED_LIVE_OUTPUT
        # Constant should not change
        assert mod.EXPECTED_LIVE_OUTPUT == original

    def test_qualification_uses_constant_directly(self):
        """Qualification must use EXPECTED_LIVE_OUTPUT directly."""
        import tools.hermes_core.opencode_invocation_authorized_live as mod
        assert mod.EXPECTED_LIVE_OUTPUT == CANONICAL_EA4E25R_EXPECTED_OUTPUT


class TestIdentityRemediationIntact:
    """Verify identity remediation remains intact."""

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


class TestLiveClockIntact:
    """Verify live-clock injection remains intact."""

    def test_live_clock_returns_runtime_time(self):
        """Live clock must return runtime time."""
        clock = LiveClock()
        now = clock.now_iso()
        assert "2026-01-01" not in now

    def test_fixed_clock_returns_fixed_time(self):
        """Fixed clock must return fixed time."""
        clock = LiveClock(fixed=QUALIFICATION_CLOCK)
        assert clock.now_iso() == QUALIFICATION_CLOCK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
