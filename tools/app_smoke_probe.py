from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8765"


ENDPOINTS = [
    ("/", "routine"),
    ("/api/health", "routine"),
    ("/api/settings", "routine"),
    ("/api/database-status", "routine"),
    ("/api/active-chapter-path", "routine"),
    ("/api/daily-youtube-status", "routine"),
    ("/api/approval-inbox", "routine"),
    ("/api/pack-health?limit=10&fast=1", "routine"),
    ("/api/pack-health?limit=30&fast=1", "routine"),
    ("/api/pack-control", "routine"),
    ("/api/growth-control-center?refresh=0", "routine"),
    ("/api/deep-tiktok-packs?limit=8&fast=1", "routine"),
    ("/api/story-hook-video-packs?limit=20&fast=1", "routine"),
    ("/api/manual-video-packs", "routine"),
    ("/api/provider-strategy", "routine"),
    ("/api/analytics-lab", "routine"),
    ("/api/predictive-growth-plan", "routine"),
    ("/api/instagram-growth-blueprint", "routine"),
    ("/api/youtube-end-screen-plan?limit=10", "routine"),
    ("/api/chapter-release-upload-queue?refresh=0", "routine"),
    ("/api/pack-health?limit=10&fast=0", "stress"),
    ("/api/growth-control-center?refresh=1", "stress"),
    ("/api/chapter-release-upload-queue?refresh=1", "stress"),
]


def probe(endpoint: str, kind: str = "routine", timeout: int = 30) -> dict[str, object]:
    started = time.perf_counter()
    status = None
    size = 0
    content_type = ""
    error = ""
    json_ok = None
    try:
        with urllib.request.urlopen(BASE_URL + endpoint, timeout=timeout) as response:
            payload = response.read()
            status = response.status
            size = len(payload)
            content_type = response.headers.get("Content-Type", "")
            if endpoint.startswith("/api"):
                json_ok = False
                try:
                    json.loads(payload.decode("utf-8"))
                    json_ok = True
                except Exception as exc:
                    error = f"Invalid JSON: {exc}"
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    return {
        "endpoint": endpoint,
        "kind": kind,
        "status": status,
        "seconds": round(elapsed, 3),
        "kb": round(size / 1024, 1),
        "contentType": content_type,
        "jsonOk": json_ok,
        "slow": elapsed >= 3,
        "error": error,
    }


def main() -> int:
    results = [probe(endpoint, kind) for endpoint, kind in ENDPOINTS]
    routine_failures = [
        item for item in results
        if item["kind"] == "routine" and (item["error"] or item["status"] not in {200, None})
    ]
    report = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": not routine_failures,
        "slow": [item for item in results if item["slow"]],
        "failed": routine_failures,
        "stress": [item for item in results if item["kind"] == "stress"],
        "results": results,
    }
    path = ROOT / "app-smoke-report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
