"""Pure fake-observation admission checks; no UAC, issuer, or Docker."""

import hashlib
import subprocess
import sys

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import CSC, ROOT
from tests.hermes_core.test_ea4e92mv_issuer_policy_candidate import canonical, policy


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("issuer-admission") / "probe.exe"
    files = [
        ROOT / "tools" / "Ea4eProtectedIssuerPolicyCandidate.cs",
        ROOT / "tools" / "Ea4eProtectedIssuerToken.cs",
        ROOT / "tools" / "Ea4eProtectedIssuerImage.cs",
        ROOT / "tools" / "Ea4eProtectedIssuerAdmissionCandidate.cs",
        ROOT / "tests" / "hermes_core" / "fixtures"
        / "ea4e92mw_issuer_admission_probe.cs",
    ]
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll", *(str(path) for path in files)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, tmp_path, *, change=None, values=None):
    values = values or policy()
    data = canonical(values).encode()
    path = tmp_path / "policy.json"
    path.write_bytes(data)
    observations = {
        "sid": values["operator_sid"],
        "elevated": "True",
        "image_path": values["issuer_path"],
        "image_sha": values["issuer_sha256"],
        "store_id": values["store_id"],
        "epoch": str(values["store_epoch"]),
        "commit": values["governing_commit"],
        "authority": values["authority_id"],
        "now": "1000",
        "expires": "1300",
    }
    observations.update(change or {})
    order = ("sid", "elevated", "image_path", "image_sha", "store_id",
             "epoch", "commit", "authority", "now", "expires")
    return subprocess.run(
        [str(executable), str(path), hashlib.sha256(data).hexdigest(),
         *(observations[key] for key in order)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_matching_fake_observations_are_not_authority(executable, tmp_path):
    result = check(executable, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "CANDIDATE_MATCH_NOT_AUTHORITY"


@pytest.mark.parametrize("change,reason", [
    ({"sid": "S-1-5-21-999"}, "OPERATOR_TOKEN_DENIED"),
    ({"elevated": "False"}, "OPERATOR_TOKEN_DENIED"),
    ({"image_path": r"C:\Temp\issuer.exe"}, "ISSUER_DISK_IMAGE_DENIED"),
    ({"image_sha": "0" * 64}, "ISSUER_DISK_IMAGE_DENIED"),
    ({"store_id": "0" * 64}, "STORE_IDENTITY_DENIED"),
    ({"epoch": "2"}, "STORE_IDENTITY_DENIED"),
    ({"commit": "0" * 64}, "SOURCE_AUTHORITY_DENIED"),
    ({"authority": "0" * 64}, "SOURCE_AUTHORITY_DENIED"),
    ({"now": "0"}, "TIME_WINDOW_DENIED"),
    ({"expires": "1000"}, "TIME_WINDOW_DENIED"),
    ({"expires": "1301"}, "TIME_WINDOW_DENIED"),
])
def test_drift_denied(executable, tmp_path, change, reason):
    result = check(executable, tmp_path, change=change)
    assert result.returncode == 1
    assert result.stdout.strip() == reason


def test_policy_commit_is_binding(executable, tmp_path):
    result = check(executable, tmp_path, values=policy(governing_commit="0" * 64),
                   change={"commit": "c" * 64})
    assert result.returncode == 1
    assert result.stdout.strip() == "SOURCE_AUTHORITY_DENIED"
