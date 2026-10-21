"""Shared Hermes daily-chapter CRON handoff.

One automated production path: POST /api/daily-chapter-workflow
Manual prompt/import remains recovery-only.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

DAILY_NOVELS = ("EN", "HA", "SF", "HP")
UNIFIED_WORKFLOW_PATH = "/api/daily-chapter-workflow"
UNIFIED_WORKFLOW_URL = "http://127.0.0.1:8765/api/daily-chapter-workflow"
AUTOMATED_PRODUCTION_ROUTE = UNIFIED_WORKFLOW_PATH
MANUAL_RECOVERY_ROUTES = (
    "/api/manual-next-chapter-prompt",
    "/api/import-manual-chapter",
    "/api/create-next-chapter",
    "/api/write-chapter",
)


def normalize_daily_abbr(abbr: str) -> str:
    text = str(abbr or "").strip().upper()
    aliases = {"HFP": "HP", "HUNDREDFOLD": "HP", "HUNDREDFOLD_PATH": "HP"}
    return aliases.get(text, text)


def cron_daily_request(abbr: str, *, dry_run: bool = True) -> dict[str, Any]:
    code = normalize_daily_abbr(abbr)
    if code not in DAILY_NOVELS:
        raise ValueError(f"Unsupported daily novel abbr: {abbr}")
    return {
        "path": UNIFIED_WORKFLOW_PATH,
        "url": UNIFIED_WORKFLOW_URL,
        "method": "POST",
        "json": {"abbr": code, "dryRun": bool(dry_run)},
        "automated": True,
        "manualRecovery": False,
    }


def cron_daily_prompt(abbr: str) -> str:
    code = normalize_daily_abbr(abbr)
    names = {
        "EN": "Eternal Nexus",
        "HA": "Heavenly Ascension System",
        "SF": "Soul Forge Era",
        "HP": "Hundredfold Path",
    }
    return (
        f"Run the unified daily chapter workflow for {code} ({names.get(code, code)}).\n"
        "Do not write chapter prose yourself.\n"
        "Do not call /api/manual-next-chapter-prompt.\n"
        "Do not call /api/import-manual-chapter.\n"
        "Do not call /api/create-next-chapter.\n"
        f"POST {UNIFIED_WORKFLOW_URL} with JSON {{\"abbr\":\"{code}\",\"dryRun\":true}}.\n"
        "Keep Patreon and Royal Road non-live. Do not set CHAPTER_LIVE_PUBLISH.\n"
        "Report the preview fields from the response."
    )


def all_daily_cron_requests(*, dry_run: bool = True) -> dict[str, dict[str, Any]]:
    return {abbr: cron_daily_request(abbr, dry_run=dry_run) for abbr in DAILY_NOVELS}


def invoke_daily_chapter_workflow(
    abbr: str,
    *,
    dry_run: bool = True,
    transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """CRON entry. Default transport is HTTP POST to the unified API."""
    request = cron_daily_request(abbr, dry_run=dry_run)
    if transport is not None:
        result = transport(request)
        if not isinstance(result, dict):
            result = {"raw": result}
        result.setdefault("cronRequest", request)
        result["UNIFIED_WORKFLOW_REACHED"] = True
        result["CRON_TRIGGERED"] = True
        return result
    data = json.dumps(request["json"]).encode("utf-8")
    req = urllib.request.Request(
        request["url"],
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "workflowStatus": "BLOCKED_SERVER_UNREACHABLE",
            "cronRequest": request,
            "UNIFIED_WORKFLOW_REACHED": False,
        }
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    payload["cronRequest"] = request
    payload["UNIFIED_WORKFLOW_REACHED"] = True
    payload["CRON_TRIGGERED"] = True
    return payload


def cron_dry_run_default() -> bool:
    flag = str(os.environ.get("CHAPTER_WORKFLOW_CRON_EXECUTE", "0")).strip().lower()
    return flag in {"", "0", "false", "no", "off"}
