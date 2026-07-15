from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = int(os.environ.get("AUTOMATION_TOOL_PORT", "8765"))
HEALTH_PATH = "/api/health"
REPORT_PATH = ROOT / "automation-server-launch.json"
SERVER_LOG_DIR = ROOT / "server-logs"
LEGACY_OUT_LOG = ROOT / "automation-server.out.log"
LEGACY_ERR_LOG = ROOT / "automation-server.err.log"

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def bundled_python() -> Path:
    candidate = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "python.exe"
    if candidate.exists():
        return candidate
    return Path(sys.executable)


def listener_pids(port: int) -> list[int]:
    run = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[int] = set()
    needle = f":{port}"
    for line in run.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if needle not in parts[1]:
            continue
        if parts[-2].upper() != "LISTENING":
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid != os.getpid():
            pids.add(pid)
    return sorted(pids)


def stop_process(pid: int) -> dict[str, Any]:
    run = subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "pid": pid,
        "ok": run.returncode == 0,
        "stdout": run.stdout.strip(),
        "stderr": run.stderr.strip(),
    }


def read_health(port: int, timeout: float = 2.0) -> dict[str, Any] | None:
    url = f"http://127.0.0.1:{port}{HEALTH_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = response.read().decode("utf-8")
            data = json.loads(payload)
            return data if isinstance(data, dict) else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def current_source_mtime() -> str:
    app_path = ROOT / "app.py"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(app_path.stat().st_mtime))


def health_matches_current_app(health: dict[str, Any] | None, port: int) -> bool:
    if not health:
        return False
    if int(health.get("port") or 0) != port:
        return False
    if str(health.get("cwd") or "").lower() != str(ROOT).lower():
        return False
    return str(health.get("sourceMtimeAtStart") or "") == current_source_mtime()


def wait_for_health(port: int, timeout_seconds: int = 45) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        health = read_health(port, timeout=2.0)
        if health:
            return health
        time.sleep(0.5)
    return None


def start_server(port: int) -> dict[str, Any]:
    python_exe = bundled_python()
    env = dict(os.environ)
    env["AUTOMATION_TOOL_PORT"] = str(port)
    env.setdefault("PYTHONUNBUFFERED", "1")
    # Strip any leaked PYTHONPATH/PYTHONHOME from a parent shell (e.g. an agent venv
    # with a broken PIL build) so the child interpreter resolves its own packages and
    # `import diffusers` does not crash into a Pexels/Pixabay fallback. app.py also
    # self-defends, but the launcher is the canonical entry point from start.bat.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    SERVER_LOG_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_log = SERVER_LOG_DIR / f"automation-server-{stamp}.out.log"
    err_log = SERVER_LOG_DIR / f"automation-server-{stamp}.err.log"
    out_handle = out_log.open("ab")
    err_handle = err_log.open("ab")
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW
    creation_mode = "detached-breakaway"
    try:
        try:
            process = subprocess.Popen(
                [str(python_exe), "app.py"],
                cwd=str(ROOT),
                env=env,
                stdout=out_handle,
                stderr=err_handle,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=False,
            )
        except PermissionError:
            creation_mode = "detached"
            process = subprocess.Popen(
                [str(python_exe), "app.py"],
                cwd=str(ROOT),
                env=env,
                stdout=out_handle,
                stderr=err_handle,
                stdin=subprocess.DEVNULL,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                close_fds=False,
            )
    finally:
        out_handle.close()
        err_handle.close()
    return {
        "pid": process.pid,
        "python": str(python_exe),
        "outLog": str(out_log),
        "errLog": str(err_log),
        "creationMode": creation_mode,
    }


def tail_file(path: str | Path, limit: int = 4000) -> str:
    target = Path(path)
    if not target.exists():
        return ""
    try:
        return target.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def open_app(port: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/"
    debug_url = f"http://127.0.0.1:9222/json/new?{urllib.parse.quote(url, safe=':/')}"
    try:
        request = urllib.request.Request(debug_url, method="PUT")
        with urllib.request.urlopen(request, timeout=2) as response:
            return {"ok": True, "method": "chrome-debug-put", "status": response.status, "url": url}
    except Exception:
        try:
            with urllib.request.urlopen(debug_url, timeout=2) as response:
                return {"ok": True, "method": "chrome-debug-get", "status": response.status, "url": url}
        except Exception as exc:
            subprocess.Popen(["cmd", "/c", "start", "", url], cwd=str(ROOT), creationflags=CREATE_NO_WINDOW)
            return {"ok": True, "method": "default-browser", "url": url, "debugError": str(exc)}


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start and verify the Azure Inkblade Automation Tool server.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--force", action="store_true", help="Stop existing listeners even if health looks current.")
    parser.add_argument("--open", action="store_true", help="Open the app after the server is healthy.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the app.")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "port": args.port,
        "root": str(ROOT),
        "sourceMtime": current_source_mtime(),
        "stopped": [],
        "started": None,
        "health": None,
        "opened": None,
        "ok": False,
        "message": "",
    }

    existing_health = read_health(args.port)
    if not args.force and health_matches_current_app(existing_health, args.port):
        report["health"] = existing_health
        report["ok"] = True
        report["message"] = "Automation Tool server is already running current code."
        if args.open and not args.no_open:
            report["opened"] = open_app(args.port)
        write_report(report)
        print(json.dumps(report, indent=2))
        return 0

    for pid in listener_pids(args.port):
        report["stopped"].append(stop_process(pid))
    time.sleep(0.75)
    remaining = listener_pids(args.port)
    if remaining:
        report["remainingPids"] = remaining
        report["health"] = read_health(args.port)
        report["ok"] = False
        report["message"] = (
            "A previous Automation Tool server is still using this port and could not be stopped. "
            "Close the old launcher/server window or run the launcher as Administrator, then try again."
        )
        write_report(report)
        print(json.dumps(report, indent=2))
        return 1

    report["started"] = start_server(args.port)
    health = wait_for_health(args.port)
    report["health"] = health
    if not health_matches_current_app(health, args.port):
        report["ok"] = False
        report["message"] = "Automation Tool server did not become healthy with the current app code."
        started = report.get("started") if isinstance(report.get("started"), dict) else {}
        report["stdoutTail"] = tail_file(started.get("outLog") or LEGACY_OUT_LOG)
        report["stderrTail"] = tail_file(started.get("errLog") or LEGACY_ERR_LOG)
        write_report(report)
        print(json.dumps(report, indent=2))
        return 1

    live_pids = listener_pids(args.port)
    report["livePids"] = live_pids
    if len(live_pids) != 1:
        report["message"] = f"Automation Tool is healthy, but {len(live_pids)} listeners are present."
    else:
        report["message"] = "Automation Tool server is healthy."
    report["ok"] = True
    if args.open and not args.no_open:
        report["opened"] = open_app(args.port)
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
