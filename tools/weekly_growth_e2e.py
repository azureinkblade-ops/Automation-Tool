from __future__ import annotations

import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def request_json(url: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    app.load_env_file()
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks: list[dict[str, object]] = []
    try:
        with urllib.request.urlopen(base + "/", timeout=10) as response:
            html = response.read().decode("utf-8")
        checks.append({"name": "weekly_growth_ui_live", "ok": 'id="weeklyGrowthBuildBtn"' in html})
        plan = request_json(base + "/api/weekly-growth-planner", {
            "weekStart": "2026-07-13",
            "weights": {"HA": 2, "EN": 1, "HP": 1, "SF": 1},
        })
        checks.append({"name": "weekly_growth_post_live", "ok": plan.get("planId") == "growth-2026-07-13" and len(plan.get("slots") or []) == 7})
        checks.append({"name": "weekly_growth_path_isolation_live", "ok": bool((plan.get("pathIsolation") or {}).get("verified"))})
        dashboard = request_json(base + "/api/weekly-growth-planner?weekStart=2026-07-13")
        checks.append({"name": "weekly_growth_get_live", "ok": (dashboard.get("plan") or {}).get("planId") == plan.get("planId")})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    failed = [item for item in checks if not item["ok"]]
    print(json.dumps({"ok": not failed, "failed": len(failed), "checks": checks}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
