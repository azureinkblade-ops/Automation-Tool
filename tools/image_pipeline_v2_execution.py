"""Image Pipeline V2 — live execution boundary (CPU contract; GPU invoked only under a later GPU authority).

This module is the application-owned production execution seam for V2. It accepts an
already *resolved* V2 request (a workflow dict produced by a qualified pipeline via the
router) and performs the production execution contract:

  - GPU/VRAM preflight (fail before submit when insufficient);
  - Ollama contention detection (HOLD active models; never auto force-kill);
  - ComfyUI submission (local endpoint only, 127.0.0.1:8188), fail closed on
    unavailable / HTTP non-2xx / workflow error / timeout / invalid output;
  - output retrieval + validation;
  - duplicate-submission protection (one logical execution submits exactly once);
  - task-final cleanup (Ollama unload if this task owns one, then POST /free + verify);
  - failure-path cleanup (preserving the primary error);
  - post-verification of cleanup effectiveness (HTTP status alone is not sufficient).

No GPU work is performed in THIS remediation lane. Every external interaction
(ComfyUI HTTP, GPU metrics, Ollama) is injected behind a small protocol so the
contract is exercised with fakes. The bundled ``HttpComfyUIExecutionClient`` is the
real runtime client and is intended to be wired under the separate bounded GPU
production-path qualification authority; it is NOT invoked here.

The execution layer MUST NOT decide profile / LoRA / checkpoint / seed / sampler /
scheduler / dimensions / workflow structure. Those remain owned by the qualified V2
pipeline (PIPELINE_AUTHORITY_PRESERVED=YES).

Renderer owner: COMFYUI. Endpoint: http://127.0.0.1:8188. Open Design is NEVER used
as a renderer. No cloud image provider is contacted. V2 enabled + ComfyUI failure
fails closed (no V1 / provider fallback).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# --------------------------------------------------------------------------- #
# Authority constants (read-only record of this lane's firewall posture)
# --------------------------------------------------------------------------- #

COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
RENDERER_OWNER = "COMFYUI"
OPEN_DESIGN_RENDERER = False
COMFYUI_LOCAL_ONLY = True

# Conservative default VRAM floor for a qualified SDXL V2 generation.
# Documented choice (no existing V2-specific authoritative threshold was found):
#   - SDXL fp16 checkpoint (~6.5 GiB resident) + LoRA + KSampler/sampler overhead
#     + ComfyUI host reserve. The lora-training gpu check (tools/lora_training/
#     check_gpu.py) uses 12 GiB but includes optimizer/backprop headroom that does
#     NOT apply to inference. 8 GiB is a deliberately conservative inference floor.
#   - This threshold is FIXED for the lane; it is never re-derived per request.
GPU_MIN_FREE_VRAM_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB
GPU_MIN_FREE_VRAM_MIB = 8192

# Warm / resident preflight floor (task-aware, NOT a weakening of the cold floor).
# Applied to follow-up replicas of the SAME deferred multi-replica task whose
# checkpoint + LoRA are already resident from a prior replica. The expensive
# cold-load risk (model load) is already satisfied, so only the generation
# working-set headroom must be free. This is a distinct, narrower floor used ONLY
# when the model is known-resident; the cold-start floor is never lowered.
GPU_MIN_FREE_VRAM_WARM_MIB = 2048
GPU_MIN_FREE_VRAM_WARM_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

COMFYUI_FAILURE_POLICY = "FAIL_CLOSED"
OLLAMA_FORCE_KILL_AUTOMATIC = False
DUPLICATE_SUBMISSION_PROTECTION = True
UNCERTAIN_INFLIGHT_AUTO_RESUBMIT = False
EXECUTION_LAYER_AUTO_RETRY_GPU_SUBMISSION = False
PIPELINE_AUTHORITY_PRESERVED = True

# Task-scoped cleanup control (default single-execution production behavior is
# unchanged: cleanup_mode="auto" performs cleanup at the end of each execution).
# A higher-level multi-replica task may opt into "deferred" so that individual
# executions do NOT issue /free and exactly one real cleanup is performed by the
# explicit task-final entry point `finalize_v2_task_cleanup`.
CLEANUP_MODE_AUTO = "auto"
CLEANUP_MODE_DEFERRED = "deferred"
EXECUTE_V2_DEFAULT_AUTO_CLEANUP = True

# VRAM preflight mode. "cold" (default) applies the full startup floor and is
# correct for the first model load of a (deferred or new) task. "warm_resident"
# applies the narrower generation-headroom floor and is correct for follow-up
# replicas of a deferred task whose model is already resident (deferred mode
# issues no /free between replicas).
PREFLIGHT_COLD = "cold"
PREFLIGHT_WARM_RESIDENT = "warm_resident"


# --------------------------------------------------------------------------- #
# Errors (fail closed; spec-aligned taxonomy + backward-compatible aliases)
# --------------------------------------------------------------------------- #


class V2ExecutionError(Exception):
    """Base fail-closed execution error."""


class V2ComfyUIUnavailable(V2ExecutionError):
    """ComfyUI cannot be reached (no HTTP submit). (spec: ComfyUIUnavailable)"""


class V2ResourceUnavailable(V2ExecutionError):
    """VRAM/resource preflight failed before any GPU submission. (InsufficientVRAM)"""


class V2OllamaContention(V2ExecutionError):
    """A resident Ollama model is active/unknown and must not be displaced."""


class V2OllamaStuck(V2ExecutionError):
    """An Ollama model is stuck in a non-terminal stop state."""


class V2SubmissionFailure(V2ExecutionError):
    """ComfyUI rejected the submission (HTTP non-2xx / no prompt_id)."""


class V2ExecutionTimeout(V2ExecutionError):
    """ComfyUI generation did not complete within the deadline."""


class V2WorkflowFailure(V2ExecutionError):
    """ComfyUI reported a workflow execution error."""


class V2OutputMissing(V2ExecutionError):
    """No output image was produced for the submitted prompt."""


class V2OutputInvalid(V2ExecutionError):
    """The retrieved output failed validation (empty / wrong format)."""


class V2DuplicateSubmission(V2ExecutionError):
    """The same logical execution identity was already submitted."""


class V2CleanupFailure(V2ExecutionError):
    """Task-final cleanup failed (recorded, primary error preserved)."""


# Spec-aligned aliases (names may differ; hierarchy is preserved).
ComfyUIUnavailable = V2ComfyUIUnavailable
InsufficientVRAM = V2ResourceUnavailable
OllamaContention = V2OllamaContention
SubmissionFailure = V2SubmissionFailure
ExecutionTimeout = V2ExecutionTimeout
WorkflowFailure = V2WorkflowFailure
OutputMissing = V2OutputMissing
OutputInvalid = V2OutputInvalid
CleanupFailure = V2CleanupFailure


# --------------------------------------------------------------------------- #
# Injectable collaborators (protocols)
# --------------------------------------------------------------------------- #


@runtime_checkable
class ComfyUIExecutionClient(Protocol):
    """Out-of-process ComfyUI execution client.

    Implemented by ``HttpComfyUIExecutionClient`` (runtime) or a Fake in tests.
    The execution layer never issues raw HTTP; it talks only to this protocol.
    """

    endpoint: str

    def health_check(self) -> bool:
        """Return True if the backend is reachable (pre-submission sanity)."""
        ...

    def submit_workflow(self, workflow: Dict[str, Any]) -> str:
        """Submit the workflow; return the ComfyUI prompt_id.

        Raises V2ComfyUIUnavailable on connection failure, V2SubmissionFailure on
        HTTP non-2xx / missing prompt_id.
        """
        ...

    def wait_for_completion(self, prompt_id: str) -> None:
        """Block until the prompt completes.

        Raises V2WorkflowFailure on a ComfyUI workflow error, V2ExecutionTimeout
        on deadline exceeded.
        """
        ...

    def retrieve_output(self, prompt_id: str) -> bytes:
        """Return the generated image bytes for the completed prompt.

        Raises V2OutputMissing when no output image is present.
        """
        ...

    def free_models(self) -> Dict[str, Any]:
        """POST /free with {unload_models:true, free_memory:true}.

        Returns a raw response dict: {"status_code": int, "body": ...} (or an
        error-encoded status such as 0 when unreachable). Never raises.
        """
        ...

    def post_cleanup_health_check(self) -> bool:
        """Verify the backend remains reachable after cleanup."""
        ...


@runtime_checkable
class GpuMetricsProvider(Protocol):
    """Provides VRAM accounting for the preflight. Fake in tests."""

    def vram_total_bytes(self) -> int: ...

    def vram_used_bytes(self) -> int: ...

    def vram_free_bytes(self) -> int: ...


@runtime_checkable
class OllamaClient(Protocol):
    """Provides Ollama resident-model accounting. Fake in tests."""

    def list_models(self) -> List[Dict[str, Any]]:
        """Return [{"name":..., "status": "running"|"idle"|"stopping"|...}, ...]."""
        ...

    def stop_model(self, name: str) -> None:
        """Request a normal Ollama stop (NOT a force kill)."""
        ...


# --------------------------------------------------------------------------- #
# Duplicate-submission guard
# --------------------------------------------------------------------------- #


class V2ExecutionRegistry:
    """In-memory registry of submitted logical execution identities.

    Guarantees one logical execution submits to ComfyUI exactly once. A second
    submit with the same stable execution identity is rejected (never
    automatically resubmitted). State is intentionally in-process only; B4 may
    later persist it for cross-process protection.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._submitted: Dict[str, str] = {}  # execution_id -> prompt_id

    def is_submitted(self, execution_id: str) -> bool:
        with self._lock:
            return execution_id in self._submitted

    def prompt_id_for(self, execution_id: str) -> Optional[str]:
        with self._lock:
            return self._submitted.get(execution_id)

    def mark_submitted(self, execution_id: str, prompt_id: str) -> None:
        with self._lock:
            self._submitted[execution_id] = prompt_id

    def reset(self) -> None:
        with self._lock:
            self._submitted.clear()


_DEFAULT_REGISTRY = V2ExecutionRegistry()


# --------------------------------------------------------------------------- #
# Result dataclasses
# --------------------------------------------------------------------------- #


@dataclass
class CleanupResult:
    attempted: bool = False
    free_http_status: Optional[int] = None
    comfyui_reachable_post: bool = False
    pre_cleanup_vram_mib: Optional[int] = None
    post_cleanup_vram_mib: Optional[int] = None
    vram_released_mib: Optional[int] = None
    cleanup_effective: bool = False
    cleanup_anomaly: bool = False
    # Truthful lifecycle status of the cleanup for this execution:
    #   "completed"  -> /free issued + verified effective (or anomaly preserved)
    #   "failed"     -> /free attempted/aborted but not effective
    #   "deferred"   -> cleanup intentionally NOT performed here; owned by the
    #                   task-final entry point; never fabricated as a success
    #   None         -> no cleanup applied (e.g. pre-submission failure)
    cleanup_status: Optional[str] = None
    note: str = ""

    def success(self) -> bool:
        # Effective cleanup requires: /free attempted, backend health verified,
        # and (when VRAM metrics are measurable) an observed model allocation
        # release. HTTP status alone is never sufficient.
        if not self.attempted:
            return False
        if not self.comfyui_reachable_post:
            return False
        if self.pre_cleanup_vram_mib is not None and self.post_cleanup_vram_mib is not None:
            # Metrics available: effectiveness requires observed release.
            return self.vram_released_mib is not None and self.vram_released_mib > 0
        # No measurable metric available: HTTP + health is sufficient evidence.
        return True


@dataclass
class V2ExecutionResult:
    profile: str
    execution_id: str
    prompt_id: Optional[str]
    output_path: Optional[str]
    output_sha256: Optional[str]
    status: str  # "success" | "failed"
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    gpu_preflight: Dict[str, Any] = field(default_factory=dict)
    ollama_preflight: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    cleanup: Optional[CleanupResult] = None
    primary_error: Optional[str] = None
    error_type: Optional[str] = None
    duplicate: bool = False


# --------------------------------------------------------------------------- #
# Real HTTP client (runtime; not invoked in this remediation lane)
# --------------------------------------------------------------------------- #


class HttpComfyUIExecutionClient:
    """Runtime ComfyUI execution client. Submits to the LOCAL endpoint only.

    Intended to be wired under the separate bounded GPU production-path
    qualification authority. Performs no GPU work itself; it only issues the
    HTTP contract that ComfyUI executes on the GPU host. Never contacts any
    non-local endpoint and never falls back to a cloud provider.
    """

    def __init__(self, base_url: str = COMFYUI_ENDPOINT, timeout: int = 120):
        if not base_url.startswith("http://127.0.0.1") and not base_url.startswith("http://localhost"):
            raise ValueError(f"ComfyUI client is local-only; refused endpoint {base_url!r}")
        self.endpoint = base_url.rstrip("/")
        self.timeout = timeout

    def _post(
        self, path: str, payload: Dict[str, Any], *, allow_empty_response: bool = False
    ) -> Any:
        """POST JSON and return (parsed_body, status_code).

        allow_empty_response=False (default, STRICT): every 2xx response must
        carry valid JSON. A non-2xx response raises V2SubmissionFailure (so the
        caller can record the failure truthfully); an empty/whitespace or
        malformed body raises V2SubmissionFailure (JSON parse failure).

        allow_empty_response=True (used by /free): a 2xx response with an
        empty/whitespace-only body is accepted as a successful transport and
        returns (None, status_code). A non-empty malformed body still raises
        V2SubmissionFailure; this flag permits an empty success body, NOT opaque
        or malformed JSON.
        """
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                status = getattr(r, "status", 200)
                raw = r.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # non-2xx
            raise V2SubmissionFailure(f"ComfyUI {path} returned HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:  # connection failure
            raise V2ComfyUIUnavailable(f"ComfyUI unreachable at {self.endpoint}: {exc.reason}") from exc

        # Empty/whitespace body on a 2xx success.
        if not raw.strip():
            if allow_empty_response:
                # Truthful representation: transport succeeded, no payload.
                return None, status
            raise V2SubmissionFailure(
                f"ComfyUI {path} returned HTTP {status} with an empty response body"
            )

        # Non-empty body: must be valid JSON on every endpoint (no endpoint
        # contract permits malformed JSON to be normalized to success).
        try:
            return json.loads(raw), status
        except (ValueError, json.JSONDecodeError) as exc:
            raise V2SubmissionFailure(
                f"ComfyUI {path} returned HTTP {status} with invalid JSON: {exc}"
            ) from exc

    def _get(self, path: str) -> Any:
        try:
            with urllib.request.urlopen(f"{self.endpoint}{path}", timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise V2ComfyUIUnavailable(f"ComfyUI unreachable at {self.endpoint}: {exc.reason}") from exc

    def health_check(self) -> bool:
        try:
            self._get("/system_stats")
            return True
        except Exception:
            return False

    def post_cleanup_health_check(self) -> bool:
        return self.health_check()

    def submit_workflow(self, workflow: Dict[str, Any]) -> str:
        result, _ = self._post("/prompt", {"prompt": workflow})
        if not isinstance(result, dict) or "prompt_id" not in result:
            raise V2SubmissionFailure(f"ComfyUI /prompt did not return prompt_id: {result!r}")
        return str(result["prompt_id"])

    def wait_for_completion(self, prompt_id: str, *, poll_interval: float = 0.5, max_seconds: float = 30.0) -> None:
        deadline = time.time() + max(0.1, max_seconds)
        while time.time() < deadline:
            try:
                history = self._get(f"/history/{prompt_id}")
            except Exception as exc:  # noqa: BLE001
                raise V2ExecutionTimeout(f"history poll failed for {prompt_id}: {exc}") from exc
            entry = history.get(prompt_id) if isinstance(history, dict) else None
            if entry is not None:
                status = entry.get("status")
                if status == "error":
                    raise V2WorkflowFailure(f"ComfyUI workflow error for {prompt_id}")
                if "outputs" in entry:
                    return
            time.sleep(poll_interval)
        raise V2ExecutionTimeout(f"ComfyUI generation timed out for {prompt_id}")

    def retrieve_output(self, prompt_id: str) -> bytes:
        history = self._get(f"/history/{prompt_id}")
        outputs = (history.get(prompt_id, {}).get("outputs", {}) if isinstance(history, dict) else {})
        image_meta: Optional[Dict[str, Any]] = None
        for node_out in outputs.values():
            imgs = (node_out or {}).get("images") or []
            if imgs:
                image_meta = imgs[0]
                break
        if not image_meta:
            raise V2OutputMissing(f"ComfyUI history contained no output image for {prompt_id}")
        url = (
            f"{self.endpoint}/view?filename={urllib.parse.quote(str(image_meta.get('filename')))}"
            f"&subfolder={urllib.parse.quote(str(image_meta.get('subfolder', '')))}"
            f"&type={urllib.parse.quote(str(image_meta.get('type', 'output')))}"
        )
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.URLError as exc:
            raise V2OutputMissing(f"Failed to retrieve generated image for {prompt_id}: {exc.reason}") from exc

    def free_models(self) -> Dict[str, Any]:
        # /free may legitimately respond with an empty/whitespace-only body on a
        # successful HTTP 200. allow_empty_response keeps the transport success
        # truthful (body=None) without fabricating a payload.
        try:
            result, status = self._post(
                "/free", {"unload_models": True, "free_memory": True},
                allow_empty_response=True,
            )
            return {"status_code": int(status), "body": result}
        except V2SubmissionFailure as exc:
            return {"status_code": 500, "error": str(exc)}
        except V2ComfyUIUnavailable as exc:
            return {"status_code": 0, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Execution context
# --------------------------------------------------------------------------- #


@dataclass
class V2ExecutionContext:
    required_vram_bytes: int = GPU_MIN_FREE_VRAM_BYTES
    poll_interval_seconds: float = 0.5
    max_poll_seconds: float = 30.0
    allow_ollama_idle_cleanup: bool = False  # explicit policy opt-in only
    # When the execution owns an Ollama model it loaded, its name is recorded so
    # cleanup can request a normal stop (never a force kill).
    owned_ollama_model: Optional[str] = None


# --------------------------------------------------------------------------- #
# Output validation
# --------------------------------------------------------------------------- #

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def validate_output_image(data: bytes, *, expected_format: str = "png") -> None:
    """Validate the retrieved output. Reuse-friendly single source of truth.

    Raises V2OutputMissing (empty) or V2OutputInvalid (wrong magic). Extend here
    if a more mature PNG/fidelity validator is introduced.
    """
    if not data:
        raise V2OutputMissing("retrieved empty image bytes")
    if expected_format == "png" and not data.startswith(_PNG_MAGIC):
        raise V2OutputInvalid("retrieved output is not a PNG image")


# --------------------------------------------------------------------------- #
# Preflight + Ollama contention
# --------------------------------------------------------------------------- #


def _preflight_vram(
    gpu_metrics: Optional[GpuMetricsProvider],
    required_vram_bytes: int,
) -> Dict[str, Any]:
    """Return VRAM accounting and fail closed before any GPU submission when insufficient.

    When no metrics are supplied the runtime GPU authority is responsible for the
    hard refusal at submit; this lane performs no GPU work and therefore does not
    invent a threshold. ``required_vram_bytes`` is resolved by the caller from the
    preflight mode (cold-start floor vs task-aware warm/resident floor).
    """
    if gpu_metrics is None:
        return {"available": False, "sufficient": True, "reason": "no_metrics_supplied"}
    total = gpu_metrics.vram_total_bytes()
    used = gpu_metrics.vram_used_bytes()
    free = gpu_metrics.vram_free_bytes()
    sufficient = free >= required_vram_bytes
    if not sufficient:
        raise V2ResourceUnavailable(
            f"insufficient VRAM for V2 execution: free={free} required={required_vram_bytes}"
        )
    return {
        "available": True,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "required_bytes": required_vram_bytes,
        "sufficient": True,
    }


def _classify_ollama(models: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify resident Ollama models into the four required states.

    MODEL_RESIDENT_ACTIVE_OR_UNKNOWN is the default for any status that is not
    explicitly idle/stopped/stopping, so unknown statuses FAIL CLOSED.
    """
    active, idle, stopping = [], [], []
    for m in models or []:
        status = str(m.get("status", "")).lower()
        name = m.get("name")
        if status in ("stopping", "stopping..."):
            stopping.append(name)
        elif status in ("idle", "unloaded", "stopped", "exited"):
            idle.append(name)
        else:
            # running / active / loaded / unknown -> hold.
            active.append(name)
    return {"active": active, "idle": idle, "stopping": stopping}


def _check_ollama_contention(
    ollama: Optional[OllamaClient],
    ctx: V2ExecutionContext,
) -> Dict[str, Any]:
    """Detect Ollama contention. Never auto force-kills a resident model.

    Policy:
      - no resident model                       -> continue
      - any model "stopping"                    -> surface V2OllamaStuck (explicit)
      - any active/loaded/UNKNOWN model         -> HOLD (V2OllamaContention)
      - idle model + policy opt-in              -> request normal stop (never kill)
    """
    if ollama is None:
        return {"resident": False, "policy": "no_ollama_client"}
    models = ollama.list_models() or []
    if not models:
        return {"resident": False, "policy": "none"}
    cl = _classify_ollama(models)
    if cl["stopping"]:
        raise V2OllamaStuck(
            f"Ollama model stuck in stop state, cannot safely proceed: {cl['stopping']}"
        )
    if cl["active"]:
        raise V2OllamaContention(
            f"resident Ollama model(s) active/unknown, holding V2 image request "
            f"(no auto kill): {cl['active']}"
        )
    if cl["idle"] and ctx.allow_ollama_idle_cleanup:
        for name in cl["idle"]:
            # Normal stop request only; never a force kill / SIGKILL.
            ollama.stop_model(str(name))
        return {"resident": True, "policy": "idle_stop_requested", "idle": cl["idle"]}
    return {"resident": True, "policy": "idle_no_action", "idle": cl["idle"]}


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #


def _perform_cleanup(
    client: ComfyUIExecutionClient,
    gpu_metrics: Optional[GpuMetricsProvider],
    ollama: Optional[OllamaClient],
    ctx: V2ExecutionContext,
    *,
    vram_before: Optional[int] = None,
) -> CleanupResult:
    """Task-final cleanup, executed exactly once per logical execution.

    Order (per contract):
      1. Ollama unload if this task owns a model (normal stop, never force-kill);
      2. verify Ollama state (owned model no longer resident);
      3. POST /free with exactly {unload_models:true, free_memory:true};
      4. verify ComfyUI remains reachable (post_cleanup_health_check);
      5. verify GPU memory release when measurable.

    Cleanup effectiveness requires /free attempted + health verified + (when
    measurable) release observed. An HTTP non-2xx with verified release is an
    ANOMALY, never silently rewritten as a normal HTTP success. /free is never
    retried within the same cleanup sequence.
    """
    pre_mib = None
    if vram_before is not None:
        pre_mib = vram_before // (1024 * 1024)
    post_mib: Optional[int] = None
    health_ok = False
    http_status: Optional[int] = None
    anomaly = False
    note_parts: List[str] = []

    # 1+2. Ollama unload if owned, then verify.
    if ctx.owned_ollama_model and ollama is not None:
        try:
            ollama.stop_model(ctx.owned_ollama_model)
            remaining = [m.get("name") for m in (ollama.list_models() or [])]
            if ctx.owned_ollama_model in remaining:
                note_parts.append("ollama owned model still resident after stop request")
            else:
                note_parts.append("ollama owned model unloaded")
        except Exception as exc:  # noqa: BLE001
            note_parts.append(f"ollama stop warning: {exc}")

    # 3. POST /free (exactly once).
    try:
        resp = client.free_models()
        http_status = int(resp.get("status_code", 0))
    except Exception as exc:  # noqa: BLE001 - cleanup must not mask primary error
        note_parts.append(f"free_models raised: {exc}")
        http_status = None

    # 4. verify ComfyUI reachable.
    try:
        health_ok = client.post_cleanup_health_check()
    except Exception:
        health_ok = False
    if not health_ok:
        note_parts.append("comfyui not reachable post-cleanup")

    # 5. verify GPU memory release when measurable.
    if gpu_metrics is not None:
        try:
            post_used = gpu_metrics.vram_used_bytes()
            post_mib = post_used // (1024 * 1024)
        except Exception:
            post_mib = None

    # Anomaly: HTTP indicates failure but measured VRAM actually released.
    if http_status is not None and http_status != 200 and pre_mib is not None and post_mib is not None:
        released = pre_mib - post_mib
        if released > 0:
            anomaly = True
            note_parts.append(
                f"cleanup HTTP {http_status} but VRAM released ({pre_mib} -> {post_mib} MiB); "
                f"anomaly recorded, effective cleanup preserved"
            )

    released_mib = None
    if pre_mib is not None and post_mib is not None:
        released_mib = pre_mib - post_mib

    result = CleanupResult(
        attempted=(http_status is not None),
        free_http_status=http_status,
        comfyui_reachable_post=health_ok,
        pre_cleanup_vram_mib=pre_mib,
        post_cleanup_vram_mib=post_mib,
        vram_released_mib=released_mib,
        cleanup_effective=False,
        cleanup_anomaly=anomaly,
        note="; ".join(note_parts),
    )
    result.cleanup_effective = result.success()
    if not result.attempted:
        result.cleanup_status = "failed"
    elif result.cleanup_effective:
        result.cleanup_status = "completed"
    else:
        result.cleanup_status = "failed"
    return result


def _deferred_cleanup_result() -> CleanupResult:
    """Truthful representation of a single execution whose cleanup is deferred.

    The execution did NOT issue /free; the owning task is responsible for the
    real task-final cleanup. This is never reported as a cleanup success and
    never fabricates ``free_http_status=200``.
    """
    return CleanupResult(
        attempted=False,
        free_http_status=None,
        comfyui_reachable_post=False,
        cleanup_effective=False,
        cleanup_anomaly=False,
        cleanup_status="deferred",
        note="cleanup deferred to task finalization",
    )


# --------------------------------------------------------------------------- #
# Single execution
# --------------------------------------------------------------------------- #


def _derive_execution_id(profile: str, resolution: Any) -> str:
    """Stable, deterministic logical execution identity for a resolved request.

    Derived from profile + workflow SHA-256 so the same resolved request maps to
    the same identity (duplicate-submission protection). A caller may instead
    pass an explicit ``execution_id``.
    """
    workflow = getattr(resolution, "workflow", resolution)
    if isinstance(workflow, dict):
        wf_bytes = json.dumps(workflow, sort_keys=True, separators=(",", ":")).encode("utf-8")
    else:
        wf_bytes = str(workflow).encode("utf-8")
    digest = hashlib.sha256(wf_bytes).hexdigest()[:16]
    return f"v2exec-{profile}-{digest}"


def execute_v2(
    profile: str,
    resolution: Any,
    target_path: Path,
    *,
    client: ComfyUIExecutionClient,
    gpu_metrics: Optional[GpuMetricsProvider] = None,
    ollama: Optional[OllamaClient] = None,
    ctx: Optional[V2ExecutionContext] = None,
    provenance: Optional[Dict[str, Any]] = None,
    execution_id: Optional[str] = None,
    registry: Optional[V2ExecutionRegistry] = None,
    cleanup_mode: str = CLEANUP_MODE_AUTO,
    preflight: str = PREFLIGHT_COLD,
) -> V2ExecutionResult:
    """Execute one resolved V2 request through the fail-closed production contract.

    ``resolution`` is the router's RoutedResolution (or any object exposing
    ``.workflow`` and ``.provenance``). All GPU/HTTP/metrics I/O is injected.

    ``cleanup_mode`` controls cleanup granularity:
      - CLEANUP_MODE_AUTO (default): the existing production behavior; cleanup
        (POST /free + verification) runs at the end of THIS execution.
      - CLEANUP_MODE_DEFERRED: this execution performs all real production steps
        (preflight, submit, wait, retrieve, validate, provenance) but does NOT
        issue /free. The owning multi-replica task is responsible for exactly
        one real cleanup via ``finalize_v2_task_cleanup``. The result truthfully
        reports ``cleanup_status="deferred"``; it never fabricates a success.

    ``preflight`` selects the VRAM preflight floor:
      - PREFLIGHT_COLD (default): applies the full cold-start floor
        (GPU_MIN_FREE_VRAM_MIB) and is correct for the first model load of a task.
      - PREFLIGHT_WARM_RESIDENT: applies the narrower generation-headroom floor
        (GPU_MIN_FREE_VRAM_WARM_MIB) and is correct for follow-up replicas of a
        deferred task whose checkpoint + LoRA are already resident from a prior
        replica (deferred mode issues no /free between replicas). This is NOT a
        weakening of the cold-start floor; it is a distinct task-aware floor used
        only when the retained allocation is the intended state.

    No actual GPU generation occurs in this remediation lane (clients are faked).
    """
    """Execute one resolved V2 request through the fail-closed production contract.

    ``resolution`` is the router's RoutedResolution (or any object exposing
    ``.workflow`` and ``.provenance``). All GPU/HTTP/metrics I/O is injected.

    No actual GPU generation occurs in this remediation lane (clients are faked).
    """
    if cleanup_mode not in (CLEANUP_MODE_AUTO, CLEANUP_MODE_DEFERRED):
        raise ValueError(
            f"cleanup_mode must be {CLEANUP_MODE_AUTO!r} or {CLEANUP_MODE_DEFERRED!r}, got {cleanup_mode!r}"
        )
    if preflight not in (PREFLIGHT_COLD, PREFLIGHT_WARM_RESIDENT):
        raise ValueError(
            f"preflight must be {PREFLIGHT_COLD!r} or {PREFLIGHT_WARM_RESIDENT!r}, got {preflight!r}"
        )
    ctx = ctx or V2ExecutionContext()
    required_vram_bytes = (
        GPU_MIN_FREE_VRAM_WARM_BYTES
        if preflight == PREFLIGHT_WARM_RESIDENT
        else ctx.required_vram_bytes
    )
    registry = registry or _DEFAULT_REGISTRY
    execution_id = execution_id or _derive_execution_id(profile, resolution)
    target_path = Path(target_path)
    # Pipeline provenance passthrough: start from the resolved request's provenance
    # so the qualified pipeline's authority is preserved through every outcome.
    base_provenance = dict(getattr(resolution, "provenance", None) or {})
    vram_before: Optional[int] = None
    if gpu_metrics is not None:
        try:
            vram_before = gpu_metrics.vram_used_bytes()
        except Exception:
            vram_before = None

    # 1. Resource preflight (fail closed before submit).
    try:
        gpu_preflight = _preflight_vram(gpu_metrics, required_vram_bytes)
    except V2ExecutionError as exc:
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=None,
            output_path=None,
            output_sha256=None,
            status="failed",
            gpu_preflight={"available": gpu_metrics is not None, "sufficient": False},
            provenance=base_provenance,
            primary_error=str(exc),
            error_type=type(exc).__name__,
        )

    # 2. Ollama contention (never force-kills).
    try:
        ollama_preflight = _check_ollama_contention(ollama, ctx)
    except V2ExecutionError as exc:
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=None,
            output_path=None,
            output_sha256=None,
            status="failed",
            gpu_preflight=gpu_preflight,
            ollama_preflight={"policy": "blocked"},
            provenance=base_provenance,
            primary_error=str(exc),
            error_type=type(exc).__name__,
        )

    # 3. Workflow resolution (pipeline authority preserved unchanged).
    workflow = getattr(resolution, "workflow", resolution)
    if not isinstance(workflow, dict):
        # Pre-submission structural error: no GPU resource acquired, no cleanup.
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=None,
            output_path=None,
            output_sha256=None,
            status="failed",
            gpu_preflight=gpu_preflight,
            ollama_preflight=ollama_preflight,
            provenance=base_provenance,
            primary_error="resolved workflow is not a dict",
            error_type="V2ExecutionError",
        )

    # 4. Duplicate-submission protection: one logical execution submits once.
    if registry.is_submitted(execution_id):
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=registry.prompt_id_for(execution_id),
            output_path=None,
            output_sha256=None,
            status="failed",
            gpu_preflight=gpu_preflight,
            ollama_preflight=ollama_preflight,
            provenance=base_provenance,
            primary_error=f"duplicate submission blocked for {execution_id}",
            error_type="V2DuplicateSubmission",
            duplicate=True,
        )

    # 5. Submit (single attempt; no automatic resubmit on failure).
    submitted_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        prompt_id = client.submit_workflow(workflow)
    except V2ComfyUIUnavailable as exc:
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=None,
            output_path=None,
            output_sha256=None,
            status="failed",
            submitted_at=submitted_at,
            gpu_preflight=gpu_preflight,
            ollama_preflight=ollama_preflight,
            provenance=base_provenance,
            primary_error=str(exc),
            error_type="V2ComfyUIUnavailable",
        )
    except V2SubmissionFailure as exc:
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=None,
            output_path=None,
            output_sha256=None,
            status="failed",
            submitted_at=submitted_at,
            gpu_preflight=gpu_preflight,
            ollama_preflight=ollama_preflight,
            provenance=base_provenance,
            primary_error=str(exc),
            error_type="V2SubmissionFailure",
        )

    # Submission succeeded: record identity. No automatic resubmit on later failure.
    registry.mark_submitted(execution_id, prompt_id)

    # 6. Wait + retrieve + validate (failures here are POST_SUBMIT_KNOWN/UNKNOWN;
    #    never automatically resubmitted).
    try:
        client.wait_for_completion(prompt_id)
        image_bytes = client.retrieve_output(prompt_id)
        validate_output_image(image_bytes)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(image_bytes)
        output_sha = hashlib.sha256(image_bytes).hexdigest()
    except V2ExecutionError as exc:
        cleanup = (
            _deferred_cleanup_result()
            if cleanup_mode == CLEANUP_MODE_DEFERRED
            else _perform_cleanup(client, gpu_metrics, ollama, ctx, vram_before=vram_before)
        )
        return V2ExecutionResult(
            profile=profile,
            execution_id=execution_id,
            prompt_id=prompt_id,
            output_path=None,
            output_sha256=None,
            status="failed",
            submitted_at=submitted_at,
            gpu_preflight=gpu_preflight,
            ollama_preflight=ollama_preflight,
            provenance=base_provenance,
            cleanup=cleanup,
            primary_error=str(exc),
            error_type=type(exc).__name__,
        )

    # 7. Success: persist output SHA + provenance, then task-final cleanup.
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    merged_provenance = dict(base_provenance)
    merged_provenance.update(provenance or {})
    merged_provenance.update(
        {
            "execution_id": execution_id,
            "prompt_id": prompt_id,
            "output_path": str(target_path),
            "output_sha256": output_sha,
            "comfyui_endpoint": getattr(client, "endpoint", COMFYUI_ENDPOINT),
            "renderer_owner": RENDERER_OWNER,
        }
    )
    cleanup = (
        _deferred_cleanup_result()
        if cleanup_mode == CLEANUP_MODE_DEFERRED
        else _perform_cleanup(client, gpu_metrics, ollama, ctx, vram_before=vram_before)
    )
    return V2ExecutionResult(
        profile=profile,
        execution_id=execution_id,
        prompt_id=prompt_id,
        output_path=str(target_path),
        output_sha256=output_sha,
        status="success",
        submitted_at=submitted_at,
        completed_at=completed_at,
        gpu_preflight=gpu_preflight,
        ollama_preflight=ollama_preflight,
        provenance=merged_provenance,
        cleanup=cleanup,
    )


# --------------------------------------------------------------------------- #
# Task-final cleanup (explicit public entry point for task-scoped cleanup)
# --------------------------------------------------------------------------- #


def finalize_v2_task_cleanup(
    client: ComfyUIExecutionClient,
    gpu_metrics: Optional[GpuMetricsProvider],
    ollama: Optional[OllamaClient],
    ctx: Optional[V2ExecutionContext] = None,
    *,
    vram_before: Optional[int] = None,
) -> CleanupResult:
    """Perform exactly one real task-final cleanup for a deferred multi-replica task.

    This is the single real cleanup entry point that a higher-level multi-replica
    logical task must call ONCE after all its deferred executions have completed.
    It performs the full B3 cleanup contract exactly once:

      - Ollama unload if the task owns a model (normal stop, never force-kill);
      - exactly one real POST /free;
      - post-call ComfyUI health verification;
      - post-cleanup VRAM verification when measurable;
      - anomaly handling (HTTP failure with verified release is preserved as an
        anomaly, never silently collapsed to a success).

    This is the SAME real production cleanup used by ``execute_v2`` in auto mode;
    it is not a fake, a deferred client, or a no-op. Cleaning up at the task
    boundary (rather than per-replica) is what lets a two-replica qualification
    task emit zero real /free calls between replicas and exactly one verified
    /free after both, while ordinary single executions keep their automatic
    per-execution cleanup unchanged.
    """
    ctx = ctx or V2ExecutionContext()
    if vram_before is None and gpu_metrics is not None:
        try:
            vram_before = gpu_metrics.vram_used_bytes()
        except Exception:
            vram_before = None
    return _perform_cleanup(client, gpu_metrics, ollama, ctx, vram_before=vram_before)
