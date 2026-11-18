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


# ---- /upload/image + wan_22 packet labels ----
import io as _io
from tools import i2v_production_adapter as A


def _png(w=64, h=32):
    from PIL import Image
    b = _io.BytesIO()
    Image.new("RGB", (w, h), (200, 10, 10)).save(b, format="PNG")
    return b.getvalue()


def test_upload_image_success_multipart():
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["ct"] = req.get_header("Content-type")
        seen["body"] = req.data
        return _Resp(json.dumps({"name": "i2v_src_job1.png", "subfolder": "", "type": "input"}).encode())

    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=opener)
    src = A.SourceImageRef("a" * 64, True, True, True, 64, 32, image_bytes=_png())
    name = tr.stage_and_upload(src, 720, 1280, "job1")
    assert name == "i2v_src_job1.png"
    assert seen["url"].endswith("/upload/image")
    assert "multipart/form-data" in seen["ct"]
    from PIL import Image
    body = seen["body"]
    png = body[body.index(b"\x89PNG"):]
    assert Image.open(_io.BytesIO(png)).size == (720, 1280)


def test_upload_fail_closed():
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=_down)
    with pytest.raises(T.ComfyUploadFailed):
        tr.upload_image(_png(), "x.png")
    with pytest.raises(T.ComfyUploadFailed):
        tr.upload_image(b"", "x.png")
    bad = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=lambda r, timeout=None: _Resp(b"{}"))
    with pytest.raises(T.ComfyUploadFailed):
        bad.upload_image(_png(), "x.png")
    src = A.SourceImageRef("a" * 64, True, True, True, 64, 32)
    with pytest.raises(T.ComfyUploadFailed):
        tr.stage_and_upload(src, 720, 1280, "j")
    assert issubclass(T.ComfyUploadFailed, InfrastructureFailure)


def test_packet_labels_wan_vs_svd():
    w = A.i2v_packet_labels("wan_22", A.MODEL_SHA256_SVD_XT_1_1)
    assert w == {"model_id": A.MODEL_ID_WAN_22, "model_sha256": A.MODEL_SHA256_WAN_22,
                 "workflow_version": A.WORKFLOW_VERSION_WAN_22}
    s = A.i2v_packet_labels(A.BACKEND_ID_SVD_XT_1_1, None)
    assert s["model_id"] == A.MODEL_ID_SVD_XT_1_1 and s["workflow_version"] == A.WORKFLOW_VERSION
    assert s["model_sha256"] == A.MODEL_SHA256_SVD_XT_1_1


def test_fail_early_packet_wan_labels(tmp_path):
    ad = A.ImageToVideoAdapter(store=A.VideoJobStore(tmp_path))
    src = A.SourceImageRef("a" * 64, True, True, True, 64, 32)
    st = list(A.ValidationStatus)[0]
    r = ad._fail_early(src, 1, A.I2VSettings(), "wf", st, "r", None, backend_id="wan_22")
    assert (r.backend_id, r.model_id, r.workflow_version) == ("wan_22", A.MODEL_ID_WAN_22, A.WORKFLOW_VERSION_WAN_22)
    r2 = ad._fail_early(src, 1, A.I2VSettings(), "wf", st, "r", None)
    assert (r2.model_id, r2.workflow_version) == (A.MODEL_ID_SVD_XT_1_1, A.WORKFLOW_VERSION)
