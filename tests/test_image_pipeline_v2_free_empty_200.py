"""CPU-only remediation tests for the real B3 HTTP client empty-body /free fix.

Proves the confirmed production-path qualification blocker is closed without
weakening JSON validation on endpoints that require JSON. Exercises the REAL
``HttpComfyUIExecutionClient`` through a mocked ``urllib.request.urlopen`` so
no live ComfyUI request is ever issued.

Firewall (must remain true):
  GPU_EXECUTION_AUTHORIZED=NO
  NEW_GPU_GENERATIONS=0
  LIVE_COMFYUI_REQUESTS=0

These tests make ZERO live HTTP calls (urllib.request.urlopen is patched).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from tools.image_pipeline_v2_execution import (  # noqa: E402
    EXECUTE_V2_DEFAULT_AUTO_CLEANUP,
    CLEANUP_MODE_AUTO,
    CLEANUP_MODE_DEFERRED,
    V2ExecutionContext,
    V2ExecutionRegistry,
    V2SubmissionFailure,
    HttpComfyUIExecutionClient,
    CleanupResult,
    execute_v2,
    finalize_v2_task_cleanup,
)


# --------------------------------------------------------------------------- #
# In-memory HTTP transport double (replaces urllib.request.urlopen)
# --------------------------------------------------------------------------- #


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class FakeComfyTransport:
    """urlopen replacement routing by request path suffix.

    routes: {path_suffix: (status, body_bytes)}
    Raises urllib.error.HTTPError for any status >= 400, mirroring real urllib.
    """

    def __init__(self, routes: Dict[str, Tuple[int, bytes]]):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        self.calls.append(url)
        route_key = None
        for key in self.routes:
            if key in url:
                route_key = key
                break
        if route_key is None:
            # Default: treat unknown paths as a 200 empty success.
            status, body = 200, b""
        else:
            status, body = self.routes[route_key]
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "simulated error", {}, None)
        return _FakeHTTPResponse(status, body)


class ReleaseGpu:
    """GPU metrics that report high VRAM before cleanup and low after.

    The execution layer reads vram_used_bytes() once before (via finalize's
    vram_before) and once after cleanup, so the second read simulates the
    release observed after /free.
    """

    def __init__(self, pre_mib: int = 4000, post_mib: int = 1000):
        self.pre_mib = pre_mib
        self.post_mib = post_mib
        self.reads = 0

    def vram_total_bytes(self) -> int:
        return 24564 * 1024 * 1024

    def vram_used_bytes(self) -> int:
        self.reads += 1
        used = self.pre_mib if self.reads <= 1 else self.post_mib
        return used * 1024 * 1024

    def vram_free_bytes(self) -> int:
        return self.vram_total_bytes() - self.vram_used_bytes()


# --------------------------------------------------------------------------- #
# Real-client response-case matrix (section 11 + 12 + 13)
# --------------------------------------------------------------------------- #


class RealClientFreeResponseTests(unittest.TestCase):
    def setUp(self):
        self.client = HttpComfyUIExecutionClient()

    def _free(self, status: int, body: bytes) -> Dict[str, Any]:
        transport = FakeComfyTransport({"/free": (status, body)})
        with mock.patch("urllib.request.urlopen", transport):
            return self.client.free_models()

    def test_case1_free_200_empty_body_accepted(self):
        resp = self._free(200, b"")
        self.assertEqual(resp["status_code"], 200)
        self.assertIsNone(resp["body"])  # truthful: no fabricated payload
        self.assertNotIn("error", resp)

    def test_case2_free_200_whitespace_body_accepted(self):
        resp = self._free(200, b"   ")
        self.assertEqual(resp["status_code"], 200)
        self.assertIsNone(resp["body"])

    def test_case3_free_200_valid_json_preserved(self):
        resp = self._free(200, b'{"ok": true}')
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["body"], {"ok": True})

    def test_case4_free_204_empty_body_accepted(self):
        resp = self._free(204, b"")
        self.assertEqual(resp["status_code"], 204)
        self.assertIsNone(resp["body"])

    def test_case5_free_500_empty_body_failure(self):
        resp = self._free(500, b"")
        self.assertEqual(resp["status_code"], 500)
        self.assertIn("error", resp)

    def test_case6_free_500_json_body_failure(self):
        resp = self._free(500, b'{"error": "boom"}')
        self.assertEqual(resp["status_code"], 500)
        self.assertIn("error", resp)

    def test_case8_free_200_malformed_nonempty_rejected(self):
        # Allow-empty does NOT permit malformed non-empty JSON; must reject.
        resp = self._free(200, b"not json at all")
        self.assertEqual(resp["status_code"], 500)
        self.assertIn("error", resp)


class RealClientStrictEndpointTests(unittest.TestCase):
    """Endpoints that require JSON must remain strict (section 10 + 11 CASE 7)."""

    def _submit(self, status: int, body: bytes):
        transport = FakeComfyTransport({"/prompt": (status, body)})
        with mock.patch("urllib.request.urlopen", transport):
            return HttpComfyUIExecutionClient().submit_workflow({"prompt": {"a": 1}})

    def test_strict_endpoint_rejects_empty_body(self):
        with self.assertRaises(V2SubmissionFailure):
            self._submit(200, b"")

    def test_strict_endpoint_rejects_malformed_json(self):
        with self.assertRaises(V2SubmissionFailure):
            self._submit(200, b"not json")

    def test_strict_endpoint_preserves_valid_json(self):
        pid = self._submit(200, b'{"prompt_id": "abc-123"}')
        self.assertEqual(pid, "abc-123")


# --------------------------------------------------------------------------- #
# finalize_v2_task_cleanup reaches post-verification on empty-body 200
# (section 14)
# --------------------------------------------------------------------------- #


class RealClientFinalizeCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.ctx = V2ExecutionContext(required_vram_bytes=1)

    def _finalize(self, free_body: bytes, *, free_status: int = 200,
                  system_stats_body: bytes = b"{}", gpu=None):
        routes = {
            "/free": (free_status, free_body),
            "/system_stats": (200, system_stats_body),
        }
        transport = FakeComfyTransport(routes)
        with mock.patch("urllib.request.urlopen", transport):
            client = HttpComfyUIExecutionClient()
            cleanup = finalize_v2_task_cleanup(client, gpu or ReleaseGpu(), None, self.ctx)
            free_calls = sum(1 for c in transport.calls if c.rstrip("/").endswith("/free"))
        return client, cleanup, free_calls

    def test_cleanup_attempted_on_empty_200(self):
        client, cleanup, free_calls = self._finalize(b"")
        self.assertEqual(cleanup.free_http_status, 200)
        self.assertTrue(cleanup.attempted, "cleanup must report attempted=True")
        self.assertEqual(cleanup.cleanup_status, "completed")
        self.assertEqual(free_calls, 1)

    def test_post_cleanup_verification_reached_not_aborted(self):
        # No JSON crash at /free; verification (health + VRAM) runs to completion.
        client, cleanup, _ = self._finalize(b"")
        self.assertTrue(cleanup.comfyui_reachable_post)
        self.assertIsNotNone(cleanup.post_cleanup_vram_mib)

    def test_simulated_release_produces_cleanup_effective(self):
        client, cleanup, _ = self._finalize(b"")
        self.assertTrue(cleanup.cleanup_effective)
        self.assertFalse(cleanup.cleanup_anomaly)

    def test_no_release_represented_truthfully(self):
        # GPU reports NO release: effective must be False, no fabrication.
        no_release = ReleaseGpu(pre_mib=4000, post_mib=4000)
        client, cleanup, _ = self._finalize(b"", gpu=no_release)
        self.assertEqual(cleanup.free_http_status, 200)
        self.assertFalse(cleanup.cleanup_effective)
        self.assertFalse(cleanup.cleanup_anomaly)
        self.assertEqual(cleanup.cleanup_status, "failed")

    def test_http_500_with_release_retains_anomaly(self):
        client, cleanup, _ = self._finalize(b"", free_status=500)
        self.assertEqual(cleanup.free_http_status, 500)
        self.assertTrue(cleanup.cleanup_effective)
        self.assertTrue(cleanup.cleanup_anomaly)

    def test_exactly_one_free_call(self):
        _, _, free_calls = self._finalize(b"")
        self.assertEqual(free_calls, 1)


# --------------------------------------------------------------------------- #
# Task-scoped cleanup contract preserved (section 15)
# --------------------------------------------------------------------------- #


class RealClientTaskScopedContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.target = self.tmp / "out.png"
        self.reg = V2ExecutionRegistry()
        self.single_client = HttpComfyUIExecutionClient()

    def _run_execute(self, cleanup_mode, *, gpu=None):
        routes = _execute_routes(free_body=b"")
        transport = FakeComfyTransport(routes)
        with mock.patch("urllib.request.urlopen", transport):
            res = execute_v2(
                "main_posts",
                SimpleResolution(),
                self.target,
                client=self.single_client,
                gpu_metrics=gpu or ReleaseGpu(),
                ctx=V2ExecutionContext(required_vram_bytes=1),
                registry=self.reg,
                cleanup_mode=cleanup_mode,
            )
            free_calls = sum(1 for c in transport.calls if c.rstrip("/").endswith("/free"))
        return res, free_calls

    def test_default_auto_cleanup_still_works(self):
        self.assertTrue(EXECUTE_V2_DEFAULT_AUTO_CLEANUP)
        res, free_calls = self._run_execute(CLEANUP_MODE_AUTO)
        self.assertEqual(res.status, "success")
        self.assertEqual(free_calls, 1)
        self.assertEqual(res.cleanup.cleanup_status, res.cleanup.cleanup_status)  # present

    def test_deferred_execution_performs_zero_free(self):
        res, free_calls = self._run_execute(CLEANUP_MODE_DEFERRED)
        self.assertEqual(res.status, "success")
        self.assertEqual(free_calls, 0)
        self.assertEqual(res.cleanup.cleanup_status, "deferred")

    def test_task_final_one_free_after_deferred(self):
        # Run a deferred execution, then the single task-final cleanup.
        res, free_calls = self._run_execute(CLEANUP_MODE_DEFERRED)
        self.assertEqual(free_calls, 0)
        routes = {"/free": (200, b""), "/system_stats": (200, b"{}")}
        transport = FakeComfyTransport(routes)
        with mock.patch("urllib.request.urlopen", transport):
            cleanup = finalize_v2_task_cleanup(
                self.single_client, ReleaseGpu(), None, V2ExecutionContext(required_vram_bytes=1))
            final_free_calls = sum(1 for c in transport.calls if c.rstrip("/").endswith("/free"))
        self.assertEqual(final_free_calls, 1)
        self.assertEqual(cleanup.cleanup_status, "completed")


def _execute_routes(*, free_body: bytes = b"", free_status: int = 200) -> Dict[str, Tuple[int, bytes]]:
    """Routes for a full real-client execute_v2 happy path plus /free."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    history = (
        b'{"pid-1": {"status": "success", "outputs": '
        b'{"3": {"images": [{"filename": "o.png", "subfolder": "", "type": "output"}]}}}}'
    )
    return {
        "/prompt": (200, b'{"prompt_id": "pid-1"}'),
        "/history": (200, history),
        "/view": (200, png),
        "/system_stats": (200, b"{}"),
        "/free": (free_status, free_body),
    }


class SimpleResolution:
    workflow = {"nodes": {"3": {"inputs": {"seed": 1}}}}
    provenance = {"pipeline": "main_posts", "spec_sha": "abc"}


if __name__ == "__main__":
    unittest.main(verbosity=2)
