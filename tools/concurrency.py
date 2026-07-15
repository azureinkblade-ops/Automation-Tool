"""Workstream B: central semaphore for heavy jobs (diffusers image-gen + ffmpeg video render).

The app is a ThreadingHTTPServer, so concurrent HTTP calls each spawn a ~4-5 GB worker
(diffusers) or an ffmpeg render. Without a cap, several simultaneous Build-All-Posts / image
requests spike total RAM to ~8+ GB and destabilize the machine. This module provides a single
process-wide limiter so at most MAX_CONCURRENT_HEAVY_JOBS heavy jobs run at once.

Usage (context manager):
    from tools.concurrency import HeavyJobLimiter
    with HeavyJobLimiter():
        ... heavy subprocess spawn ...

The limit is read from the MAX_CONCURRENT_HEAVY_JOBS env var (default 2). Set to 1 if the
machine still spikes under concurrent load; raise only on a machine with headroom.
"""
from __future__ import annotations

import os
import threading

DEFAULT_MAX_HEAVY_JOBS = int(os.environ.get("MAX_CONCURRENT_HEAVY_JOBS", "2"))


class HeavyJobLimiter:
    """Process-wide semaphore gating heavy subprocess spawns (diffusers / ffmpeg).

    Reentrant-safe per-thread is not required; the same thread should not nest heavy jobs.
    """

    _lock = threading.Lock()
    _instance: "HeavyJobLimiter | None" = None

    def __init__(self, max_parallel: int | None = None) -> None:
        self._max = max_parallel or DEFAULT_MAX_HEAVY_JOBS
        if self._max < 1:
            self._max = 1
        self._sem = threading.Semaphore(self._max)

    def __enter__(self) -> "HeavyJobLimiter":
        self._sem.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self._sem.release()

    @property
    def max_parallel(self) -> int:
        return self._max

    @classmethod
    def instance(cls) -> "HeavyJobLimiter":
        """Shared singleton so every heavy spawn site counts against the SAME cap."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
