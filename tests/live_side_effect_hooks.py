# -*- coding: utf-8 -*-
"""pytest hooks for PYTEST_LIVE_SIDE_EFFECT_ISOLATION (registered once, from either conftest)."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

from tests import live_side_effect_barrier as lsb

lsb.install()

_CONFIG_CRED_NAMES: list[str] = []
_SESSION_FLAGS: dict[str, str] = {}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_network(host, port): allow exactly one host:port for this test only "
        "(PYTEST_LIVE_SIDE_EFFECT_ISOLATION)",
    )
    config.addinivalue_line(
        "markers",
        "requires_inkblade: needs private Inkblade Author Studio sibling data (Studio Bible profiles/"
        "locations, AIVSB reasoning package). Skips with REQUIRES_PRIVATE_INKBLADE_TEST_DATA when the data "
        "is absent; AT_REQUIRE_INKBLADE=1 turns that skip into a hard failure.",
    )
    if not lsb.is_active():
        pytest.exit("PYTEST_LIVE_SIDE_EFFECT_ISOLATION barrier not active at pytest_configure", returncode=2)
    print(f"INKBLADE_MODE simulated_absent={'YES' if lsb.inkblade_simulated_absent() else 'NO'} "
          f"present={'YES' if inkblade_available() else 'NO'} strict={'YES' if _strict() else 'NO'}", flush=True)
    _CONFIG_CRED_NAMES[:] = lsb.external_credential_names()
    _SESSION_FLAGS.update(lsb.flag_state())
    print("SESSION_START_FLAG_STATE " + " ".join(f"{k}={v}" for k, v in sorted(_SESSION_FLAGS.items())), flush=True)
    print(f"PYTHON_EXECUTABLE={sys.executable}", flush=True)
    info = lsb.INSTALL_INFO
    print(f"LIVE_BARRIER_INSTALLED=YES NETWORK_DEFAULT={lsb.NETWORK_DEFAULT} "
          f"LOCALHOST_DEFAULT={lsb.LOCALHOST_DEFAULT} COMFYUI_ACCESS={lsb.COMFYUI_ACCESS}", flush=True)
    print("BARRIER_ACTIVE_BEFORE_TEST_MODULE_IMPORT="
          + ("YES" if info.get("barrier_active_before_test_module_import") else "NO"), flush=True)
    print(f"TEST_PROCESS_EXTERNAL_CREDENTIAL_COUNT={len(_CONFIG_CRED_NAMES)}", flush=True)
    print(f"LIVE_BARRIER_TEMP_ROOT={lsb.TEMP_ROOT}", flush=True)


# ------------------------------------------------------------------ requires_inkblade
REQUIRES_INKBLADE_SKIP_REASON = "REQUIRES_PRIVATE_INKBLADE_TEST_DATA"
_NODE_LIST = Path(__file__).resolve().parent / "fixtures" / "requires_inkblade_nodes.csv"
_INKBLADE_STATS = {"marked": 0, "skipped": 0, "strict_failed": 0}


def _strict() -> bool:
    return os.environ.get("AT_REQUIRE_INKBLADE", "") == "1"


def inkblade_root() -> Path:
    # Derived from the production default (tools/structured_location_authority_r21.DEFAULT_LOCATIONS_YAML):
    # <root>/scripts/aivsb/locations/locations.yaml
    from tools import structured_location_authority_r21 as core
    return Path(core.DEFAULT_LOCATIONS_YAML).parents[3]


def inkblade_available() -> bool:
    if lsb.inkblade_simulated_absent():
        return False
    try:
        return inkblade_root().is_dir()
    except Exception:
        return False


def _marked_nodes() -> set:
    if not _NODE_LIST.exists():
        return set()
    import csv
    with open(_NODE_LIST, encoding="utf-8", newline="") as f:
        return {r["TEST_NODE_ID"] for r in csv.DictReader(f) if r.get("TEST_NODE_ID") and r.get("INKBLADE_DEPENDENCY_PROVEN") == "YES"}


def pytest_collection_modifyitems(session, config, items):
    nodes = _marked_nodes()
    for it in items:
        if it.nodeid in nodes:
            it.add_marker(pytest.mark.requires_inkblade)
    _INKBLADE_STATS["marked"] = sum(1 for it in items if it.get_closest_marker("requires_inkblade"))
    print(f"REQUIRES_INKBLADE_MARKED_COUNT={_INKBLADE_STATS['marked']}", flush=True)


def _access_by_test() -> dict:
    out: dict = {}
    for a in lsb.INKBLADE_ACCESSES:
        t = (a.get("test") or "<collection>").rsplit(" (", 1)[0]
        tail = a.get("path_tail", "").split("/")
        area = "/".join(tail[:-1]) if len(tail) > 1 else tail[0]
        out.setdefault(t, set()).add(area)
    return {k: sorted(v) for k, v in out.items()}


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if item.get_closest_marker("requires_inkblade") and not inkblade_available():
        if _strict():
            _INKBLADE_STATS["strict_failed"] += 1
            pytest.fail("AT_REQUIRE_INKBLADE=1: private Inkblade test data is missing "
                        f"({REQUIRES_INKBLADE_SKIP_REASON})", pytrace=False)
        _INKBLADE_STATS["skipped"] += 1
        pytest.skip(REQUIRES_INKBLADE_SKIP_REASON)


def pytest_collect_file(file_path, parent):
    # Every test module is imported after this point; prove the barrier is live.
    if file_path.suffix == ".py" and file_path.name.startswith("test") and not lsb.is_active():
        raise RuntimeError(f"live barrier inactive while collecting {file_path}")
    return None


@pytest.fixture(autouse=True)
def _live_barrier_allow_network(request):
    """Per-test exact host:port allowance from @pytest.mark.allow_network(host, port)."""
    marks = [m for m in getattr(request.node, "own_markers", []) if m.name == "allow_network"]
    entries = []
    for m in marks:
        if len(m.args) != 2 or m.kwargs:
            raise pytest.UsageError("allow_network takes exactly (host, port)")
        host, port = m.args
        try:
            lsb.validate_allow_entry(host, port)
        except ValueError as exc:
            raise pytest.UsageError(str(exc))
        entries.append((host, port))
    before = lsb.allowed_destinations()
    import contextlib
    with contextlib.ExitStack() as stack:
        for host, port in entries:
            stack.enter_context(lsb.allow_network(host, port))
        yield
    after = lsb.allowed_destinations()
    if after != before:
        lsb.ALLOWLIST_LEAKS.append(sorted(after - before))
        raise RuntimeError(f"network allowance leaked past test: {sorted(after - before)}")


_R21_ENV_CLEARED_AFTER_COLLECTION: list[str] = []


def pytest_collection_finish(session):
    # R21_* bench/harness vars must stay cleared for the run; a test module may setdefault one at
    # import (tests/test_r21_cutover_harness.py sets R21_JOB_MONITOR_LOG to %TEMP%, outside the
    # sandbox). Clear them once collection is done; tests that need one use monkeypatch.
    for k in list(os.environ):
        if k.upper().startswith("R21_"):
            _R21_ENV_CLEARED_AFTER_COLLECTION.append(k)
            del os.environ[k]
    print("R21_ENV_CLEARED_AFTER_COLLECTION=" + ",".join(sorted(_R21_ENV_CLEARED_AFTER_COLLECTION)), flush=True)


def _report(session) -> dict:
    unexpected = lsb.unexpected_attempts()
    allc = lsb.ATTEMPTS
    try:
        from tests import gpu_test_barrier as g
        gpu_hits = g.block_hit_count()
    except Exception:
        gpu_hits = None
    by_kind = Counter(a["kind"] for a in unexpected)
    by_cat = Counter(a.get("category", a["kind"]) for a in unexpected)
    return {
        "install": lsb.INSTALL_INFO,
        "unexpected_attempt_count": len(unexpected),
        "unexpected_by_kind": dict(by_kind),
        "unexpected_by_category": dict(by_cat),
        "unexpected_attempts": unexpected[:500],
        "expected_selftest_attempts": sum(1 for a in allc if a.get("expected")),
        "gpu_test_barrier_block_hits": gpu_hits,
        "credential_names_at_configure": _CONFIG_CRED_NAMES,
        "credential_names_at_finish": lsb.external_credential_names(),
        "stripped_credential_names": lsb.STRIPPED_CREDENTIAL_NAMES,
        "temp_root": str(lsb.TEMP_ROOT),
        "session_start_flag_state": dict(_SESSION_FLAGS),
        "python_executable": sys.executable,
        "allowlist_scope": lsb.ALLOWLIST_SCOPE,
        "allowlist_leak_count": len(lsb.ALLOWLIST_LEAKS),
        "allowlist_active_at_finish": sorted(lsb.allowed_destinations()),
        "r21_env_cleared_after_collection": sorted(_R21_ENV_CLEARED_AFTER_COLLECTION),
        "r21_env_at_finish": sorted(k for k in os.environ if k.upper().startswith("R21_")),
        "inkblade_simulated_absent": lsb.inkblade_simulated_absent(),
        "inkblade_access_count": len(lsb.INKBLADE_ACCESSES),
        "inkblade_accesses": lsb.INKBLADE_ACCESSES[:200],
        "inkblade_access_by_test": _access_by_test(),
        "requires_inkblade": dict(_INKBLADE_STATS, strict=_strict()),
        "exitstatus_before": int(getattr(session, "exitstatus", 0) or 0),
    }


def pytest_sessionfinish(session, exitstatus):
    rep = _report(session)
    out = os.environ.get("AT_LIVE_BARRIER_REPORT")
    if out:
        try:
            Path(out).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
        except Exception as exc:
            print(f"LIVE_BARRIER_REPORT_WRITE_FAILED={type(exc).__name__}", flush=True)
    print(f"\nLIVE_BARRIER_UNEXPECTED_ATTEMPTS={rep['unexpected_attempt_count']} "
          f"BY_KIND={rep['unexpected_by_kind']} BY_CATEGORY={rep['unexpected_by_category']} "
          f"GPU_BARRIER_BLOCK_HITS={rep['gpu_test_barrier_block_hits']} "
          f"EXPECTED_SELFTEST_ATTEMPTS={rep['expected_selftest_attempts']} "
          f"CREDENTIAL_NAMES_AT_FINISH={rep['credential_names_at_finish']} "
          f"ALLOWLIST_LEAK_COUNT={rep['allowlist_leak_count']}", flush=True)
    print(f"INKBLADE_ACCESS_COUNT={rep['inkblade_access_count']} SIMULATED_ABSENT={rep['inkblade_simulated_absent']} "
          f"REQUIRES_INKBLADE={rep['requires_inkblade']}", flush=True)
    if rep["unexpected_attempt_count"]:
        for a in rep["unexpected_attempts"][:50]:
            print(f"LIVE_BARRIER_ATTEMPT kind={a['kind']} dest={a['dest']} where={a['where']} test={a.get('test','')}", flush=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
