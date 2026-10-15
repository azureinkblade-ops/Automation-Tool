"""Single-process token and request preflight; no issue or Docker capability."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tests.hermes_core.test_ea4e92jv_agent_local_kilo_network_issue_request import _build
from tests.hermes_core.test_ea4e92ki_network_request_candidate import (
    CSC, JSON_DLL, SYSTEM_CORE_DLL, SYSTEM_DLL,
)
from tools.hermes_core.agent_local_docker_operator_token import (
    _read_current_windows_token,
)
from tools.hermes_core.hashing import canonical_json, sha256_payload


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def candidate(tmp_path_factory):
    if (sys.platform != "win32" or not CSC.is_file() or
            not JSON_DLL.is_file() or not SYSTEM_DLL.is_file() or
            not SYSTEM_CORE_DLL.is_file()):
        pytest.skip("Windows .NET Framework candidate dependencies unavailable")
    target = tmp_path_factory.mktemp("network-preflight") / "preflight.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/noconfig", "/target:exe",
         "/main:Ea4eNetworkIssuePreflightCandidate", f"/out:{target}",
         f"/reference:{JSON_DLL}", f"/reference:{SYSTEM_DLL}",
         f"/reference:{SYSTEM_CORE_DLL}",
         str(ROOT / "tools" / "ea4e_docker_operator_preflight.cs"),
         str(ROOT / "tools" / "Ea4eNetworkIssueRequestCandidate.cs"),
         str(ROOT / "tools" / "Ea4eNetworkIssuePreflightCandidate.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.fixture
def request_path(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    start, values, spec, _, _, _ = setup(source)
    sid, _ = _read_current_windows_token()
    try:
        request = _build(values, spec, operator_id=sid)
    finally:
        start.close()
    path = tmp_path / "request.json"
    path.write_bytes(canonical_json(request).encode())
    return request, path


def run(candidate, request, path, sid):
    labels = request["labels"]
    args = [
        sid, path, request["request_hash"], request["governing_commit"],
        request["docker_executable_sha256"], request["attempt_id"],
        request["operator_id"], request["network_name"],
        labels["hermes.ea4e.attempt"],
        labels["hermes.ea4e.candidate_sha256"],
        labels["hermes.ea4e.profile"],
        labels["hermes.ea4e.cleanup_owner"],
    ]
    return subprocess.run(
        [str(candidate), *map(str, args)], capture_output=True, text=True,
        timeout=10, check=False,
    )


def test_actual_token_and_request(candidate, request_path):
    request, path = request_path
    sid, elevated = _read_current_windows_token()
    result = run(candidate, request, path, sid)
    assert result.returncode == (0 if elevated else 1)
    assert result.stdout.strip() == (
        "MATCH:NON_AUTHORIZING_PREFLIGHT" if elevated else
        "DENY:OPERATOR_TOKEN_NOT_ELEVATED"
    )


def test_wrong_sid_denied_before_request_read(candidate, request_path):
    request, path = request_path
    missing = path.with_name("never-created.json")
    request["operator_id"] = "S-1-5-21-0-0-0-9999"
    request["request_hash"] = sha256_payload({
        key: value for key, value in request.items() if key != "request_hash"
    })
    result = run(candidate, request, missing, "S-1-5-21-0-0-0-9999")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:OPERATOR_SID_MISMATCH"


def test_unbound_operator_denied(candidate, request_path):
    request, path = request_path
    sid, _ = _read_current_windows_token()
    request["operator_id"] = "operator-candidate"
    request["request_hash"] = sha256_payload({
        key: value for key, value in request.items() if key != "request_hash"
    })
    path.write_bytes(canonical_json(request).encode())
    result = run(candidate, request, path, sid)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:OPERATOR_BINDING_MISMATCH"


def test_bounded_request_read(candidate, request_path):
    request, path = request_path
    sid, elevated = _read_current_windows_token()
    path.write_bytes(b"x" * 16385)
    result = run(candidate, request, path, sid)
    assert result.returncode == 1
    assert result.stdout.strip() == (
        "DENY:REQUEST_UNAVAILABLE" if elevated else
        "DENY:OPERATOR_TOKEN_NOT_ELEVATED"
    )


def test_missing_arguments_denied(candidate):
    result = subprocess.run(
        [str(candidate)], capture_output=True, text=True, timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:ARGUMENTS_INVALID"
