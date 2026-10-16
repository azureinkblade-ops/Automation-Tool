"""Non-authorizing ceremony-review bytes must bind the exact request/grant pair."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    KEYS, LABEL_KEYS, canonical,
)
from tests.hermes_core.test_ea4e92kw_network_request_grant_binding import pair


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
REVIEW_FIELDS = (
    "action", "attempt_id", "authority_id", "ceremony_id",
    "docker_executable_sha256", "expires_at", "grant_artifact_hash",
    "grant_id", "issuer_binary_sha256", "issued_at", "network_name",
    "nonce", "operator_sid", "predecessor_hash", "request_hash",
    "schema_id", "source_commit", "store_epoch", "store_id",
)


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ceremony-review-candidate") / "probe.exe"
    sources = (
        ROOT / "tools" / "Ea4eNetworkIssueRequestCandidate.cs",
        ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs",
        ROOT / "tools" / "Ea4eNetworkRequestGrantBinding.cs",
        ROOT / "tools" / "Ea4eNetworkCeremonyReviewCandidate.cs",
        ROOT / "tests" / "hermes_core" / "fixtures"
        / "ea4e92kx_ceremony_review_candidate_probe.cs",
    )
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll", *(str(source) for source in sources)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def review_for(grant):
    return {
        "action": "network_create",
        "attempt_id": grant["attempt_id"],
        "authority_id": grant["authority_id"],
        "ceremony_id": grant["ceremony_id"],
        "docker_executable_sha256": grant["docker_executable_sha256"],
        "expires_at": str(grant["expires_at"]),
        "grant_artifact_hash": grant["artifact_hash"],
        "grant_id": grant["grant_id"],
        "issuer_binary_sha256": grant["issuer_binary_sha256"],
        "issued_at": str(grant["issued_at"]),
        "network_name": grant["network_name"],
        "nonce": grant["nonce"],
        "operator_sid": grant["operator_sid"],
        "predecessor_hash": grant["predecessor_hash"],
        "request_hash": grant["request_hash"],
        "schema_id": "hermes.docker-network-ceremony-review-candidate/v1",
        "source_commit": grant["source_commit"],
        "store_epoch": str(grant["store_epoch"]),
        "store_id": grant["store_id"],
    }


def check(executable, tmp_path, request, grant, review_bytes):
    paths = [tmp_path / name for name in ("review.json", "request.json", "grant.json")]
    for path, content in zip(paths, (
        review_bytes, canonical(request).encode(), canonical(grant).encode(),
    )):
        path.write_bytes(content)
    return subprocess.run(
        [str(executable), *(str(path) for path in paths),
         *(str(grant[key]) for key in KEYS),
         *(str(grant["labels"][key]) for key in LABEL_KEYS)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_exact_review_data_matches(executable, tmp_path, pair):
    request, grant = pair
    result = check(executable, tmp_path, request, grant,
                   canonical(review_for(grant)).encode())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:NON_AUTHORIZING_REVIEW_DATA"


@pytest.mark.parametrize("field", REVIEW_FIELDS)
def test_changed_review_field_denied(executable, tmp_path, pair, field):
    request, grant = pair
    review = review_for(grant)
    review[field] = review[field] + "x"
    assert check(executable, tmp_path, request, grant,
                 canonical(review).encode()).returncode == 1


@pytest.mark.parametrize("change", ["extra", "missing", "duplicate", "whitespace"])
def test_nonexact_review_structure_denied(executable, tmp_path, pair, change):
    request, grant = pair
    review = review_for(grant)
    if change == "extra":
        review["operator_verified"] = True
        raw = canonical(review).encode()
    elif change == "missing":
        del review["store_id"]
        raw = canonical(review).encode()
    elif change == "duplicate":
        raw = canonical(review).replace(
            '"action":"network_create",',
            '"action":"network_create","action":"network_create",',
        ).encode()
    else:
        raw = (canonical(review) + " ").encode()
    assert check(executable, tmp_path, request, grant, raw).returncode == 1


def test_review_does_not_repair_changed_request(executable, tmp_path, pair):
    request, grant = pair
    request = {**request, "operator_verified": True}
    assert check(executable, tmp_path, request, grant,
                 canonical(review_for(grant)).encode()).returncode == 1
