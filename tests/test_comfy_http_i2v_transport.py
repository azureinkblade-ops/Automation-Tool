import io
import json
import urllib.error

import pytest

from tools import comfy_http_i2v_transport as T
from tools.i2v_backend_registry import BACKEND_ID_WAN_22
from tools.i2v_production_adapter import BACKEND_ID_SVD_XT_1_1, InfrastructureFailure, I2VBackendTransport


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake(routes, calls):
    def opener(req, timeout=None):
        url = req.full_url
        calls.append((req.get_method(), url))
        for prefix, val in routes.items():
            if prefix in url:
                v = val(req) if callable(val) else val
                return _Resp(v if isinstance(v, bytes) else json.dumps(v).encode())
        raise urllib.error.URLError("no route")
    return opener


def _down(req, timeout=None):
    raise urllib.error.URLError("connection refused")


ALL_MODELS = {
    "/models/diffusion_models": ["wan2.2_ti2v_5B_fp16.safetensors"],
    "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
    "/models/vae": ["wan2.2_vae.safetensors"],
}


def test_protocol_conformance():
    assert isinstance(T.ComfyHttpI2VTransport(), I2VBackendTransport)


def test_endpoint_down_fail_closed():
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, base_url="http://127.0.0.1:1", opener=_down)
    assert tr.health_check() is False
    assert tr.free_models()["freed"] is False
    with pytest.raises(T.ComfyTransportUnavailable):
        tr.submit_and_wait({"1": {}})
    assert issubclass(T.ComfyTransportUnavailable, InfrastructureFailure)


def test_models_missing_fail_closed_no_submit():
    calls = []
    routes = {"/system_stats": {}, "/models/": []}
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=_fake(routes, calls))
    with pytest.raises(T.ComfyModelsMissing) as e:
        tr.submit_and_wait({"1": {}})
    assert "wan2.2_vae" in str(e.value)
    assert not any("/prompt" in u for _, u in calls)


def test_wan_selects_transport_svd_unchanged():
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22)
    assert isinstance(tr, T.ComfyHttpI2VTransport)
    assert tr.required_models == T.WAN_22_REQUIRED_MODELS
    assert T.select_i2v_transport(BACKEND_ID_SVD_XT_1_1) is None


def test_happy_path_submit_poll_download():
    calls = []
    polls = {"n": 0}

    def history(req):
        polls["n"] += 1
        if polls["n"] < 2:
            return {}
        return {"pid1": {"status": {"completed": True, "status_str": "success"},
                         "outputs": {"9": {"images": [{"filename": "wan_00001.mp4", "subfolder": "", "type": "output"}]}}}}

    routes = dict(ALL_MODELS)
    routes.update({"/system_stats": {}, "/prompt": {"prompt_id": "pid1", "node_errors": {}},
                   "/history/pid1": history, "/view?": b"\x00\x00\x00\x18ftypmp42VIDEO"})
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=_fake(routes, calls), sleep=lambda s: None)
    out = tr.submit_and_wait({"1": {"class_type": "X"}})
    assert out["prompt_id"] == "pid1"
    assert out["video_bytes"].startswith(b"\x00\x00\x00\x18ftyp")
    assert out["identity_canon"] is False
    assert ("POST", "http://127.0.0.1:8188/prompt") in calls


def test_job_error_and_timeout():
    routes = dict(ALL_MODELS)
    routes.update({"/system_stats": {}, "/prompt": {"prompt_id": "p"},
                   "/history/p": {"p": {"status": {"status_str": "error"}, "outputs": {}}}})
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=_fake(routes, []), sleep=lambda s: None)
    with pytest.raises(T.ComfyJobFailed):
        tr.submit_and_wait({})
    routes["/history/p"] = {}
    t = [0.0]
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=_fake(routes, []), max_wait_s=5,
                                sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
    with pytest.raises(T.ComfyJobFailed):
        tr.submit_and_wait({})


def test_flags_and_no_side_effects():
    import tools.production_orchestration_live_wiring as lw
    assert T.IDENTITY_CANON is False
    assert lw.LIVE_PUBLISH_ENABLED_DEFAULT is False
    assert lw.SOCIAL_READY_CREATES_IDENTITY_CANON is False
    src = open(T.__file__, encoding="utf-8").read()
    for bad in ("patreon", "LIVE_PUBLISH", "HA-114", "allocate"):
        assert bad.lower() not in src.lower().replace("no net-patreon", "").replace("no live_publish", "").replace("no chapter allocation", "")
