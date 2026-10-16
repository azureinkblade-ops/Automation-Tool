"""Fake-only relationship check between request bytes and v2 grant bytes."""

import hashlib
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tests.hermes_core.test_ea4e92jv_agent_local_kilo_network_issue_request import _build
from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    KEYS, LABEL_KEYS, candidate, canonical,
)


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("network-request-grant-binding") / "probe.exe"
    sources = (
        ROOT / "tools" / "Ea4eNetworkIssueRequestCandidate.cs",
        ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs",
        ROOT / "tools" / "Ea4eNetworkRequestGrantBinding.cs",
        ROOT / "tests" / "hermes_core" / "fixtures"
        / "ea4e92kw_network_request_grant_binding_probe.cs",
    )
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll", *(str(source) for source in sources)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.fixture
def pair(tmp_path):
    source = tmp_path / "request-source"
    source.mkdir()
    start, values, spec, _, _, _ = setup(source)
    try:
        request = _build(values, spec, operator_id="S-1-5-21-123")
    finally:
        start.close()
    grant = candidate(
        attempt_id=request["attempt_id"],
        request_hash=request["request_hash"],
        command_spec_hash=request["request_hash"],
        source_commit=request["governing_commit"],
        operator_sid=request["operator_id"],
        docker_executable_sha256=request["docker_executable_sha256"],
        network_name=request["network_name"], labels=request["labels"],
        expires_at=1060,
    )
    return request, grant


def check(executable, tmp_path, request, grant, *, expected=None, raw_request=None):
    request_path = tmp_path / "request.json"
    grant_path = tmp_path / "grant.json"
    request_path.write_bytes(raw_request if raw_request is not None else canonical(request).encode())
    grant_path.write_bytes(canonical(grant).encode())
    expected = expected or grant
    return subprocess.run(
        [str(executable), str(request_path), str(grant_path),
         *(str(expected[key]) for key in KEYS),
         *(str(grant["labels"][key]) for key in LABEL_KEYS)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def rehash(request):
    request["request_hash"] = hashlib.sha256(canonical({
        key: value for key, value in request.items() if key != "request_hash"
    }).encode()).hexdigest()
    return request


def test_exact_request_grant_pair_matches(executable, tmp_path, pair):
    result = check(executable, tmp_path, *pair)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:NON_AUTHORIZING_BINDING"


@pytest.mark.parametrize("key,value", [
    ("source_commit", "8" * 64),
    ("docker_executable_sha256", "8" * 64),
    ("operator_sid", "S-1-5-21-456"),
    ("attempt_id", "another-attempt"),
    ("network_name", "ea4e-kilo-" + "8" * 32),
    ("request_hash", "8" * 64),
])
def test_individually_valid_grant_with_foreign_request_denied(
    executable, tmp_path, pair, key, value,
):
    request, grant = pair
    change = {key: value}
    if key == "request_hash":
        change["command_spec_hash"] = value
    elif key == "attempt_id":
        labels = dict(grant["labels"])
        labels["hermes.ea4e.attempt"] = value
        change["labels"] = labels
    changed_grant = candidate(**{**{
        field: grant[field] for field in (
            "attempt_id", "request_hash", "command_spec_hash", "source_commit",
            "operator_sid", "docker_executable_sha256", "network_name",
            "labels", "expires_at",
        )}, **change})
    assert check(executable, tmp_path, request, changed_grant).returncode == 1


def test_grant_cannot_outlive_requested_ttl(executable, tmp_path, pair):
    request, grant = pair
    changed = candidate(**{**{
        field: grant[field] for field in (
            "attempt_id", "request_hash", "command_spec_hash", "source_commit",
            "operator_sid", "docker_executable_sha256", "network_name", "labels",
        )}, "expires_at": 1061})
    assert check(executable, tmp_path, request, changed).returncode == 1


def test_rehashed_request_with_authority_flag_denied(executable, tmp_path, pair):
    request, grant = pair
    changed = rehash({**request, "operator_verified": True})
    assert check(executable, tmp_path, changed, grant).returncode == 1


def test_noncanonical_request_bytes_denied(executable, tmp_path, pair):
    request, grant = pair
    raw = (canonical(request) + " ").encode()
    assert check(executable, tmp_path, request, grant, raw_request=raw).returncode == 1


def test_external_grant_expectation_mismatch_denied(executable, tmp_path, pair):
    request, grant = pair
    expected = deepcopy(grant)
    expected["authority_id"] = "8" * 64
    assert check(executable, tmp_path, request, grant, expected=expected).returncode == 1
