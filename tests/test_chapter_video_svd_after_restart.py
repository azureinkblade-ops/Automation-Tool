"""Wan crashed ComfyUI twice (retry used up) -> one fresh ComfyUI start via the launcher before SVD. CPU only.

Research's real run on 25f2e71: both Wan attempts died with an access violation in the final VAE decode; SVD then
failed only because the crashed ComfyUI was down. ComfyUI is never launched or contacted here: ``FakeHost`` stands in
for start_comfyui_wan.bat and the port, pipelines and the queue probe are fakes.
"""
from __future__ import annotations

import threading

from tests.test_chapter_video_comfy_resilience import DEFAULT, REUSE, FakeHost, _run, idle
from tests.test_chapter_video_wiring import _still
from tools import chapter_video_wiring as cvw


class ScriptedStarts(FakeHost):
    """``start_rcs``: return code of each successive launcher start (last one repeats)."""

    def __init__(self, start_rcs, **kw):
        super().__init__(**kw)
        self.start_rcs = list(start_rcs)
        self.timeouts = []

    def __call__(self, argv, timeout):
        self.timeouts.append((list(argv)[1:], timeout))
        if list(argv)[1:] == [] and not self.busy:
            self.start_rc = self.start_rcs.pop(0) if len(self.start_rcs) > 1 else self.start_rcs[0]
        return super().__call__(argv, timeout)


def test_wan_crashes_twice_restart_then_svd_succeeds(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "crash"], "svd_xt_1_1": ["ok"]})
    assert res.ready and res.outcome == "SOCIAL_READY" and res.backend_used == "svd_xt_1_1" and res.fallback_used
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22", "svd_xt_1_1"]
    assert res.fallback_restart == "svd_after_restart" and res.comfy_restarts == 2
    assert host.starts == 2  # Wan crash restart + one fresh start before SVD, both via the launcher
    pre = [a for a in res.attempts if a.get("stage") == "before_fallback"]
    assert pre == [{"backend": "svd_xt_1_1", "outcome": "COMFY_RESTARTED", "reason": "restarted_before_fallback_via_launcher",
                    "stage": "before_fallback", "status": "svd_after_restart"}]
    # each start is followed by -Status (dynvram_disabled=True required); our instance is stopped at the end
    starts = [i for i, c in enumerate(host.calls) if c == []]
    assert all(host.calls[i + 1] == ["-Status"] for i in starts)
    assert host.calls[-1] == ["-Stop"]
    assert res.to_dict()["fallback_restart"] == "svd_after_restart"


def test_restart_before_svd_fails_is_media_hold_and_svd_not_run(tmp_path, monkeypatch):
    host = ScriptedStarts([0, 4], busy=True)  # crash restart ok, the pre-SVD start exits early (rc 4)
    res, pipes, _ = _run(tmp_path, monkeypatch, host, {"wan_22": ["crash", "crash"], "svd_xt_1_1": ["ok"]})
    assert res.outcome == "MEDIA_HOLD" and not res.ready and res.asset_path is None
    assert "COMFY_START_FAILED:rc=4" in res.hold_reason and res.hold_reason.startswith("VIDEO_REQUIRED_MISSING:")
    assert res.fallback_restart == "svd_restart_failed:COMFY_START_FAILED:rc=4"
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22"]  # SVD never runs against a dead server
    assert host.starts == 2


def test_dynvram_not_disabled_after_pre_svd_start_is_media_hold(tmp_path, monkeypatch):
    host = FakeHost(busy=True)
    real = host.__call__

    def runner(argv, timeout):
        if list(argv)[1:] == [] and host.starts == 1:
            host.dynvram = False  # the second fresh start comes up without dynvram disabled
        return real(argv, timeout)

    from tests.test_chapter_video_comfy_resilience import CrashyPipelines  # noqa: F401 (same fakes as _run)
    res, pipes, _ = _run(tmp_path, monkeypatch, runner_host(host, runner), {"wan_22": ["crash", "crash"], "svd_xt_1_1": ["ok"]})
    assert res.outcome == "MEDIA_HOLD" and "COMFY_DYNVRAM_NOT_DISABLED_AFTER_START" in res.fallback_restart
    assert [b for b, _ in pipes.log] == ["wan_22", "wan_22"]


class runner_host:  # noqa: N801 - tiny adapter: FakeHost API (kill/busy) + a custom __call__
    def __init__(self, host, runner):
        self.host, self.runner = host, runner

    def kill(self):
        self.host.kill()

    def __call__(self, argv, timeout):
        return self.runner(argv, timeout)


def test_step_timeout_during_pre_svd_restart_is_media_hold(tmp_path, monkeypatch):
    monkeypatch.setattr(cvw, "MIN_RESTART_BUDGET_S", 0.0)  # let the start begin even with ~1 s left
    release = threading.Event()
    host = FakeHost(busy=True)
    seen = []

    def runner(argv, timeout):
        flags = list(argv)[1:]
        seen.append((flags, timeout))
        if flags == [] and host.starts == 1:
            release.wait(10)  # the second (pre-SVD) start hangs past the step deadline
        return host(argv, timeout)

    try:
        res, pipes, _ = _run_with_timeout(tmp_path, monkeypatch, runner_host(host, runner), 1.5)
        assert res.outcome == "MEDIA_HOLD" and "CLIP_STEP_TIMEOUT:1.5s" in res.hold_reason and not res.ready
        assert [b for b, _ in pipes.log] == ["wan_22", "wan_22"]  # SVD never ran
        start_timeouts = [t for f, t in seen if f == []]
        assert len(start_timeouts) == 2 and start_timeouts[1] <= 1.5  # launcher timeout capped by the step deadline
        assert ["-Stop"] in [f for f, _ in seen[-3:]]  # the deadline stops the half-started instance of ours
    finally:
        release.set()


def _run_with_timeout(tmp_path, monkeypatch, host, step_timeout_s):
    from tests.test_chapter_video_comfy_resilience import CrashyPipelines, _probe, validate_presented_social_video
    monkeypatch.setattr(cvw, "validate_presented_social_video",
                        lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(73 / 24), **kw))
    pipes = CrashyPipelines(tmp_path, host, {"wan_22": ["crash", "crash"], "svd_xt_1_1": ["ok"]})
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:t", store_root=tmp_path / "store", still_approved=True, cfg=REUSE,
        pipeline_builder=pipes, comfy_runner=host, queue_probe=idle, sleep=lambda s: None, step_timeout_s=step_timeout_s)
    return res, pipes, host


def test_no_time_left_under_step_deadline_skips_start_and_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(cvw, "MIN_RESTART_BUDGET_S", 10_000.0)  # any real deadline is "too little time"
    host = FakeHost(busy=True)
    res, pipes, _ = _run_with_timeout(tmp_path, monkeypatch, host, 120.0)
    assert res.outcome == "MEDIA_HOLD" and "COMFY_FALLBACK_RESTART_NO_TIME_LEFT" in res.fallback_restart
    assert host.starts == 1 and [b for b, _ in pipes.log] == ["wan_22", "wan_22"]


# ------------------------------------------------------------------ ownership rules for the pre-SVD restart

def test_alive_instance_answering_queue_is_never_restarted_before_svd():
    host = FakeHost(busy=True)
    r = cvw.restart_comfy_before_fallback(DEFAULT, host, lambda u, t: (1, 2), sleep=lambda s: None, owned=True)
    assert r.ok and r.reason == cvw.FALLBACK_NOT_NEEDED and host.stops == 0 and host.starts == 0


def test_foreign_unresponsive_instance_is_never_stopped():
    host = FakeHost(busy=True, ours=False)
    r = cvw.restart_comfy_before_fallback(DEFAULT, host, lambda u, t: None, sleep=lambda s: None, owned=False)
    assert not r.ok and r.reason == "COMFY_FOREIGN_INSTANCE_UNRESPONSIVE_NOT_STOPPED"
    assert host.calls == [["-Status"]] and host.stops == 0 and host.starts == 0


def test_own_unresponsive_instance_is_stopped_via_launcher_then_fresh_start():
    host = FakeHost(busy=True)
    r = cvw.restart_comfy_before_fallback(DEFAULT, host, lambda u, t: None, sleep=lambda s: None, owned=True)
    assert r.ok and r.started_by_us and r.reason == "restarted_before_fallback_via_launcher"
    assert host.calls == [["-Status"], ["-Stop"], ["-Status"], [], ["-Status"]] and host.starts == 1


def test_dead_server_port_free_starts_without_probing_queue():
    host = FakeHost(busy=False)

    def never(u, t):
        raise AssertionError("queue must not be probed when the port is free")

    r = cvw.restart_comfy_before_fallback(DEFAULT, host, never, sleep=lambda s: None, owned=False)
    assert r.ok and host.starts == 1 and host.calls == [["-Status"], [], ["-Status"]]
