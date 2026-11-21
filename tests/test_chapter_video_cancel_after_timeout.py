"""After the step deadline the abandoned worker is cancelled: no launcher, no restart, no ComfyUI submit. CPU only.

``produce_chapter_clip`` returns MEDIA_HOLD (CLIP_STEP_TIMEOUT) at the deadline and sets a cancel Event. These
tests hold the worker past the deadline, release it, wait for it to finish, and check that nothing ran after
the timeout except the main thread's own -Stop. ComfyUI is never launched: FakeHost stands in for the launcher.
"""
from __future__ import annotations

import threading

from tests.test_chapter_video_comfy_resilience import REUSE, CrashyPipelines, FakeHost, idle
from tests.test_chapter_video_wiring import _probe, _still
from tools import chapter_video_wiring as cvw
from tools.media_validity import validate_presented_social_video


class Recorder:
    """Wraps a FakeHost; records each launcher call with whether it ran before or after the timeout."""

    def __init__(self, host, gate_on=None):
        self.host, self.gate_on = host, gate_on  # gate_on(flags, host) -> True: block this call until released
        self.timed_out = threading.Event()
        self.release = threading.Event()
        self.blocked = threading.Event()
        self.log = []  # (flags, after_timeout, thread_name)

    def kill(self):
        self.host.kill()

    def __call__(self, argv, timeout):
        flags = list(argv)[1:]
        self.log.append((flags, self.timed_out.is_set(), threading.current_thread().name))
        if self.gate_on and self.gate_on(flags, self.host) and not self.blocked.is_set():
            self.blocked.set()
            self.release.wait(10)
        return self.host(argv, timeout)

    def worker_calls_after_timeout(self):
        return [f for f, after, name in self.log if after and name.startswith("chapter-clip-")]


class GatedPipelines(CrashyPipelines):
    """CrashyPipelines whose first submit blocks until released; records submits made after the timeout."""

    def __init__(self, tmp_path, rec, script, block_first=True):
        super().__init__(tmp_path, rec, script)
        self.rec, self.block_first, self.after = rec, block_first, []

    def __call__(self, backend):
        inner = super().__call__(backend)
        outer = self

        class P:
            def produce_social_media(self, still, *, workflow_id, seed):
                if outer.rec.timed_out.is_set():
                    outer.after.append((backend, workflow_id))
                if outer.block_first and len(outer.log) == 0:
                    outer.rec.blocked.set()
                    outer.rec.release.wait(10)
                return inner.produce_social_media(still, workflow_id=workflow_id, seed=seed)

        return P()


def _go(tmp_path, monkeypatch, rec, pipes, limit=1.0):
    monkeypatch.setattr(cvw, "validate_presented_social_video",
                        lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(73 / 24), **kw))
    monkeypatch.setattr(cvw, "MIN_RESTART_BUDGET_S", 0.0)
    before = set(threading.enumerate())
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:t", store_root=tmp_path / "store", still_approved=True, cfg=REUSE,
        pipeline_builder=pipes, comfy_runner=rec, queue_probe=idle, sleep=lambda s: None, step_timeout_s=limit)
    rec.timed_out.set()
    workers = [t for t in threading.enumerate() if t not in before and t.name.startswith("chapter-clip-")]
    rec.release.set()
    for t in workers:
        t.join(10)
    assert all(not t.is_alive() for t in workers), "abandoned worker did not finish after release"
    return res


def test_timeout_during_wan_then_crash_no_restart_no_retry_no_svd(tmp_path, monkeypatch):
    rec = Recorder(FakeHost(busy=True))
    pipes = GatedPipelines(tmp_path, rec, {"wan_22": ["crash", "ok"], "svd_xt_1_1": ["ok"]})
    res = _go(tmp_path, monkeypatch, rec, pipes)
    assert res.outcome == "MEDIA_HOLD" and "CLIP_STEP_TIMEOUT" in res.hold_reason and not res.ready
    # the blocked Wan job then "crashed" ComfyUI: without the cancel flag the worker would -Status, start, retry
    assert rec.worker_calls_after_timeout() == []
    assert rec.host.starts == 0
    assert pipes.after == [] and [b for b, _ in pipes.log] == ["wan_22"]


def test_timeout_during_pre_svd_restart_never_starts_launcher_or_submits_svd(tmp_path, monkeypatch):
    # Wan crashes twice (crash restart = start #1); the pre-SVD restart's -Status blocks past the deadline
    def gate(flags, host):
        return flags == ["-Status"] and host.starts == 1 and not host.busy

    rec = Recorder(FakeHost(busy=True), gate_on=gate)
    pipes = GatedPipelines(tmp_path, rec, {"wan_22": ["crash", "crash"], "svd_xt_1_1": ["ok"]}, block_first=False)
    res = _go(tmp_path, monkeypatch, rec, pipes)
    assert rec.blocked.is_set(), "test did not reach the pre-SVD restart"
    assert res.outcome == "MEDIA_HOLD" and "CLIP_STEP_TIMEOUT" in res.hold_reason
    assert rec.worker_calls_after_timeout() == []  # no start, no -Status, no -Stop from the abandoned worker
    assert rec.host.starts == 1  # only the crash restart that happened before the deadline
    assert pipes.after == [] and "svd_xt_1_1" not in [b for b, _ in pipes.log]


def test_timeout_during_crash_restart_start_no_wan_retry(tmp_path, monkeypatch):
    # first Wan attempt crashes; the crash-restart START blocks past the deadline -> no -Status recheck, no retry
    def gate(flags, host):
        return flags == []

    rec = Recorder(FakeHost(busy=True), gate_on=gate)
    pipes = GatedPipelines(tmp_path, rec, {"wan_22": ["crash", "ok"], "svd_xt_1_1": ["ok"]}, block_first=False)
    res = _go(tmp_path, monkeypatch, rec, pipes)
    assert rec.blocked.is_set() and res.outcome == "MEDIA_HOLD"
    assert rec.worker_calls_after_timeout() == []
    assert pipes.after == [] and [b for b, _ in pipes.log] == ["wan_22"]
    # the deadline handler (main thread, not the worker) issued -Stop for the in-flight start of ours
    assert [f for f, _after, name in rec.log if not name.startswith("chapter-clip-")] == [["-Stop"]]


def test_cancelled_before_start_runs_nothing(tmp_path):
    host = FakeHost(busy=False)
    pipes = CrashyPipelines(tmp_path, host, {"wan_22": ["ok"], "svd_xt_1_1": ["ok"]})
    ev = threading.Event()
    ev.set()
    res = cvw._produce_chapter_clip_inner(
        _still(tmp_path), workflow_id="w", store_root=tmp_path, still_approved=True, cfg=REUSE,
        pipeline_builder=pipes, comfy_runner=host, queue_probe=idle, sleep=lambda s: None, _state={"cancel": ev})
    assert res.outcome == "MEDIA_HOLD" and cvw.CLIP_STEP_CANCELLED in res.hold_reason
    assert host.calls == [] and pipes.log == []


def test_guarded_runner_blocks_restart_helpers_once_cancelled(tmp_path):
    """Cancel set between the guard and a restart: restart_comfy_if_gone / the pre-SVD restart get a refusing
    runner and never reach the launcher (they turn the exception into not-ok)."""
    host = FakeHost(busy=False)
    ev = threading.Event()
    pipes_calls = []

    class Pipes:
        def __call__(self, backend):
            class P:
                def produce_social_media(self, still, *, workflow_id, seed):
                    pipes_calls.append(backend)
                    ev.set()  # deadline fires while Wan is running
                    raise ConnectionError("ComfyUI died")
            return P()

    res = cvw._produce_chapter_clip_inner(
        _still(tmp_path), workflow_id="w", store_root=tmp_path, still_approved=True, cfg=REUSE,
        pipeline_builder=Pipes(), comfy_runner=host, queue_probe=idle, sleep=lambda s: None, _state={"cancel": ev})
    assert res.outcome == "MEDIA_HOLD" and pipes_calls == ["wan_22"]
    assert host.calls == [["-Status"], [], ["-Status"]]  # only the guard's start before the deadline
    assert any(a.get("outcome") == cvw.CLIP_STEP_CANCELLED for a in res.attempts)
