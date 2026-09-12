"""EA-4D.4E dispatcher mechanics: gate, dispatch, pass-through, error propagation.

The 4E dispatcher's contract is about the GATE and PASS-THROUGH behavior, not
about 4A/4B/4C semantics (those are tested separately). So these tests use a
fake 4D orchestrator to exercise the dispatcher in isolation.

Proves:
* disabled -> ExecutionPostLaunchDispatchDisabledError, 4D invoked 0 times
* enabled -> exactly one 4D call, same launch_attempt_id, same result
* status pass-through for STARTED_PROJECTED / STARTED_NOT_PROJECTED / FAILED_RECORDED
* typed error propagation (PostLaunchExecutionError, 4A, 4B conflict/integrity/ineligible)
* ZERO automatic retry (one dispatch -> at most one run_post_launch; no second call on error)
* input launch_attempt_id forwarded unchanged; not created/derived/mutated
"""

import unittest

from tools.hermes_core.execution_authorization import (
    ExecutionStateProjectionConflictError,
    ExecutionStateProjectionIntegrityError,
    ExecutionStateProjectionIneligibleError,
)
from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionError,
    PostLaunchExecutionResult,
    PostLaunchStatus,
)
from tools.hermes_core.execution_post_launch_dispatcher import (
    ExecutionPostLaunchDispatchDisabledError,
    ExecutionPostLaunchDispatcher,
)


class FakeOrch:
    """Records run_post_launch calls and returns a scripted result/error."""

    def __init__(self, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def run_post_launch(self, launch_attempt_id):
        self.calls.append(launch_attempt_id)
        if self._error is not None:
            raise self._error
        return self._result


def _started_result():
    return PostLaunchExecutionResult(
        launch_attempt_id="l1",
        start_result=None,
        projection=None,
        status=PostLaunchStatus.STARTED_PROJECTED,
    )


def _not_projected_result():
    return PostLaunchExecutionResult(
        launch_attempt_id="l1",
        start_result=None,
        projection=None,
        status=PostLaunchStatus.STARTED_NOT_PROJECTED,
    )


def _failed_result():
    return PostLaunchExecutionResult(
        launch_attempt_id="l1",
        start_result=None,
        projection=None,
        status=PostLaunchStatus.FAILED_RECORDED,
    )


class TestDisabledGate(unittest.TestCase):
    def test_disabled_raises_and_does_not_invoke_4d(self):
        orch = FakeOrch(result=_started_result())
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=False)

        with self.assertRaises(ExecutionPostLaunchDispatchDisabledError):
            disp.dispatch_post_launch("l1")

        self.assertEqual(len(orch.calls), 0)

    def test_disabled_does_not_touch_4d_even_with_error_result(self):
        orch = FakeOrch(error=PostLaunchExecutionError("boom"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=False)

        with self.assertRaises(ExecutionPostLaunchDispatchDisabledError):
            disp.dispatch_post_launch("l1")

        self.assertEqual(len(orch.calls), 0)


class TestEnabledDispatch(unittest.TestCase):
    def test_enabled_forwards_same_id_and_result(self):
        orch = FakeOrch(result=_started_result())
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        result = disp.dispatch_post_launch("l1")

        self.assertEqual(len(orch.calls), 1)
        self.assertEqual(orch.calls[0], "l1")
        self.assertEqual(result.status, PostLaunchStatus.STARTED_PROJECTED)

    def test_enabled_forwards_id_unchanged(self):
        orch = FakeOrch(result=_started_result())
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        disp.dispatch_post_launch("attempt-abc-123")

        self.assertEqual(orch.calls[0], "attempt-abc-123")


class TestStatusPassThrough(unittest.TestCase):
    def test_started_not_projected(self):
        orch = FakeOrch(result=_not_projected_result())
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        result = disp.dispatch_post_launch("l1")

        self.assertEqual(result.status, PostLaunchStatus.STARTED_NOT_PROJECTED)

    def test_failed_recorded(self):
        orch = FakeOrch(result=_failed_result())
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        result = disp.dispatch_post_launch("l1")

        self.assertEqual(result.status, PostLaunchStatus.FAILED_RECORDED)


class TestTypedErrorPropagation(unittest.TestCase):
    def test_post_launch_execution_error_propagates(self):
        orch = FakeOrch(error=PostLaunchExecutionError("non-definitive"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        with self.assertRaises(PostLaunchExecutionError):
            disp.dispatch_post_launch("l1")

    def test_4a_typed_error_propagates(self):
        from tools.hermes_core.execution_start_result_service import (
            ExecutionStartResultError,
        )
        orch = FakeOrch(error=ExecutionStartResultError("unknown attempt"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        with self.assertRaises(ExecutionStartResultError):
            disp.dispatch_post_launch("l1")

    def test_4b_conflict_propagates(self):
        orch = FakeOrch(error=ExecutionStateProjectionConflictError("conflict"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        with self.assertRaises(ExecutionStateProjectionConflictError):
            disp.dispatch_post_launch("l1")

    def test_4b_integrity_propagates(self):
        orch = FakeOrch(error=ExecutionStateProjectionIntegrityError("integrity"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        with self.assertRaises(ExecutionStateProjectionIntegrityError):
            disp.dispatch_post_launch("l1")

    def test_4b_ineligible_propagates(self):
        orch = FakeOrch(error=ExecutionStateProjectionIneligibleError("ineligible"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        with self.assertRaises(ExecutionStateProjectionIneligibleError):
            disp.dispatch_post_launch("l1")


class TestZeroRetry(unittest.TestCase):
    def test_one_dispatch_at_most_one_4d_call(self):
        orch = FakeOrch(error=PostLaunchExecutionError("non-definitive"))
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        with self.assertRaises(PostLaunchExecutionError):
            disp.dispatch_post_launch("l1")

        # Exactly one downstream 4D call; zero automatic retry.
        self.assertEqual(len(orch.calls), 1)

    def test_success_one_call(self):
        orch = FakeOrch(result=_started_result())
        disp = ExecutionPostLaunchDispatcher(post_launch_orchestrator=orch, enabled=True)

        disp.dispatch_post_launch("l1")

        self.assertEqual(len(orch.calls), 1)


class TestNegativeCapability(unittest.TestCase):
    def test_no_runtime_deps(self):
        with open(
            "tools/hermes_core/execution_post_launch_dispatcher.py", encoding="utf-8"
        ) as f:
            src = f.read()
        for token in (
            "RuntimeLaunchAdapter", "RuntimeStartLookup", "subprocess",
            "Popen", "requests", "httpx", "socket", "ssh", "docker",
            "ollama", "os.environ", "configparser",
        ):
            self.assertNotIn(token, src, f"4E must not depend on {token}")


if __name__ == "__main__":
    unittest.main()
