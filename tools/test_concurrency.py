"""Workstream B test: HeavyJobLimiter never lets more than max_parallel jobs overlap."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from concurrency import HeavyJobLimiter  # noqa: E402


def main() -> int:
    lim = HeavyJobLimiter(max_parallel=2)
    starts: list[float] = []
    concurrent = 0
    peak = 0
    lock = threading.Lock()

    def job() -> None:
        nonlocal concurrent, peak
        with lim:
            with lock:
                concurrent += 1
                peak = max(peak, concurrent)
            time.sleep(0.2)
            with lock:
                concurrent -= 1
            starts.append(time.time())

    threads = [threading.Thread(target=job) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(starts) == 5, f"expected 5 jobs, got {len(starts)}"
    assert peak <= 2, f"more than 2 jobs overlapped (peak={peak})"
    print(f"OK: 5 jobs ran, max concurrent = {peak} (cap 2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
