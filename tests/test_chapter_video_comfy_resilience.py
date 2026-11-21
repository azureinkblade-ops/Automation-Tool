"""ComfyUI lifecycle in chapter_video_wiring: idle-restart rule + one crash retry. CPU only.

ComfyUI is never launched or contacted: ``FakeHost`` stands in for start_comfyui_wan.bat (and the port), the
queue probe is a fake, and the pipelines are fakes. Every launcher call is recorded.
"""
from __future__ import annotations

import dataclasses
import hashlib

import pytest

from tests.test_chapter_video_wiring import _probe, _still
from tools import chapter_video_wiring as cvw
from tools import media_pipeline_integration as mpi
from tools.media_validity import validate_presented_social_video

DEFAULT = cvw.ChapterVideoConfig.from_env({})  # idle_restart=True (production default)
REUSE = dataclasses.replace(DEFAULT, idle_restart=False)  # legacy reuse


class FakeHost:
    """Scripted launcher + port. ``busy``: something listens on 8188; ``ours``: the launcher's pid file matches it."""

    def __init__(self, busy, ours=True, dynvram=True, stop_rc=None, start_rc=0, stop_frees_port=True):
        self.busy, self.ours, self.dynvram = busy, ours, dynvram
        self.stop_rc, self.start_rc, self.stop_frees_port = stop_rc, start_rc, stop_frees_port
        self.calls, self.starts, self.stops = [], 0, 0

    def kill(self):  # the ComfyUI process dies (e.g. access violation in load_unet)
        self.busy = False

    def __call__(self, argv, timeout):
        a = list(argv)
        assert len(a) >= 1 and isinstance(a[0], str) and a[0].lower().endswith(".bat")
        flags = a[1:]
        self.calls.append(flags)
        if flags == ["-Status"]:
            if not self.busy:
                return 0, "STATUS port8188_busy=False our_pid=none\nSTATUS /system_stats unreachable"
            return 0, f"STATUS port8188_busy=True our_pid=1\nSTATUS dynvram_disabled={self.dynvram}"
        if flags == ["-Stop"]:
            self.stops += 1
            if not self.ours or not self.busy:
                return 1, "STOP: no running instance started by this script"
            if self.stop_frees_port:
                self.busy = False
            return 0, "STOP"
        if flags == []:
            if self.busy:
                return 3, "ABORT: port 8188 is already in use"  # the real launcher refuses a second instance
            self.starts += 1
            if self.start_rc == 0:
                self.busy, self.ours = True, True
            return self.start_rc, "START"
        raise AssertionError(flags)


def idle(_url, _t):
    return (0, 0)


def never_called(_url, _t):
    raise AssertionError("queue must not be probed")


# ------------------------------------------------------------------ idle-restart rule (steering)

def test_idle_instance_is_restarted_through_launcher_then_status_confirmed():
    host = FakeHost(busy=True)
    r = cvw.ensure_comfy_ready(DEFAULT, host, idle, sleep=lambda s: None)
    assert r.ok and r.started_by_us and r.reason == "restarted_idle_instance_via_launcher"
    assert host.calls == [["-Status"], ["-Stop"], ["-Status"], [], ["-Status"]]
    assert host.starts == 1 and host.busy  # exactly one ComfyUI, via the launcher


@pytest.mark.parametrize("queue", [(1, 0), (0, 2), (1, 3)])
def test_busy_instance_is_held_never_stopped(queue):
    host = FakeHost(busy=True)
    r = cvw.ensure_comfy_ready(DEFAULT, host, lambda u, t: queue, sleep=lambda s: None)
    assert not r.ok and r.reason.startswith("COMFY_BUSY_NOT_RESTARTED")
    assert host.calls == [["-Status"]] and host.stops == 0 and host.starts == 0


def test_unknown_queue_is_held_never_stopped():
    host = FakeHost(busy=True)
    r = cvw.ensure_comfy_ready(DEFAULT, host, lambda u, t: None, sleep=lambda s: None)
    assert not r.ok and "QUEUE_UNKNOWN" in r.reason and host.calls == [["-Status"]]


def test_probe_exception_is_held_never_stopped():
    def boom(u, t):
        raise OSError("x")

    host = FakeHost(busy=True)
    assert not cvw.ensure_comfy_ready(DEFAULT, host, boom, sleep=lambda s: None).ok
    assert host.stops == 0


def test_idle_instance_not_stoppable_by_launcher_is_held_and_no_second_start():
    host = FakeHost(busy=True, ours=False)  # someone else's ComfyUI: launcher -Stop refuses (rc 1)
    r = cvw.ensure_comfy_ready(DEFAULT, host, idle, sleep=lambda s: None)
    assert not r.ok and "NOT_STOPPABLE" in r.reason
    assert host.starts == 0 and host.busy


def test_stop_that_leaves_port_busy_never_starts_a_second():
    host = FakeHost(busy=True, stop_frees_port=False)
    r = cvw.ensure_comfy_ready(DEFAULT, host, idle, sleep=lambda s: None)
    assert not r.ok and r.reason == "COMFY_IDLE_RESTART_PORT_STILL_BUSY" and host.starts == 0


def test_restart_with_dynvram_not_disabled_stops_and_holds():
    host = FakeHost(busy=True, dynvram=False)  # after our start, -Status says dynvram False -> hold + -Stop of ours
    r = cvw.ensure_comfy_ready(DEFAULT, host, idle, sleep=lambda s: None)
    assert not r.ok and host.calls[-1] == ["-Stop"]


def test_port_free_starts_once_without_probing_queue():
    host = FakeHost(busy=False)
    r = cvw.ensure_comfy_ready(DEFAULT, host, never_called, sleep=lambda s: None)
    assert r.ok and r.started_by_us and host.starts == 1 and host.stops == 0


def test_idle_restart_off_is_legacy_reuse_without_probe():
    host = FakeHost(busy=True)
    r = cvw.ensure_comfy_ready(REUSE, host, never_called)
    assert r.ok and not r.started_by_us and host.calls == [["-Status"]]


# ------------------------------------------------------------------ driver: crash -> one fresh start + one retry

class CrashyPipelines:
    """Per-backend scripted pipelines. A step is 'ok' | 'hold' | 'raise' | 'crash' (ComfyUI dies, then raises)."""

    def __init__(self, tmp_path, host, script):
        self.tmp, self.host, self.script, self.log = tmp_path, host, {k: list(v) for k, v in script.items()}, []

    def __call__(self, backend):
        outer = self

        class P:
            def produce_social_media(self, still, *, workflow_id, seed):
                outer.log.append((backend, workflow_id))
                steps = outer.script[backend]
                step = steps.pop(0) if len(steps) > 1 else steps[0]
                if step == "crash":
                    outer.host.kill()
                    raise ConnectionError("connection dropped: ComfyUI died loading the model")
                if step == "raise":
                    raise RuntimeError("comfy node error (server alive)")
                if step == "hold":
                    return mpi.PipelineResult(workflow_id=workflow_id, media_record_id="m", idempotency_key="k", outcome="MEDIA_HOLD",
                                              state="MEDIA_HOLD", source_image_sha256=still.source_image_sha256, asset_path=None,
                                              asset_sha256=None, asset_kind="none", raw_video_sha256=None, presented_video_sha256=None,
                                              video_creates_identity_canon=False, failure_reason=f"VIDEO_REQUIRED_MISSING:{backend}_failed")
                out = outer.tmp / f"{backend}-{len(outer.log)}.mp4"
                out.write_bytes(b"v" * 20000)
                return mpi.PipelineResult(workflow_id=workflow_id, media_record_id="m", idempotency_key="k", outcome="SOCIAL_READY",
                                          state="READY", source_image_sha256=still.source_image_sha256, asset_path=str(out),
                                          asset_sha256=hashlib.sha256(out.read_bytes()).hexdigest(), asset_kind="presented_mp4",
                                          raw_video_sha256="r", presented_video_sha256="p", video_creates_identity_canon=False,
                                          failure_reason=None)

        return P()


def _run(tmp_path, monkeypatch, host, script, cfg=REUSE, probe=never_called):
    monkeypatch.setattr(cvw, "validate_presented_social_video",
                        lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(73 / 24), **kw))
    pipes = CrashyPipelines(tmp_path, host, script)
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:t", store_root=tmp_path / "store", still_approved=True, cfg=cfg,
        pipeline_builder=pipes, comfy_runner=host, queue_probe=probe, sleep=lambda s: None)
    return res, pipes, host


def test_reused_instance_dies_fresh_start_and_one_wan_retry_succeeds(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "ok"], "svd_xt_1_1": ["ok"]})
    assert res.ready and res.backend_used == "wan_22" and not res.fallback_used and res.comfy_restarts == 1
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22"]  # exactly one retry, no SVD
    assert pipes.log[0][1] != pipes.log[1][1] and pipes.log[1][1].endswith("|retry1")  # retry has its own job identity
    assert host.starts == 1  # one fresh ComfyUI, via the launcher only
    assert host.calls[:4] == [["-Status"], ["-Status"], [], ["-Status"]]  # reuse check, crash check, start, dynvram re-check
    assert host.calls[-1] == ["-Stop"] and host.stops == 1  # we started the fresh one -> stop only that at the end
    assert any(a.get("outcome") == "COMFY_RESTARTED" for a in res.attempts)


def test_default_cfg_idle_restart_then_crash_still_gets_one_fresh_start_and_retry(tmp_path, monkeypatch):
    host = FakeHost(busy=True)  # idle instance -> restarted up front, then it crashes loading the model
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "ok"], "svd_xt_1_1": ["ok"]}, cfg=DEFAULT, probe=idle)
    assert res.ready and res.backend_used == "wan_22" and res.comfy_restarts == 1
    assert host.starts == 2 and host.stops == 2  # initial idle restart (-Stop of old) + crash restart; final -Stop of ours
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22"]


def test_retry_fails_then_svd_and_never_a_second_restart(tmp_path, monkeypatch):
    host = FakeHost(busy=True)  # the retry errors but ComfyUI stays alive (/queue answers) -> no restart before SVD
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "raise"], "svd_xt_1_1": ["ok"]}, probe=idle)
    assert res.ready and res.backend_used == "svd_xt_1_1" and res.fallback_used
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22", "svd_xt_1_1"]
    assert host.starts == 1 and res.comfy_restarts == 1 and res.fallback_restart == ""
    assert host.calls[-1] == ["-Stop"]


def test_still_alive_but_erroring_is_never_restarted_straight_to_svd(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["raise"], "svd_xt_1_1": ["ok"]})
    assert res.ready and res.backend_used == "svd_xt_1_1"
    assert [b for b, _ in pipes.log] == ["wan_22", "svd_xt_1_1"]  # no Wan retry
    assert host.starts == 0 and host.stops == 0 and [] not in host.calls and ["-Stop"] not in host.calls
    assert res.comfy_restarts == 0 and res.attempts[0].get("comfy_alive") is True


def test_still_alive_wan_media_hold_is_not_a_crash(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["hold"], "svd_xt_1_1": ["ok"]})
    assert res.backend_used == "svd_xt_1_1" and host.starts == 0 and host.stops == 0


def test_crash_restart_failure_fails_closed_no_svd_no_asset(tmp_path, monkeypatch):
    host = FakeHost(busy=True, start_rc=4)  # ComfyUI exited early on the fresh start
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash"], "svd_xt_1_1": ["ok"]})
    assert res.outcome == "MEDIA_HOLD" and res.asset_path is None and not res.ready
    assert res.hold_reason.startswith("VIDEO_REQUIRED_MISSING:") and "COMFY_START_FAILED" in res.hold_reason
    assert [b for b, _ in pipes.log] == ["wan_22"]  # dead server: SVD is not attempted against nothing


def test_everything_fails_after_restart_is_media_hold(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "hold"], "svd_xt_1_1": ["hold"]}, probe=idle)
    assert res.outcome == "MEDIA_HOLD" and res.asset_path is None and "wan_22" in res.hold_reason and "svd_xt_1_1" in res.hold_reason
    assert host.starts == 1 and host.calls[-1] == ["-Stop"]


def test_second_crash_in_same_run_is_not_restarted_again(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "crash"], "svd_xt_1_1": ["crash"]})
    # cap: one crash restart for the Wan retry + one fresh start before SVD (svd_after_restart); never a third
    assert res.outcome == "MEDIA_HOLD" and host.starts == 2 and res.comfy_restarts == 2
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22", "svd_xt_1_1"] and res.fallback_restart == "svd_after_restart"


def test_crash_restart_refused_rc3_never_stops_the_foreign_instance(tmp_path, monkeypatch):
    """Someone else grabbed 8188 between the failure and our start: the launcher refuses (rc 3); we never -Stop it."""
    host = FakeHost(busy=True, start_rc=3)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash"], "svd_xt_1_1": ["ok"]})
    assert res.outcome == "MEDIA_HOLD" and "COMFY_START_FAILED:rc=3" in res.hold_reason
    assert ["-Stop"] not in host.calls and res.comfy_restarts == 0


def test_skip_guard_never_restarts(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    monkeypatch.setattr(cvw, "validate_presented_social_video",
                        lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(73 / 24), **kw))
    pipes = CrashyPipelines(tmp_path, host, {"wan_22": ["crash"], "svd_xt_1_1": ["ok"]})
    res = cvw.produce_chapter_clip(_still(tmp_path), workflow_id="w", store_root=tmp_path, still_approved=True, cfg=REUSE,
                                   pipeline_builder=pipes, comfy_runner=host, skip_comfy_guard=True)
    assert host.calls == [] and res.backend_used == "svd_xt_1_1"


def test_default_driver_holds_when_comfy_busy_with_other_work(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["ok"], "svd_xt_1_1": ["ok"]}, cfg=DEFAULT, probe=lambda u, t: (1, 1))
    assert res.outcome == "MEDIA_HOLD" and "COMFY_BUSY_NOT_RESTARTED" in res.hold_reason
    assert pipes.log == [] and host.stops == 0 and host.starts == 0


def test_default_queue_probe_parses_comfy_queue_and_fails_closed(monkeypatch):
    import io
    import json
    import urllib.request

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = {}

    def fake_urlopen(url, timeout=None):
        seen["url"] = url
        return Resp(json.dumps({"queue_running": [["a"]], "queue_pending": []}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert cvw.default_queue_probe("http://127.0.0.1:8188/") == (1, 0) and seen["url"] == "http://127.0.0.1:8188/queue"

    def boom(url, timeout=None):
        raise OSError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert cvw.default_queue_probe("http://127.0.0.1:8188") is None
