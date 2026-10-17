"""CPU-only suite: B3 task-scoped (deferred) cleanup remediation.

Proves the new first-class mechanism that lets a multi-replica logical task
defer real /free until exactly one task-final cleanup, while ordinary single
executions keep automatic per-execution cleanup unchanged.

No GPU, no live ComfyUI. All external interactions are injected fakes.

GPU firewall posture for this lane (must remain true):
  GPU_EXECUTION_AUTHORIZED=NO
  NEW_GPU_GENERATIONS=0
  LIVE_COMFYUI_REQUESTS=0
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.image_pipeline_v2_execution import (  # noqa: E402
    CLEANUP_MODE_AUTO,
    CLEANUP_MODE_DEFERRED,
    CleanupResult,
    V2ExecutionContext,
    V2ExecutionRegistry,
    V2WorkflowFailure,
    execute_v2,
    finalize_v2_task_cleanup,
)
from tools.image_pipeline_v2_provenance import (  # noqa: E402
    build_v2_provenance_record,
    build_v2_failure_record,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def make_resolution(profile: str = "main_posts", workflow: Optional[Dict[str, Any]] = None,
                    provenance: Optional[Dict[str, Any]] = None) -> SimpleNamespace:
    return SimpleNamespace(
        workflow=workflow if workflow is not None else {"nodes": {"3": {"inputs": {"seed": 1}}}},
        provenance=provenance if provenance is not None else {"pipeline": profile, "spec_sha": "abc"},
    )


class FakeGpu:
    def __init__(self, total_mib: int = 24564, used_before_mib: int = 1000, used_after_mib: int = 1000):
        self.total_mib = total_mib
        self.used_before_mib = used_before_mib
        self.used_after_mib = used_after_mib
        self._freed = False

    def vram_total_bytes(self) -> int:
        return self.total_mib * 1024 * 1024

    def vram_used_bytes(self) -> int:
        return (self.used_after_mib if self._freed else self.used_before_mib) * 1024 * 1024

    def vram_free_bytes(self) -> int:
        return self.vram_total_bytes() - self.vram_used_bytes()

    def mark_freed(self) -> None:
        self._freed = True


class FakeOllama:
    def __init__(self, models: Optional[List[Dict[str, Any]]] = None):
        self._models = list(models or [])
        self.stopped: List[str] = []

    def list_models(self) -> List[Dict[str, Any]]:
        return list(self._models)

    def stop_model(self, name: str) -> None:
        self.stopped.append(name)
        self._models = [m for m in self._models if m.get("name") != name]


class FakeComfy:
    def __init__(self, *, endpoint: str = "http://127.0.0.1:8188",
                 free_return: Optional[Dict[str, Any]] = None,
                 on_free: Optional[Any] = None):
        self.endpoint = endpoint
        self.healthy = True
        self.submit_return = "prompt-123"
        self.wait_side_effect = None
        self.retrieve_return: bytes = PNG_BYTES
        self.retrieve_side_effect = None
        self.free_return: Dict[str, Any] = free_return or {"status_code": 200, "body": {}}
        self.free_side_effect = None
        self.on_free = on_free
        self.submit_calls = 0
        self.free_calls = 0
        self.post_health_calls = 0

    def health_check(self) -> bool:
        return self.healthy

    def post_cleanup_health_check(self) -> bool:
        self.post_health_calls += 1
        return self.healthy

    def submit_workflow(self, workflow: Dict[str, Any]) -> str:
        self.submit_calls += 1
        return self.submit_return

    def wait_for_completion(self, prompt_id: str) -> None:
        if self.wait_side_effect is not None:
            raise self.wait_side_effect

    def retrieve_output(self, prompt_id: str) -> bytes:
        if self.retrieve_side_effect is not None:
            raise self.retrieve_side_effect
        return self.retrieve_return

    def free_models(self) -> Dict[str, Any]:
        self.free_calls += 1
        if self.on_free is not None:
            self.on_free()
        if self.free_side_effect is not None:
            raise self.free_side_effect
        return dict(self.free_return)


# --------------------------------------------------------------------------- #
# 1. Default (auto) behavior unchanged
# --------------------------------------------------------------------------- #


class TestDefaultAutoCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)

    def test_1_default_execute_v2_performs_cleanup_once(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertEqual(client.free_calls, 1)
        self.assertEqual(res.cleanup.cleanup_status, "completed")

    def test_2_explicit_auto_mode_equivalent(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_AUTO)
        self.assertEqual(client.free_calls, 1)
        self.assertEqual(res.cleanup.cleanup_status, "completed")

    def test_3_invalid_cleanup_mode_rejected(self):
        with self.assertRaises(ValueError):
            execute_v2("main_posts", make_resolution(), self.target,
                       client=FakeComfy(), ctx=self.ctx, registry=self.reg,
                       cleanup_mode="bogus")


# --------------------------------------------------------------------------- #
# 2-4. Deferred single + between-replicas
# --------------------------------------------------------------------------- #


class TestDeferredExecution(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)

    def test_4_deferred_performs_zero_real_free_calls(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                         execution_id="r1")
        self.assertEqual(res.status, "success")
        self.assertEqual(client.free_calls, 0)

    def test_5_deferred_result_says_cleanup_deferred(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                         execution_id="r1")
        self.assertIsInstance(res.cleanup, CleanupResult)
        self.assertEqual(res.cleanup.cleanup_status, "deferred")
        self.assertFalse(res.cleanup.attempted)
        self.assertIsNone(res.cleanup.free_http_status)

    def test_6_two_deferred_executions_zero_free_between_them(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        r1 = execute_v2("main_posts", make_resolution(), self.target,
                        client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                        registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                        execution_id="r1")
        r2 = execute_v2("main_posts", make_resolution(), self.target,
                        client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                        registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                        execution_id="r2")
        self.assertEqual(r1.status, "success")
        self.assertEqual(r2.status, "success")
        self.assertEqual(client.free_calls, 0, "no /free between replicas")
        self.assertEqual(r1.cleanup.cleanup_status, "deferred")
        self.assertEqual(r2.cleanup.cleanup_status, "deferred")


# --------------------------------------------------------------------------- #
# 5-7. Task-final cleanup (real, exactly once)
# --------------------------------------------------------------------------- #


class TestTaskFinalCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)

    def _two_deferred(self, client: FakeComfy):
        execute_v2("main_posts", make_resolution(), self.target,
                   client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                   registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                   execution_id="r1")
        execute_v2("main_posts", make_resolution(), self.target,
                   client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                   registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                   execution_id="r2")

    def test_7_task_finalization_performs_exactly_one_free(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        self._two_deferred(client)
        self.assertEqual(client.free_calls, 0)
        cleanup = finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertEqual(client.free_calls, 1, "exactly one /free at task final")
        self.assertEqual(cleanup.cleanup_status, "completed")

    def test_8_final_cleanup_performs_post_health_verification(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        self._two_deferred(client)
        cleanup = finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertGreaterEqual(client.post_health_calls, 1)
        self.assertTrue(cleanup.comfyui_reachable_post)

    def test_9_final_cleanup_performs_vram_post_verification(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        self._two_deferred(client)
        cleanup = finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertIsNotNone(cleanup.pre_cleanup_vram_mib)
        self.assertIsNotNone(cleanup.post_cleanup_vram_mib)
        self.assertIsNotNone(cleanup.vram_released_mib)
        self.assertGreater(cleanup.vram_released_mib, 0)

    def test_10_http_200_with_release_handled_normally(self):
        client = FakeComfy(free_return={"status_code": 200, "body": {}},
                           on_free=self.gpu.mark_freed)
        cleanup = finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertEqual(cleanup.free_http_status, 200)
        self.assertTrue(cleanup.cleanup_effective)
        self.assertFalse(cleanup.cleanup_anomaly)

    def test_11_http_500_with_release_effective_and_anomaly(self):
        self.gpu.used_before_mib = 4000
        self.gpu.used_after_mib = 1000
        client = FakeComfy(free_return={"status_code": 500, "error": "internal"},
                           on_free=self.gpu.mark_freed)
        cleanup = finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertEqual(cleanup.free_http_status, 500)
        self.assertTrue(cleanup.cleanup_effective)
        self.assertTrue(cleanup.cleanup_anomaly)
        self.assertEqual(cleanup.cleanup_status, "completed")

    def test_12_failed_cleanup_represented_truthfully(self):
        # HTTP 500 with NO observed VRAM release => cleanup failed.
        self.gpu.used_before_mib = 4000
        self.gpu.used_after_mib = 4000
        client = FakeComfy(free_return={"status_code": 500, "error": "internal"})
        cleanup = finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertEqual(cleanup.free_http_status, 500)
        self.assertFalse(cleanup.cleanup_effective)
        self.assertFalse(cleanup.cleanup_anomaly)
        self.assertEqual(cleanup.cleanup_status, "failed")

    def test_13_finalize_does_not_resubmit_gpu_work(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        self._two_deferred(client)
        submits_before = client.submit_calls
        finalize_v2_task_cleanup(client, self.gpu, None, self.ctx)
        self.assertEqual(client.submit_calls, submits_before, "finalize must not submit GPU work")


# --------------------------------------------------------------------------- #
# 8. Failure semantics
# --------------------------------------------------------------------------- #


class TestDeferredFailureSemantics(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)

    def test_14_second_replica_failure_still_permits_one_task_final_cleanup(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        client.wait_side_effect = None
        r1 = execute_v2("main_posts", make_resolution(), self.target,
                        client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                        registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                        execution_id="r1")
        # Replica 2 fails AFTER submission.
        client2 = FakeComfy(on_free=self.gpu.mark_freed)
        client2.wait_side_effect = V2WorkflowFailure("boom")
        r2 = execute_v2("main_posts", make_resolution(), self.target,
                        client=client2, gpu_metrics=self.gpu, ctx=self.ctx,
                        registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                        execution_id="r2")
        self.assertEqual(r1.status, "success")
        self.assertEqual(r2.status, "failed")
        # No /free from either replica (both deferred).
        self.assertEqual(client.free_calls, 0)
        self.assertEqual(client2.free_calls, 0)
        # Task-final cleanup reachable exactly once.
        cleanup = finalize_v2_task_cleanup(client2, self.gpu, None, self.ctx)
        self.assertEqual(client2.free_calls, 1)
        self.assertEqual(cleanup.cleanup_status, "completed")

    def test_15_primary_execution_failure_survives_cleanup_failure(self):
        # Deferred replica 2 fails (primary error). Task-final cleanup then ALSO
        # fails. The replica's primary error must be preserved and the cleanup
        # failure represented truthfully (not masking the primary error).
        client2 = FakeComfy()
        client2.wait_side_effect = V2WorkflowFailure("primary node error")
        r2 = execute_v2("main_posts", make_resolution(), self.target,
                        client=client2, gpu_metrics=self.gpu, ctx=self.ctx,
                        registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                        execution_id="r2")
        self.assertEqual(r2.status, "failed")
        self.assertIn("primary node error", r2.primary_error)
        self.assertEqual(r2.cleanup.cleanup_status, "deferred")
        # Task-final cleanup fails (HTTP 500, no release).
        self.gpu.used_before_mib = 4000
        self.gpu.used_after_mib = 4000
        fail_client = FakeComfy(free_return={"status_code": 500, "error": "cleanup dead"})
        cleanup = finalize_v2_task_cleanup(fail_client, self.gpu, None, self.ctx)
        self.assertEqual(cleanup.cleanup_status, "failed")
        self.assertFalse(cleanup.cleanup_effective)
        # Primary error of the replica is untouched.
        self.assertIn("primary node error", r2.primary_error)

    def test_16_presubmit_failure_does_not_issue_cleanup(self):
        # Failure before submission must not issue /free even in deferred mode.
        gpu = FakeGpu(total_mib=4096, used_before_mib=4000)
        ctx = V2ExecutionContext(required_vram_bytes=8 * 1024 * 1024 * 1024)
        client = FakeComfy()
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=gpu, ctx=ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED)
        self.assertEqual(res.status, "failed")
        self.assertEqual(client.free_calls, 0)


# --------------------------------------------------------------------------- #
# 9. Provenance truthfulness for deferred cleanup
# --------------------------------------------------------------------------- #


class TestDeferredProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)

    def test_17_deferred_cleanup_status_in_success_record(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                         execution_id="r1")
        rec = build_v2_provenance_record(res)
        self.assertEqual(rec["cleanup_result"]["cleanup_status"], "deferred")
        self.assertIsNone(rec["cleanup_result"]["free_http_status"])

    def test_18_deferred_cleanup_status_in_failure_record(self):
        client = FakeComfy()
        client.wait_side_effect = V2WorkflowFailure("boom")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_DEFERRED,
                         execution_id="r1")
        rec = build_v2_failure_record(res)
        self.assertEqual(rec["cleanup_result"]["cleanup_status"], "deferred")
        self.assertIsNone(rec["cleanup_result"]["free_http_status"])

    def test_19_completed_cleanup_status_distinguished(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         registry=self.reg, cleanup_mode=CLEANUP_MODE_AUTO,
                         execution_id="r1")
        rec = build_v2_provenance_record(res)
        self.assertEqual(rec["cleanup_result"]["cleanup_status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
