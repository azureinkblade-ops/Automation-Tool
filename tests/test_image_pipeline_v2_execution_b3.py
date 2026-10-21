"""CPU-only B3 test matrix for the Image Pipeline V2 live execution boundary.

Proves the fail-closed production execution contract (tools.image_pipeline_v2_execution)
with fakes only: no ComfyUI HTTP, no GPU, no Ollama process. Every external
interaction (ComfyUI client, GPU metrics, Ollama) is injected behind a small
protocol and driven by deterministic fakes.

Test plan mirrors the authoritative remediation contract:
  PREFLIGHT (1-3), OLLAMA (4-8), COMFYUI (9-16), DUPLICATION (17-20),
  CLEANUP (21-30), RESULT (31-35).
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
    EXECUTION_LAYER_AUTO_RETRY_GPU_SUBMISSION,
    GPU_MIN_FREE_VRAM_MIB,
    GPU_MIN_FREE_VRAM_WARM_MIB,
    OLLAMA_FORCE_KILL_AUTOMATIC,
    PREFLIGHT_COLD,
    PREFLIGHT_WARM_RESIDENT,
    V2ComfyUIUnavailable,
    V2DuplicateSubmission,
    V2ExecutionContext,
    V2ExecutionError,
    V2ExecutionRegistry,
    V2ExecutionTimeout,
    V2OllamaContention,
    V2OllamaStuck,
    V2OutputInvalid,
    V2OutputMissing,
    V2ResourceUnavailable,
    V2SubmissionFailure,
    V2WorkflowFailure,
    CleanupResult,
    ComfyUIExecutionClient,
    GpuMetricsProvider,
    OllamaClient,
    execute_v2,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def make_resolution(profile: str = "main_posts", workflow: Optional[Dict[str, Any]] = None,
                    provenance: Optional[Dict[str, Any]] = None) -> SimpleNamespace:
    return SimpleNamespace(
        workflow=workflow if workflow is not None else {"nodes": {"3": {"inputs": {"seed": 1}}}},
        provenance=provenance if provenance is not None else {"pipeline": profile, "spec_sha": "abc"},
    )


class FakeGpu:
    """Injectable GpuMetricsProvider: fixed totals, optional used/free."""

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

    def reset(self) -> None:
        self._freed = False


class FakeOllama:
    """Injectable OllamaClient."""

    def __init__(self, models: Optional[List[Dict[str, Any]]] = None):
        self._models = list(models or [])
        self.stopped: List[str] = []

    def list_models(self) -> List[Dict[str, Any]]:
        return list(self._models)

    def stop_model(self, name: str) -> None:
        self.stopped.append(name)
        # Reflect the stop in the resident list for verification.
        self._models = [m for m in self._models if m.get("name") != name]


class FakeComfy:
    """Injectable ComfyUIExecutionClient (no live HTTP)."""

    def __init__(self, *, endpoint: str = "http://127.0.0.1:8188",
                 free_return: Optional[Dict[str, Any]] = None,
                 on_free: Optional[Any] = None):
        self.endpoint = endpoint
        self.healthy = True
        self.submit_side_effect = None
        self.submit_return = "prompt-123"
        self.wait_side_effect = None
        self.retrieve_return: bytes = PNG_BYTES
        self.retrieve_side_effect = None
        self.free_return: Dict[str, Any] = free_return or {"status_code": 200, "body": {}}
        self.free_side_effect = None
        self.on_free = on_free
        self.submit_calls = 0
        self.free_calls = 0
        self.health_calls = 0
        self.post_health_calls = 0

    def health_check(self) -> bool:
        self.health_calls += 1
        return self.healthy

    def post_cleanup_health_check(self) -> bool:
        self.post_health_calls += 1
        return self.healthy

    def submit_workflow(self, workflow: Dict[str, Any]) -> str:
        self.submit_calls += 1
        if self.submit_side_effect is not None:
            raise self.submit_side_effect
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
# PREFLIGHT
# --------------------------------------------------------------------------- #


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.client = FakeComfy()

    def test_1_sufficient_vram_permits_progression(self):
        gpu = FakeGpu(used_before_mib=1000)  # huge free
        ctx = V2ExecutionContext(required_vram_bytes=1024 * 1024 * 1024)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=gpu, ctx=ctx, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertEqual(self.client.submit_calls, 1)

    def test_2_insufficient_vram_fails_before_submit(self):
        gpu = FakeGpu(total_mib=4096, used_before_mib=4000)  # tiny free
        ctx = V2ExecutionContext(required_vram_bytes=8 * 1024 * 1024 * 1024)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=gpu, ctx=ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIsInstance(res.primary_error, str)
        self.assertIn("V2ResourceUnavailable", res.error_type)
        self.assertEqual(self.client.submit_calls, 0)

    def test_3_gpu_metrics_unavailable_handled_deterministically(self):
        # No metrics supplied: lane performs no GPU work and proceeds (the runtime
        # GPU authority enforces the hard refusal at submit). Deterministic: proceeds.
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=None, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertEqual(self.client.submit_calls, 1)


# --------------------------------------------------------------------------- #
# OLLAMA
# --------------------------------------------------------------------------- #


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.client = FakeComfy()

    def test_4_no_model_permits_progression(self):
        ollama = FakeOllama([])
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, ollama=ollama, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertEqual(ollama.stopped, [])

    def test_5_idle_model_normal_stop_behavior(self):
        ctx = V2ExecutionContext(allow_ollama_idle_cleanup=True)
        ollama = FakeOllama([{"name": "llama3", "status": "idle"}])
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, ollama=ollama, ctx=ctx, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertEqual(ollama.stopped, ["llama3"])

    def test_6_active_model_blocks(self):
        ollama = FakeOllama([{"name": "llama3", "status": "running"}])
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, ollama=ollama, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2OllamaContention", res.error_type)
        self.assertEqual(self.client.submit_calls, 0)
        self.assertEqual(ollama.stopped, [])  # never force-killed

    def test_7_stuck_stopping_state_blocks(self):
        ollama = FakeOllama([{"name": "llama3", "status": "stopping"}])
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, ollama=ollama, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2OllamaStuck", res.error_type)
        self.assertEqual(self.client.submit_calls, 0)

    def no_automatic_force_kill(self):
        pass

    def test_8_no_automatic_force_kill(self):
        # Active/unknown/stuck states must never trigger stop_model (force-kill).
        for status in ("running", "active", "loaded", "weird-unknown"):
            ollama = FakeOllama([{"name": "m", "status": status}])
            execute_v2("main_posts", make_resolution(), self.target,
                       client=FakeComfy(), ollama=ollama, registry=V2ExecutionRegistry())
            self.assertEqual(ollama.stopped, [], f"stop called for status={status}")


# --------------------------------------------------------------------------- #
# COMFYUI
# --------------------------------------------------------------------------- #


class ComfyUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)  # tiny so preflight passes
        self.gpu = FakeGpu(used_before_mib=1000)

    def test_9_health_unavailable_fails_closed(self):
        client = FakeComfy()
        client.submit_side_effect = V2ComfyUIUnavailable("connection refused")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2ComfyUIUnavailable", res.error_type)
        self.assertEqual(client.submit_calls, 1)

    def test_10_submit_http_failure_fails_closed(self):
        client = FakeComfy()
        client.submit_side_effect = V2SubmissionFailure("HTTP 500")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2SubmissionFailure", res.error_type)
        self.assertEqual(client.submit_calls, 1)  # no resubmit

    def test_11_successful_submit_records_prompt_id(self):
        client = FakeComfy()
        client.submit_return = "pid-XYZ"
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.prompt_id, "pid-XYZ")

    def test_12_timeout_fails_closed(self):
        client = FakeComfy()
        client.wait_side_effect = V2ExecutionTimeout("deadline exceeded")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2ExecutionTimeout", res.error_type)
        self.assertEqual(client.free_calls, 1)  # failure-path cleanup

    def test_13_workflow_failure_fails_closed(self):
        client = FakeComfy()
        client.wait_side_effect = V2WorkflowFailure("node error")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2WorkflowFailure", res.error_type)

    def test_14_missing_output_fails_closed(self):
        client = FakeComfy()
        client.retrieve_side_effect = V2OutputMissing("no image")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2OutputMissing", res.error_type)

    def test_15_invalid_output_fails_closed(self):
        client = FakeComfy()
        client.retrieve_return = b"not-a-png"
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2OutputInvalid", res.error_type)

    def test_16_valid_output_succeeds(self):
        client = FakeComfy()
        client.retrieve_return = PNG_BYTES
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "success")
        self.assertTrue(self.target.exists())


# --------------------------------------------------------------------------- #
# DUPLICATION
# --------------------------------------------------------------------------- #


class DuplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=1000)

    def test_17_one_logical_execution_submits_exactly_once(self):
        client = FakeComfy()
        execute_v2("task-1", make_resolution(), self.target,
                   client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                   execution_id="exec-1", registry=self.reg)
        client2 = FakeComfy()
        res2 = execute_v2("task-1", make_resolution(), self.target,
                          client=client2, gpu_metrics=self.gpu, ctx=self.ctx,
                          execution_id="exec-1", registry=self.reg)
        self.assertEqual(client.submit_calls, 1)  # first only
        self.assertEqual(client2.submit_calls, 0)  # blocked
        self.assertTrue(res2.duplicate)
        self.assertEqual(res2.status, "failed")

    def test_18_uncertain_in_flight_state_does_not_resubmit(self):
        client = FakeComfy()
        client.wait_side_effect = V2ExecutionTimeout("uncertain state")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-u", registry=self.reg)
        # submit happened once; no automatic resubmit despite uncertain state.
        self.assertEqual(client.submit_calls, 1)
        self.assertEqual(client.free_calls, 1)
        self.assertEqual(res.status, "failed")
        self.assertFalse(res.duplicate)

    def test_19_execution_identity_stable(self):
        client = FakeComfy()
        res = execute_v2("realistic", make_resolution("realistic"), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="stable-id-99", registry=self.reg)
        self.assertEqual(res.execution_id, "stable-id-99")

    def test_20_prompt_id_preserved(self):
        client = FakeComfy()
        client.submit_return = "preserved-pid"
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-p", registry=self.reg)
        self.assertEqual(res.prompt_id, "preserved-pid")
        self.assertEqual(res.provenance.get("prompt_id"), "preserved-pid")


# --------------------------------------------------------------------------- #
# CLEANUP
# --------------------------------------------------------------------------- #


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)  # release 3000 MiB

    def _run_success(self, *, free_return=None, on_free=None) -> "tuple[FakeComfy, V2ExecutionResult]":
        client = FakeComfy(free_return=free_return, on_free=on_free)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        return client, res

    def test_21_successful_execution_invokes_cleanup_once(self):
        client, res = self._run_success()
        self.assertEqual(client.free_calls, 1)
        self.assertIsInstance(res.cleanup, CleanupResult)

    def test_22_pre_submit_failure_does_not_call_free(self):
        # Insufficient VRAM -> fails before submit -> no /free.
        gpu = FakeGpu(total_mib=4096, used_before_mib=4000)
        ctx = V2ExecutionContext(required_vram_bytes=8 * 1024 * 1024 * 1024)
        client = FakeComfy()
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=gpu, ctx=ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertEqual(client.free_calls, 0)

    def test_23_post_submit_failure_invokes_bounded_cleanup(self):
        client = FakeComfy()
        client.wait_side_effect = V2WorkflowFailure("boom")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertEqual(client.free_calls, 1)
        self.assertIsNotNone(res.cleanup)

    def test_24_free_200_with_release_effective(self):
        client, res = self._run_success(
            free_return={"status_code": 200, "body": {}}, on_free=self.gpu.mark_freed)
        self.assertEqual(res.cleanup.free_http_status, 200)
        self.assertTrue(res.cleanup.cleanup_effective)
        self.assertFalse(res.cleanup.cleanup_anomaly)

    def test_25_free_500_with_release_effective_and_anomaly(self):
        self.gpu.used_before_mib = 4000
        self.gpu.used_after_mib = 1000
        client, res = self._run_success(
            free_return={"status_code": 500, "error": "internal"}, on_free=self.gpu.mark_freed)
        self.assertEqual(res.cleanup.free_http_status, 500)
        self.assertTrue(res.cleanup.cleanup_effective)
        self.assertTrue(res.cleanup.cleanup_anomaly)

    def test_26_free_failure_without_release_is_cleanup_failure(self):
        # No release: post used == pre used.
        self.gpu.used_before_mib = 4000
        self.gpu.used_after_mib = 4000
        client, res = self._run_success(
            free_return={"status_code": 500, "error": "internal"})
        self.assertEqual(res.cleanup.free_http_status, 500)
        self.assertFalse(res.cleanup.cleanup_effective)
        self.assertFalse(res.cleanup.cleanup_anomaly)

    def test_27_post_cleanup_health_checked(self):
        client, res = self._run_success()
        self.assertGreaterEqual(client.post_health_calls, 1)
        self.assertTrue(res.cleanup.comfyui_reachable_post)

    def test_28_primary_error_preserved_when_cleanup_also_fails(self):
        client = FakeComfy()
        client.wait_side_effect = V2ExecutionTimeout("primary timeout")
        client.free_side_effect = RuntimeError("cleanup blew up")
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("timeout", res.primary_error)
        self.assertIsNotNone(res.cleanup)
        self.assertFalse(res.cleanup.cleanup_effective)

    def test_29_no_repeated_free_call(self):
        client, res = self._run_success(on_free=self.gpu.mark_freed)
        self.assertEqual(client.free_calls, 1)
        self.assertEqual(res.cleanup.free_http_status, 200)

    def test_30_cleanup_metrics_recorded(self):
        client, res = self._run_success(on_free=self.gpu.mark_freed)
        self.assertIsNotNone(res.cleanup.pre_cleanup_vram_mib)
        self.assertIsNotNone(res.cleanup.post_cleanup_vram_mib)
        self.assertIsNotNone(res.cleanup.vram_released_mib)
        self.assertGreater(res.cleanup.vram_released_mib, 0)


# --------------------------------------------------------------------------- #
# RESULT / PROVENANCE
# --------------------------------------------------------------------------- #


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)
        self.gpu = FakeGpu(used_before_mib=4000, used_after_mib=1000)

    def test_31_pipeline_provenance_preserved(self):
        prov = {"pipeline": "main_posts", "spec_sha": "deadbeef", "lora": "lora_main_posts"}
        client = FakeComfy()
        res = execute_v2("main_posts", make_resolution(provenance=prov), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-pp", registry=self.reg, provenance=prov)
        self.assertEqual(res.status, "success")
        for k, v in prov.items():
            self.assertEqual(res.provenance.get(k), v)

    def test_32_output_sha_captured(self):
        prov = {"pipeline": "main_posts"}
        client = FakeComfy()
        client.retrieve_return = PNG_BYTES
        res = execute_v2("main_posts", make_resolution(provenance=prov), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-sha", registry=self.reg)
        self.assertIsNotNone(res.output_sha256)
        import hashlib
        self.assertEqual(res.output_sha256, hashlib.sha256(PNG_BYTES).hexdigest())

    def test_33_profile_retained(self):
        client = FakeComfy()
        res = execute_v2("realistic", make_resolution("realistic"), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-prof", registry=self.reg)
        self.assertEqual(res.profile, "realistic")

    def test_34_execution_id_retained(self):
        client = FakeComfy()
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-retain-34", registry=self.reg)
        self.assertEqual(res.execution_id, "exec-retain-34")

    def test_35_cleanup_status_retained(self):
        client = FakeComfy(on_free=self.gpu.mark_freed)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=client, gpu_metrics=self.gpu, ctx=self.ctx,
                         execution_id="exec-cln", registry=self.reg)
        self.assertIsNotNone(res.cleanup)
        self.assertTrue(res.cleanup.cleanup_effective)

    def test_policy_constants(self):
        self.assertFalse(EXECUTION_LAYER_AUTO_RETRY_GPU_SUBMISSION)
        self.assertFalse(OLLAMA_FORCE_KILL_AUTOMATIC)
        self.assertEqual(GPU_MIN_FREE_VRAM_MIB, 8192)
        self.assertEqual(GPU_MIN_FREE_VRAM_WARM_MIB, 2048)
        self.assertEqual(PREFLIGHT_COLD, "cold")
        self.assertEqual(PREFLIGHT_WARM_RESIDENT, "warm_resident")


# --------------------------------------------------------------------------- #
# WARM / RESIDENT PREFLIGHT (B3 deferred-task VRAM floor distinction)
# --------------------------------------------------------------------------- #


class WarmPreflightTests(unittest.TestCase):
    """Task-aware warm/resident preflight for follow-up deferred replicas.

    A deferred multi-replica task leaves the SDXL checkpoint + LoRA resident
    between replicas (no /free between replicas). The follow-up replica must not
    be held to the cold-start 8 GiB floor, which already accounts for loading
    the model that is now resident. It is held only to the narrower generation
    working-set headroom floor.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.client = FakeComfy()
        # Device with model already resident: ~6.1 GiB free (below cold 8 GiB
        # floor, above warm 2 GiB floor).
        self.gpu_resident = FakeGpu(total_mib=16376, used_before_mib=10266,
                                     used_after_mib=10266)

    def test_cold_floor_blocks_when_model_resident(self):
        cold_ctx = V2ExecutionContext(required_vram_bytes=8 * 1024 * 1024 * 1024)
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=self.gpu_resident,
                         ctx=cold_ctx, registry=self.reg)
        self.assertEqual(res.status, "failed")
        self.assertIn("V2ResourceUnavailable", res.error_type)
        self.assertEqual(self.client.submit_calls, 0)

    def test_warm_resident_floor_passes_when_cold_would_fail(self):
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=self.gpu_resident,
                         registry=V2ExecutionRegistry(),
                         preflight=PREFLIGHT_WARM_RESIDENT)
        self.assertEqual(res.status, "success")
        self.assertEqual(self.client.submit_calls, 1)

    def test_default_preflight_is_cold(self):
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=self.gpu_resident,
                         registry=self.reg)
        self.assertEqual(res.status, "failed")

    def test_invalid_preflight_rejected(self):
        with self.assertRaises(ValueError):
            execute_v2("main_posts", make_resolution(), self.target,
                       client=self.client, registry=self.reg,
                       preflight="bogus")

    def test_warm_records_resident_required_bytes(self):
        res = execute_v2("main_posts", make_resolution(), self.target,
                         client=self.client, gpu_metrics=self.gpu_resident,
                         registry=V2ExecutionRegistry(),
                         preflight=PREFLIGHT_WARM_RESIDENT)
        self.assertEqual(res.gpu_preflight["required_bytes"],
                         GPU_MIN_FREE_VRAM_WARM_MIB * 1024 * 1024)


if __name__ == "__main__":
    unittest.main(verbosity=2)
