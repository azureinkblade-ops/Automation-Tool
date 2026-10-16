"""Pure v2 artifact construction; no trusted issuer or execution capability."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    KEYS, LABEL_KEYS, candidate, canonical,
)


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
BUILD_KEYS = tuple(key for key in KEYS if key != "artifact_hash")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("network-grant-builder") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ku_network_grant_builder_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def build(executable, tmp_path, fields, labels):
    output = tmp_path / "built-grant.json"
    result = subprocess.run(
        [str(executable), str(output), *(str(fields[key]) for key in BUILD_KEYS),
         *(str(labels[key]) for key in LABEL_KEYS)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result, output


def test_builder_matches_canonical_v2_candidate(executable, tmp_path):
    grant = candidate()
    result, output = build(executable, tmp_path, grant, grant["labels"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_bytes() == canonical(grant).encode()


@pytest.mark.parametrize("field,value", [
    ("grant_id", "not-a-hash"),
    ("nonce", ""),
    ("store_epoch", "0"),
    ("store_epoch", "01"),
    ("issued_at", "-1"),
    ("expires_at", "1301"),
    ("operator_sid", "not-a-sid"),
    ("network_name", "foreign-network"),
])
def test_invalid_inputs_denied(executable, tmp_path, field, value):
    grant = candidate()
    fields = {**grant, field: value}
    result, output = build(executable, tmp_path, fields, grant["labels"])
    assert result.returncode == 1
    assert not output.exists()


def test_label_mismatch_denied(executable, tmp_path):
    grant = candidate()
    labels = {**grant["labels"], "hermes.ea4e.attempt": "different"}
    result, output = build(executable, tmp_path, grant, labels)
    assert result.returncode == 1
    assert not output.exists()


def test_request_derived_values_round_trip(executable, tmp_path):
    from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
    from tests.hermes_core.test_ea4e92jv_agent_local_kilo_network_issue_request import _build

    source = tmp_path / "network-request"
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
        network_name=request["network_name"],
        labels=request["labels"],
    )
    result, output = build(executable, tmp_path, grant, grant["labels"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_bytes() == canonical(grant).encode()


def test_fake_builder_store_claim_wiring(executable, tmp_path):
    from tests.hermes_core.test_ea4e92kt_network_grant_v4_store import (
        SOURCES, call,
    )

    store_probe = tmp_path / "store-probe.exe"
    compiled = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{store_probe}",
         "/r:System.Web.Extensions.dll", *(str(source) for source in SOURCES)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    grant = candidate()
    built, artifact = build(executable, tmp_path, grant, grant["labels"])
    assert built.returncode == 0
    decoded = json.loads(artifact.read_text(encoding="ascii"))
    db, anchor = tmp_path / "wired.sqlite", tmp_path / "wired.anchor"
    assert call(store_probe, "init", db, anchor, grant["store_id"], 1).returncode == 0
    issued = call(
        store_probe, "issue", db, anchor, artifact,
        *(decoded[key] for key in KEYS),
        *(grant["labels"][key] for key in LABEL_KEYS),
    )
    assert issued.returncode == 0, issued.stdout + issued.stderr
    assert call(store_probe, "open", db, anchor).returncode == 0
    assert call(store_probe, "claim", db, anchor, grant["grant_id"], 1050).returncode == 0
    assert call(store_probe, "claim", db, anchor, grant["grant_id"], 1050).returncode == 1
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT state FROM network_grant_v4_rows"
        ).fetchone() == ("CLAIMED",)
