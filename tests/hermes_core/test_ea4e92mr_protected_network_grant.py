"""Protected grant byte contract only; no issuer, store, or Docker access."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    CSC, KEYS, LABEL_KEYS, ROOT, candidate, canonical,
)


SCHEMA = "hermes.docker-network-mutation-grant/protected-v1"
PROFILE = "LOCAL_CONTAINER_PROTECTED_ISSUER"


def protected(**changes):
    grant = candidate()
    grant["schema_id"] = SCHEMA
    grant["labels"]["hermes.ea4e.profile"] = PROFILE
    grant.update(changes)
    grant.pop("artifact_hash")
    grant["artifact_hash"] = hashlib.sha256(canonical(grant).encode()).hexdigest()
    return grant


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("protected-network-grant") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92mr_protected_grant_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, tmp_path, mode, grant, *, raw=None, expected=None):
    path = tmp_path / "protected-grant.json"
    if mode != "build":
        path.write_bytes(raw if raw is not None else canonical(grant).encode())
    identity = expected or grant
    result = subprocess.run(
        [str(executable), mode, str(path),
         *(str(identity[key]) for key in KEYS),
         *(str(identity["labels"][key]) for key in LABEL_KEYS)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result, path


def test_protected_builder_and_reader_round_trip(executable, tmp_path):
    grant = protected()
    result, path = call(executable, tmp_path, "build", grant)
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == canonical(grant).encode()
    assert call(executable, tmp_path, "read", grant)[0].returncode == 0


def test_fake_and_protected_profiles_do_not_cross(executable, tmp_path):
    grant = protected()
    assert call(executable, tmp_path, "fake", grant)[0].returncode == 1
    fake = candidate()
    assert call(executable, tmp_path, "read", fake)[0].returncode == 1
    wrong = protected(schema_id=fake["schema_id"])
    assert call(executable, tmp_path, "read", wrong)[0].returncode == 1
    labels = dict(grant["labels"], **{"hermes.ea4e.profile": fake["labels"]["hermes.ea4e.profile"]})
    wrong = protected(labels=labels)
    assert call(executable, tmp_path, "read", wrong)[0].returncode == 1
    assert call(executable, tmp_path, "build", wrong)[0].returncode == 1


@pytest.mark.parametrize("change", [
    {"action": "gateway_create"},
    {"one_attempt_budget": 2},
    {"expires_at": 1301},
    {"network_internal": False},
    {"operator_sid": "not-a-sid"},
])
def test_invalid_scope_denied_even_with_recomputed_hash(executable, tmp_path, change):
    assert call(executable, tmp_path, "read", protected(**change))[0].returncode == 1


@pytest.mark.parametrize("field", [
    "issuer_binary_sha256", "operator_sid", "source_commit", "store_id",
    "authority_id", "request_hash",
])
def test_external_expected_identity_required(executable, tmp_path, field):
    grant = protected()
    expected = protected()
    expected[field] = "8" * 64 if field != "operator_sid" else "S-1-5-21-456"
    assert call(executable, tmp_path, "read", grant, expected=expected)[0].returncode == 1


def test_noncanonical_and_extra_bytes_denied(executable, tmp_path):
    grant = protected()
    assert call(executable, tmp_path, "read", grant,
                raw=(canonical(grant) + " ").encode())[0].returncode == 1
    assert call(executable, tmp_path, "read", protected(extra="bad"))[0].returncode == 1
