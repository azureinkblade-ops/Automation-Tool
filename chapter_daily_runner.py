"""Windows Task Scheduler chapter runner.

Hermes gateway is not the clock. This process:
1. checks/starts the Automation Tool server
2. generates the next local chapter for each novel
3. POSTs /api/daily-chapter-workflow for generate only
4. leaves Patreon and Royal Road gated off. Publish is a separate job.

Hermes chat is used only inside the existing generate adapter.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from chapter_cron_handoff import DAILY_NOVELS, invoke_daily_chapter_workflow, normalize_daily_abbr
from chapter_publish_workflow import live_patreon_allowed, live_royal_road_allowed, next_missing_patreon_chapter

ROOT = Path(r"C:\Users\David\Documents\Automation tool")
HEALTH_URL = "http://127.0.0.1:8765/api/health"
WORKFLOW_STATE_DIR = ROOT / "chapter-workflow-state"
SERVER_CONTROL = ROOT / "tools" / "server_control.py"
CANONICAL_PYTHON = ROOT / ".venv-gpu" / "Scripts" / "python.exe"
LOG_PATH = ROOT / "logs" / "chapter_daily_runner.log"
RUNNER_MUTEX_NAME = r"Local\AzureInkbladeChapterDailyRunner"
SERVER_START_MUTEX_NAME = r"Local\AzureInkbladeChapterDailyServerStart"
WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED = 0x00000080
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def parse_novels(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not values:
        return ("EN",)
    out: list[str] = []
    for raw in values:
        for part in str(raw).replace(",", " ").split():
            code = normalize_daily_abbr(part)
            if code not in DAILY_NOVELS:
                raise ValueError(f"Unsupported daily novel abbr: {part}")
            if code not in out:
                out.append(code)
    return tuple(out)


def default_novels(env: dict[str, str] | None = None) -> tuple[str, ...]:
    source = env if env is not None else os.environ
    raw = str(source.get("CHAPTER_DAILY_NOVELS", "EN")).strip()
    if not raw:
        return ("EN",)
    return parse_novels([raw])


def live_remotes_requested(env: dict[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return live_patreon_allowed(source) or live_royal_road_allowed(source)


def apply_runner_remote_gate(env: dict[str, str]) -> dict[str, str]:
    """This runner never publishes. Inherited live flags cannot leak in."""
    out = dict(env)
    out["CHAPTER_LIVE_PATREON"] = "0"
    out["CHAPTER_LIVE_ROYAL_ROAD"] = "0"
    out["CHAPTER_LIVE_PUBLISH"] = "0"
    return out


def lock_path(root: Path | None = None) -> Path:
    base = root if root is not None else ROOT
    return base / "chapter_daily_runner.lock"


def select_due_work(
    *,
    latest_written: int,
    saved_chapters: list[int] | set[int],
    patreon_complete: list[int] | set[int],
    remotes_allowed: bool,
) -> dict[str, Any]:
    """Generate is independent of Patreon/Royal Road.

    A missing Patreon chapter is reported as patreonBacklog only. This runner
    never uploads. remotes_allowed is kept for the execute-path refuse check.
    """
    del remotes_allowed
    backlog = next_missing_patreon_chapter(saved_chapters, patreon_complete)
    return {
        "action": "generate",
        "patreonBacklog": backlog,
        "nextChapter": int(latest_written) + 1,
    }


def should_invoke_workflow(work: dict[str, Any]) -> bool:
    return work.get("action") == "generate"


class NamedMutex:
    def __init__(self, name: str):
        self.name = name
        self.handle = None

    def acquire(self, timeout_ms: int = 0) -> bool:
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise OSError(f"CreateMutexW failed err={ctypes.get_last_error()}")
        self.handle = handle
        waited = kernel32.WaitForSingleObject(handle, int(timeout_ms))
        if waited in (WAIT_OBJECT_0, WAIT_ABANDONED):
            return True
        return False

    def release(self) -> None:
        handle = self.handle
        self.handle = None
        if not handle:
            return
        try:
            kernel32.ReleaseMutex(handle)
        finally:
            kernel32.CloseHandle(handle)


def acquire_named_mutex(name: str, timeout_ms: int = 0) -> NamedMutex | None:
    mutex = NamedMutex(name)
    if mutex.acquire(timeout_ms=timeout_ms):
        return mutex
    mutex.release()
    return None


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}


def health_ok(timeout: float = 8.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict) and payload.get("ok"):
        return payload
    return None


def ensure_server(
    timeout_seconds: int = 90,
    *,
    health_fn: Callable[[], dict[str, Any] | None] | None = None,
    start_fn: Callable[[], None] | None = None,
    mutex_name: str = SERVER_START_MUTEX_NAME,
) -> dict[str, Any]:
    probe = health_fn or health_ok
    existing = probe()
    if existing is not None:
        return {"started": False, "reused": True, "health": existing}
    mutex = acquire_named_mutex(mutex_name, timeout_ms=120_000)
    if mutex is None:
        raise RuntimeError("could not acquire server start mutex")
    try:
        existing = probe()
        if existing is not None:
            return {"started": False, "reused": True, "health": existing}

        def _start() -> None:
            if not CANONICAL_PYTHON.is_file():
                raise RuntimeError(f"canonical interpreter missing: {CANONICAL_PYTHON}")
            subprocess.Popen(
                [str(CANONICAL_PYTHON), str(SERVER_CONTROL), "--port", "8765", "--no-open"],
                cwd=str(ROOT),
                env=_clean_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        starter = start_fn or _start
        starter()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            health = probe()
            if health is not None:
                return {"started": True, "reused": False, "health": health}
            time.sleep(0.05 if start_fn is not None else 2)
        raise RuntimeError("Automation Tool server did not become healthy")
    finally:
        mutex.release()


def local_chapter_state(root: Path, abbr: str) -> dict[str, Any]:
    code = normalize_daily_abbr(abbr)
    saved: list[int] = []
    complete: list[int] = []
    latest = 0
    state_dir = root / "chapter-workflow-state"
    if state_dir.is_dir():
        for path in state_dir.glob(f"{code}-*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            number = int(data.get("chapterNumber") or 0)
            if number <= 0:
                continue
            latest = max(latest, number)
            if data.get("saved"):
                saved.append(number)
            if data.get("innerDiscipleUploaded") and data.get("pathInitiateUploaded"):
                complete.append(number)
    return {
        "saved": sorted(set(saved)),
        "complete": sorted(set(complete)),
        "latestWritten": latest,
    }


def run_novel(
    abbr: str,
    *,
    execute: bool,
    remotes_allowed: bool,
    root: Path | None = None,
    invoke: Callable[..., dict[str, Any]] | None = None,
    latest_written: int | None = None,
    saved_chapters: list[int] | None = None,
    patreon_complete: list[int] | None = None,
) -> dict[str, Any]:
    code = normalize_daily_abbr(abbr)
    base = root if root is not None else ROOT
    local = local_chapter_state(base, code)
    saved = saved_chapters if saved_chapters is not None else local["saved"]
    complete = patreon_complete if patreon_complete is not None else local["complete"]
    written = latest_written if latest_written is not None else local["latestWritten"]
    if written <= 0:
        raise RuntimeError(f"no local written chapter state for {code}")
    work = select_due_work(
        latest_written=written,
        saved_chapters=saved,
        patreon_complete=complete,
        remotes_allowed=remotes_allowed,
    )
    result: dict[str, Any] = {
        "novel": code,
        "selectedNovel": code,
        "selectedAction": work["action"],
        "patreonBacklog": work["patreonBacklog"],
        "nextChapter": work["nextChapter"],
        "oldestPatreonIncompleteChapter": work["patreonBacklog"],
        "latestWritten": written,
        "workflowMutation": "none",
        "workflowCalls": 0,
        "CLOCK": "windows-task-scheduler",
        "HERMES_GATEWAY_REQUIRED": False,
        "LIVE_REMOTES": False,
    }
    if remotes_allowed:
        raise RuntimeError("remote publishing is not part of the Windows runner default path")
    if not should_invoke_workflow(work):
        return result
    caller = invoke or invoke_daily_chapter_workflow
    payload = caller(code, dry_run=not execute, timeout=3600 if execute else 120)
    result.update(payload)
    result["selectedAction"] = work["action"]
    result["workflowMutation"] = "generate" if execute else "dry-run"
    result["workflowCalls"] = 1
    return result


def _sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(report, default=str))
    for item in clone.get("results") or []:
        if isinstance(item, dict):
            item.pop("chapterText", None)
            record = item.get("record")
            if isinstance(record, dict):
                record.pop("chapterText", None)
    return clone


def write_report(report: dict[str, Any]) -> None:
    text = json.dumps(_sanitize_report(report), indent=2, default=str)
    print(text)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Windows-scheduled durable chapter runner")
    parser.add_argument("--novels", nargs="+", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mutex-name", default=RUNNER_MUTEX_NAME)
    args = parser.parse_args(argv)
    novels = parse_novels(args.novels) if args.novels else default_novels()
    execute = bool(args.execute) and not bool(args.dry_run)
    env = apply_runner_remote_gate(dict(os.environ))
    remotes = live_remotes_requested(env)
    report: dict[str, Any] = {
        "ok": True,
        "novels": list(novels),
        "execute": execute,
        "liveRemotes": remotes,
        "clock": "windows-task-scheduler",
        "lockHeld": False,
        "results": [],
    }
    if remotes:
        report["ok"] = False
        report["error"] = "LIVE_REMOTES_NOT_AUTHORIZED_ON_WINDOWS_RUNNER"
        write_report(report)
        return 2
    mutex = acquire_named_mutex(str(args.mutex_name), timeout_ms=0)
    if mutex is None:
        report["ok"] = True
        report["lockHeld"] = True
        report["selectedAction"] = "lock_held"
        report["workflowMutation"] = "none"
        write_report(report)
        return 0
    try:
        report["server"] = ensure_server()
        for abbr in novels:
            report["results"].append(run_novel(abbr, execute=execute, remotes_allowed=False))
        if report["results"]:
            first = report["results"][0]
            report["selectedNovel"] = first.get("selectedNovel")
            report["selectedAction"] = first.get("selectedAction")
            report["patreonBacklog"] = first.get("patreonBacklog")
            report["workflowMutation"] = first.get("workflowMutation")
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        write_report(report)
        return 1
    finally:
        mutex.release()
    write_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
