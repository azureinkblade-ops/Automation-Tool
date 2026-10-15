"""Pure C# network-request byte parity; never issues or calls Docker."""

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tests.hermes_core.test_ea4e92jv_agent_local_kilo_network_issue_request import _build
from tools.hermes_core.hashing import canonical_json, sha256_payload


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SYSTEM_DLL = CSC.parent / "System.dll"
SYSTEM_CORE_DLL = CSC.parent / "System.Core.dll"
JSON_DLL = Path(
    r"C:\Windows\Microsoft.NET\assembly\GAC_MSIL\System.Web.Extensions"
    r"\v4.0_4.0.0.0__31bf3856ad364e35\System.Web.Extensions.dll"
)


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if (sys.platform != "win32" or not CSC.is_file() or
            not JSON_DLL.is_file() or not SYSTEM_DLL.is_file() or
            not SYSTEM_CORE_DLL.is_file()):
        pytest.skip("Windows .NET Framework JSON dependency unavailable")
    target = tmp_path_factory.mktemp("network-request") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/noconfig", "/target:exe", f"/out:{target}",
         f"/reference:{JSON_DLL}",
         f"/reference:{SYSTEM_DLL}", f"/reference:{SYSTEM_CORE_DLL}",
         str(ROOT / "tools" / "Ea4eNetworkIssueRequestCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ki_network_request_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.fixture
def network_request(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    start, values, spec, _, _, _ = setup(source)
    try:
        return _build(values, spec)
    finally:
        start.close()


def check(executable, tmp_path, network_request, *, raw=None, **expected_changes):
    request = network_request
    source = tmp_path / "candidate.json"
    source.write_bytes(raw if raw is not None else canonical_json(request).encode())
    labels = request["labels"]
    expected = dict(
        digest=request["request_hash"], commit=request["governing_commit"],
        docker=request["docker_executable_sha256"],
        attempt=request["attempt_id"], operator=request["operator_id"],
        network=request["network_name"], label_attempt=labels["hermes.ea4e.attempt"],
        candidate=labels["hermes.ea4e.candidate_sha256"],
        profile=labels["hermes.ea4e.profile"],
        owner=labels["hermes.ea4e.cleanup_owner"],
    )
    expected.update(expected_changes)
    args = [source, expected["digest"], expected["commit"], expected["docker"],
            expected["attempt"], expected["operator"], expected["network"],
            expected["label_attempt"], expected["candidate"], expected["profile"],
            expected["owner"]]
    return subprocess.run(
        [str(executable), *map(str, args)], capture_output=True, text=True,
        timeout=10, check=False,
    )


def test_existing_builder_request_matches(executable, network_request, tmp_path):
    result = check(executable, tmp_path, network_request)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "REQUEST_BYTES_MATCH_ONLY"


@pytest.mark.parametrize("field,value", [
    ("docker_engine_endpoint", "npipe:////./pipe/other"),
    ("network_internal", False), ("issue_authorized", True),
    ("requested_ttl_seconds", 301), ("network_name", "foreign"),
    ("operator_id", "other-operator"),
])
def test_changed_request_denied(executable, network_request, tmp_path, field, value):
    candidate = deepcopy(network_request)
    candidate[field] = value
    candidate["request_hash"] = sha256_payload({
        key: data for key, data in candidate.items() if key != "request_hash"
    })
    assert check(executable, tmp_path, candidate,
                 digest=candidate["request_hash"],
                 operator=network_request["operator_id"]).returncode == 1


@pytest.mark.parametrize("change", [
    {"digest": "0" * 64}, {"commit": "0" * 64},
    {"docker": "0" * 64}, {"attempt": "other"},
    {"operator": "other"}, {"network": "ea4e-kilo-" + "0" * 32},
    {"candidate": "0" * 64}, {"profile": "PRODUCTION"},
    {"owner": "ea4e-kilo-owner-" + "0" * 32},
])
def test_changed_independent_expectation_denied(executable, network_request, tmp_path, change):
    assert check(executable, tmp_path, network_request, **change).returncode == 1


def test_noncanonical_duplicate_and_extra_fields_denied(executable, network_request, tmp_path):
    canonical = canonical_json(network_request).encode()
    assert check(executable, tmp_path, network_request, raw=canonical + b" ").returncode == 1
    with_duplicate = canonical.replace(b'"action":"network_create",',
                                       b'"action":"network_create","action":"network_create",')
    assert check(executable, tmp_path, network_request, raw=with_duplicate).returncode == 1
    extra = deepcopy(network_request)
    extra["authorization_id"] = "forged"
    assert check(executable, tmp_path, extra).returncode == 1


def test_network_argv_and_labels_denied(executable, network_request, tmp_path):
    for field in ("argv", "labels"):
        candidate = deepcopy(network_request)
        if field == "argv":
            candidate["argv"][4] = "--attachable"
        else:
            candidate["labels"]["hermes.ea4e.profile"] = "PRODUCTION"
        candidate["request_hash"] = sha256_payload({
            key: data for key, data in candidate.items() if key != "request_hash"
        })
        assert check(executable, tmp_path, candidate,
                     digest=candidate["request_hash"]).returncode == 1


def test_bad_bytes_denied(executable, network_request, tmp_path):
    assert check(executable, tmp_path, network_request, raw=b"\xff").returncode == 1
    assert check(executable, tmp_path, network_request, raw=b"{" + b"x" * 16384).returncode == 1
