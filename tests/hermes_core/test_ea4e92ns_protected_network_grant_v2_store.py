"""Protected-v2 candidate ledger qualification; no issuer, Docker, or receiver calls."""

import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    KEYS, LABEL_KEYS, candidate, canonical,
)

from tests.hermes_core.test_ea4e92mr_protected_network_grant import protected


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SOURCES = [
    ROOT / "tools" / "Ea4eProtectedSqlite.cs",
    ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs",
    ROOT / "tools" / "Ea4eProtectedNetworkGrantV2Digest.cs",
    ROOT / "tools" / "Ea4eProtectedNetworkGrantV2Store.cs",
    ROOT / "tests" / "hermes_core" / "fixtures"
    / "ea4e92ns_protected_network_grant_v2_store_probe.cs",
]


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("network-protected-grant-v2-store") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll", *(str(source) for source in SOURCES)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, command, db, anchor, *extra):
    return subprocess.run(
        [str(executable), command, str(db), str(anchor), *(str(x) for x in extra)],
        capture_output=True, text=True, timeout=10, check=False,
    )


@pytest.fixture
def store(executable, tmp_path):
    db, anchor = tmp_path / "protected-grant-v2.sqlite", tmp_path / "protected-grant-v2.anchor"
    result = call(executable, "init", db, anchor, "c" * 64, 1)
    assert result.returncode == 0, result.stdout
    return db, anchor


def issue(executable, store, tmp_path, grant=None, command="issue", expected=None):
    db, anchor = store
    grant = grant or protected()
    path = tmp_path / "grant.json"
    path.write_bytes(canonical(grant).encode())
    expected = expected or grant
    return call(executable, command, db, anchor, path,
                *(expected[key] for key in KEYS),
                *(grant["labels"][key] for key in LABEL_KEYS))


def test_issue_claim_replay_and_fresh_reopen(executable, store, tmp_path):
    db, anchor = store
    grant = protected()
    assert issue(executable, store, tmp_path, grant).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 0
    assert call(executable, "claim", db, anchor, grant["grant_id"], 1050).returncode == 0
    assert call(executable, "claim", db, anchor, grant["grant_id"], 1050).returncode == 1
    assert call(executable, "revoke", db, anchor, grant["grant_id"], 1050).returncode == 1
    assert call(executable, "uncertain", db, anchor, grant["grant_id"], 1050).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 0
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT state FROM protected_grant_v2_rows"
        ).fetchone() == ("UNCERTAIN",)
        assert connection.execute(
            "SELECT generation FROM protected_grant_v2_metadata"
        ).fetchone() == ("3",)


def test_revoke_and_expiry_deny_claim(executable, store, tmp_path):
    db, anchor = store
    grant = protected()
    assert issue(executable, store, tmp_path, grant).returncode == 0
    assert call(executable, "claim", db, anchor, grant["grant_id"], 1100).returncode == 1
    assert call(executable, "revoke", db, anchor, grant["grant_id"], 1050).returncode == 0
    assert call(executable, "claim", db, anchor, grant["grant_id"], 1050).returncode == 1
    assert call(executable, "open", db, anchor).returncode == 0
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT state FROM protected_grant_v2_rows"
        ).fetchone() == ("REVOKED",)


@pytest.mark.parametrize("change", [
    {"nonce": "8" * 64},
    {"attempt_id": "attempt-2", "labels": {
        "hermes.ea4e.attempt": "attempt-2",
        "hermes.ea4e.candidate_sha256": "6" * 64,
        "hermes.ea4e.profile": "LOCAL_CONTAINER_PROTECTED_ISSUER",
        "hermes.ea4e.cleanup_owner": "ea4e-kilo-owner-" + "7" * 32,
    }},
    {"network_name": "ea4e-kilo-" + "8" * 32},
    {"grant_id": "8" * 64},
])
def test_duplicate_identity_denied(executable, store, tmp_path, change):
    first = protected()
    assert issue(executable, store, tmp_path, first).returncode == 0
    second = protected(**change)
    assert issue(executable, store, tmp_path, second).returncode == 1
    assert call(executable, "open", *store).returncode == 0


def test_independent_expectation_mismatch_denied(executable, store, tmp_path):
    grant = protected(authority_id="8" * 64)
    assert issue(executable, store, tmp_path, grant,
                 expected=protected()).returncode == 1
    assert call(executable, "open", *store).returncode == 0


def test_row_byte_tamper_denied(executable, store, tmp_path):
    assert issue(executable, store, tmp_path).returncode == 0
    db, anchor = store
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE protected_grant_v2_rows SET artifact_json='{}'")
    assert call(executable, "open", db, anchor).returncode == 1


def test_current_state_tamper_denied(executable, store, tmp_path):
    assert issue(executable, store, tmp_path).returncode == 0
    db, anchor = store
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE protected_grant_v2_rows SET state='CLAIMED'")
    assert call(executable, "open", db, anchor).returncode == 1


def test_post_commit_missing_anchor_fail_closed(executable, store, tmp_path):
    result = issue(executable, store, tmp_path, command="crash-issue")
    assert result.returncode == 1
    assert "Injected post-commit anchor gap" in result.stdout
    assert call(executable, "open", *store).returncode == 1


def test_stale_handle_cannot_claim_after_other_handle_issues(executable, store, tmp_path):
    result = issue(executable, store, tmp_path, command="stale")
    assert result.returncode == 1
    assert "Concurrent store drift denied" in result.stdout
    assert call(executable, "open", *store).returncode == 0


def test_database_rollback_denied(executable, store, tmp_path):
    db, anchor = store
    earlier = tmp_path / "earlier.sqlite"
    shutil.copyfile(db, earlier)
    assert issue(executable, store, tmp_path).returncode == 0
    shutil.copyfile(earlier, db)
    assert call(executable, "open", db, anchor).returncode == 1


def test_missing_anchor_denied(executable, store, tmp_path):
    db, anchor = store
    assert issue(executable, store, tmp_path).returncode == 0
    latest = anchor.parent / (anchor.name + ".g00000001")
    latest.rename(anchor.parent / "preserved-anchor")
    assert call(executable, "open", db, anchor).returncode == 1


def test_anchor_tamper_denied(executable, store):
    db, anchor = store
    generation_zero = anchor.parent / (anchor.name + ".g00000000")
    with generation_zero.open("ab") as handle:
        handle.write(b"tamper")
    assert call(executable, "open", db, anchor).returncode == 1


def test_added_trigger_denied(executable, store):
    db, anchor = store
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TRIGGER injected AFTER UPDATE ON protected_grant_v2_rows "
            "BEGIN DELETE FROM protected_grant_v2_journal; END"
        )
    assert call(executable, "open", db, anchor).returncode == 1


def test_actual_v3_store_cross_open_denied(executable, tmp_path):
    db, anchor = tmp_path / "v3.sqlite", tmp_path / "v3.anchor"
    old_exe = tmp_path / "v3-probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{old_exe}",
         str(ROOT / "tools" / "Ea4eProtectedSqlite.cs"),
         str(ROOT / "tools" / "Ea4eDockerMutationStoreIdentity.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92kd_store_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert call(old_exe, "init", db, anchor, "a" * 64, 1).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 1


def test_expected_store_identity_rejects_valid_substitute(executable, store, tmp_path):
    db, anchor = store
    assert call(executable, "open-expected", db, anchor, "c" * 64, 1).returncode == 0
    assert call(executable, "open-expected", db, anchor, "8" * 64, 1).returncode == 1
    assert call(executable, "open-expected", db, anchor, "c" * 64, 2).returncode == 1
    foreign_db = tmp_path / "foreign.sqlite"
    foreign_anchor = tmp_path / "foreign.anchor"
    assert call(executable, "init", foreign_db, foreign_anchor, "8" * 64, 1).returncode == 0
    assert call(executable, "open", foreign_db, foreign_anchor).returncode == 0
    assert call(executable, "open-expected", foreign_db, foreign_anchor,
                "c" * 64, 1).returncode == 1


def test_fake_grant_rejected_by_protected_store(executable, store, tmp_path):
    assert issue(executable, store, tmp_path, candidate()).returncode == 1
    assert call(executable, "open", *store).returncode == 0


def test_protected_v1_bootstrap_cannot_cross_open(executable, tmp_path):
    db, anchor = tmp_path / "v1.sqlite", tmp_path / "v1.anchor"
    old_exe = tmp_path / "v1-probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{old_exe}",
         str(ROOT / "tools" / "Ea4eProtectedSqlite.cs"),
         str(ROOT / "tools" / "Ea4eProtectedNetworkGrantStoreBootstrap.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92nq_protected_store_bootstrap_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert call(old_exe, "init", db, anchor, "c" * 64, 1).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 1


def test_fake_v4_store_cannot_cross_open(executable, tmp_path):
    db, anchor = tmp_path / "fake-v4.sqlite", tmp_path / "fake-v4.anchor"
    old_exe = tmp_path / "fake-v4-probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{old_exe}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eProtectedSqlite.cs"),
         str(ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs"),
         str(ROOT / "tools" / "Ea4eNetworkGrantV4Digest.cs"),
         str(ROOT / "tools" / "Ea4eNetworkGrantV4Store.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92kt_network_grant_v4_store_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert call(old_exe, "init", db, anchor, "c" * 64, 1).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 1


def test_simultaneous_issue_has_one_winner(executable, store, tmp_path):
    grant = protected()
    path = tmp_path / "concurrent-grant.json"
    path.write_bytes(canonical(grant).encode())
    arguments = (
        path, *(grant[key] for key in KEYS),
        *(grant["labels"][key] for key in LABEL_KEYS),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda _: call(executable, "issue", *store, *arguments), range(2)
        ))
    assert sorted(result.returncode for result in outcomes) == [0, 1]
    assert call(executable, "open", *store).returncode == 0
    with sqlite3.connect(store[0]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM protected_grant_v2_rows"
        ).fetchone() == (1,)
