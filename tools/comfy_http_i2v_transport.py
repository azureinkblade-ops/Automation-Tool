"""Comfy HTTP I2V transport (additive; implements I2VBackendTransport).

Out-of-process urllib client for a running ComfyUI: POST /prompt, poll
/history/<id>, download outputs via /view. Fail-closed: unreachable endpoint
or missing required models raise ComfyTransportUnavailable / ComfyModelsMissing
(subclasses of InfrastructureFailure) -- never a placeholder video.

Opt-in for wan_22 only via select_i2v_transport(); SVD default path is untouched
(returns None -> caller keeps its existing transport). GPU ownership stays with
ImageToVideoAdapter's ExclusiveGpuLease.KIND_I2V; this transport never acquires it.
No identity canon, no LIVE_PUBLISH, no NET-PATREON, no chapter allocation.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from tools.i2v_backend_registry import BACKEND_ID_WAN_22
from tools.i2v_production_adapter import InfrastructureFailure

IDENTITY_CANON = False
COMFY_I2V_URL_ENV = "COMFY_I2V_URL"
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"

WAN_22_REQUIRED_MODELS: Dict[str, str] = {
    "wan2.2_ti2v_5B_fp16.safetensors": "diffusion_models",
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": "text_encoders",
    "wan2.2_vae.safetensors": "vae",
}
_VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".gif", ".webp")


class ComfyTransportUnavailable(InfrastructureFailure):
    pass


class ComfyModelsMissing(InfrastructureFailure):
    pass


class ComfyJobFailed(InfrastructureFailure):
    pass


Opener = Callable[..., Any]


class ComfyHttpI2VTransport:
    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        timeout: float = 10.0,
        poll_interval: float = 2.0,
        max_wait_s: float = 1800.0,
        required_models: Optional[Mapping[str, str]] = None,
        opener: Opener = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = (base_url or os.environ.get(COMFY_I2V_URL_ENV) or DEFAULT_COMFY_URL).rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait_s = max_wait_s
        self.required_models = dict(required_models or {})
        self._open = opener
        self._sleep = sleep
        self._clock = clock
        self.client_id = uuid.uuid4().hex

    # -- http ---------------------------------------------------------
    def _req(self, path: str, payload: Optional[Dict[str, Any]] = None, raw: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with self._open(req, timeout=self.timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise ComfyJobFailed(f"comfy HTTP {e.code} on {path}: {detail}") from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ComfyTransportUnavailable(f"comfy unreachable at {self.base_url}: {e}") from e
        if raw:
            return body
        return json.loads(body.decode("utf-8")) if body else {}

    # -- protocol -----------------------------------------------------
    def health_check(self) -> bool:
        try:
            self._req("/system_stats")
            return True
        except InfrastructureFailure:
            return False

    def free_models(self) -> Dict[str, Any]:
        try:
            self._req("/free", {"unload_models": True, "free_memory": True})
            return {"freed": True}
        except InfrastructureFailure as e:
            return {"freed": False, "error": str(e)}

    def missing_models(self) -> List[str]:
        missing: List[str] = []
        cache: Dict[str, Iterable[str]] = {}
        for name, folder in self.required_models.items():
            if folder not in cache:
                listing = self._req(f"/models/{urllib.parse.quote(folder)}")
                cache[folder] = set(listing or [])
            if name not in cache[folder]:
                missing.append(f"{folder}/{name}")
        return missing

    def assert_ready(self) -> None:
        if not self.health_check():
            raise ComfyTransportUnavailable(f"comfy unreachable at {self.base_url}")
        missing = self.missing_models()
        if missing:
            raise ComfyModelsMissing("comfy models missing: " + ", ".join(missing))

    def submit_and_wait(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        self.assert_ready()
        resp = self._req("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if resp.get("node_errors"):
            raise ComfyJobFailed(f"comfy node_errors: {json.dumps(resp['node_errors'])[:500]}")
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            raise ComfyJobFailed(f"comfy /prompt returned no prompt_id: {resp}")
        deadline = self._clock() + self.max_wait_s
        entry: Optional[Dict[str, Any]] = None
        while True:
            hist = self._req(f"/history/{prompt_id}")
            entry = hist.get(prompt_id) if isinstance(hist, dict) else None
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise ComfyJobFailed(f"comfy job {prompt_id} error: {json.dumps(status)[:500]}")
                if status.get("completed", True) and entry.get("outputs"):
                    break
            if self._clock() >= deadline:
                raise ComfyJobFailed(f"comfy job {prompt_id} timed out after {self.max_wait_s}s")
            self._sleep(self.poll_interval)
        ref = _pick_video_output(entry.get("outputs") or {})
        if ref is None:
            raise ComfyJobFailed(f"comfy job {prompt_id} produced no video output")
        q = urllib.parse.urlencode({"filename": ref["filename"], "subfolder": ref.get("subfolder", ""),
                                    "type": ref.get("type", "output")})
        video_bytes = self._req(f"/view?{q}", raw=True)
        if not video_bytes:
            raise ComfyJobFailed(f"comfy job {prompt_id} empty video download")
        return {
            "prompt_id": prompt_id,
            "video_bytes": video_bytes,
            "comfy_output": ref,
            "identity_canon": False,
        }


def _pick_video_output(outputs: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    for node_out in outputs.values():
        if not isinstance(node_out, Mapping):
            continue
        for key in ("videos", "gifs", "images"):
            for item in node_out.get(key) or []:
                fn = str(item.get("filename", ""))
                if fn.lower().endswith(_VIDEO_EXT):
                    return dict(item)
    return None


def select_i2v_transport(backend_id: str, *, base_url: Optional[str] = None, **kw: Any) -> Optional[ComfyHttpI2VTransport]:
    """wan_22 -> ComfyHttpI2VTransport with Wan model preflight. Others -> None (SVD unchanged)."""
    if backend_id != BACKEND_ID_WAN_22:
        return None
    kw.setdefault("required_models", WAN_22_REQUIRED_MODELS)
    return ComfyHttpI2VTransport(base_url, **kw)
