"""Non-live v5 production-profile store qualification; no issuer or Docker."""

from concurrent.futures import ThreadPoolExecutor
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    CSC, KEYS, LABEL_KEYS, ROOT, candidate, canonical,
)
from tests.hermes_core.test_ea4e92mr_protected_network_grant import protected


SOURCES = [
    ROOT / "tools" / "Ea4eProtectedSqlite.cs",
    ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs",
    ROOT / "tools" / "Ea4eNetworkGrantV5Digest.cs",
    ROOT / "tools" / "Ea4eNetworkGrantV5Store.cs",
    ROOT / "tests" / "hermes_core" / "fixtures"
    / "ea4e92ms_network_grant_v5_store_probe.cs",
]


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("protected-network-store") / "probe.exe"
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
    db, anchor = tmp_path / "grant-v5.sqlite", tmp_path / "grant-v5.anchor"
    result = call(executable, "init", db, anchor, "c" * 64, 1)
    assert result.returncode == 0, result.stdout + result.stderr
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


def test_issue_claim_reopen_and_replay_denial(executable, store, tmp_path):
    db, anchor = store
    grant = protected()
    assert issue(executable, store, tmp_path, grant).returncode == 0
    assert call(executable, "open-expected", db, anchor, grant["store_id"], 1).returncode == 0
    assert call(executable, "claim", db, anchor, grant["grant_id"], 1050).returncode == 0
    assert call(executable, "claim", db, anchor, grant["grant_id"], 1050).returncode == 1
    assert call(executable, "revoke", db, anchor, grant["grant_id"], 1050).returncode == 1
    assert call(executable, "uncertain", db, anchor, grant["grant_id"], 1050).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 0
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT state FROM network_grant_v5_rows"
        ).fetchone() == ("UNCERTAIN",)


def test_concurrent_claims_have_at_most_one_winner(executable, store, tmp_path):
    grant = protected()
    assert issue(executable, store, tmp_path).returncode == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: call(executable, "claim", *store, grant["grant_id"], 1050),
            range(2),
        ))
    assert sorted(result.returncode for result in results) == [0, 1]
    assert call(executable, "open", *store).returncode == 0


def test_revocation_and_expiry(executable, store, tmp_path):
    grant = protected()
    assert issue(executable, store, tmp_path).returncode == 0
    assert call(executable, "claim", *store, grant["grant_id"], 1100).returncode == 1
    assert call(executable, "revoke", *store, grant["grant_id"], 1050).returncode == 0
    assert call(executable, "claim", *store, grant["grant_id"], 1050).returncode == 1


def test_preissuance_time_denied_for_claim_and_revocation(executable, store, tmp_path):
    grant = protected()
    assert issue(executable, store, tmp_path).returncode == 0
    assert call(executable, "claim", *store, grant["grant_id"], 999).returncode == 1
    assert call(executable, "revoke", *store, grant["grant_id"], 999).returncode == 1
    assert call(executable, "open", *store).returncode == 0
    assert call(executable, "claim", *store, grant["grant_id"], 1000).returncode == 0


def test_fake_grant_and_store_identity_denied(executable, store, tmp_path):
    assert issue(executable, store, tmp_path, grant=candidate()).returncode == 1
    assert call(executable, "open-expected", *store, "8" * 64, 1).returncode == 1
    assert call(executable, "open", *store).returncode == 0


@pytest.mark.parametrize("change", [
    {"nonce": "8" * 64},
    {"network_name": "ea4e-kilo-" + "8" * 32},
    {"grant_id": "8" * 64},
])
def test_duplicate_identity_denied(executable, store, tmp_path, change):
    assert issue(executable, store, tmp_path).returncode == 0
    assert issue(executable, store, tmp_path, protected(**change)).returncode == 1
    assert call(executable, "open", *store).returncode == 0


def test_external_expected_identity_denied(executable, store, tmp_path):
    grant = protected(authority_id="8" * 64)
    assert issue(executable, store, tmp_path, grant,
                 expected=protected()).returncode == 1
    assert call(executable, "open", *store).returncode == 0


def test_anchor_gap_after_commit_is_fail_closed(executable, store, tmp_path):
    result = issue(executable, store, tmp_path, command="crash-issue")
    assert result.returncode == 1
    assert "Injected post-commit anchor gap" in result.stdout
    assert call(executable, "open", *store).returncode == 1


def test_stale_handle_and_rollback_denied(executable, store, tmp_path):
    result = issue(executable, store, tmp_path, command="stale")
    assert result.returncode == 1
    assert "Concurrent store drift denied" in result.stdout
    assert call(executable, "open", *store).returncode == 0
    db, anchor = store
    earlier = tmp_path / "earlier.sqlite"
    shutil.copyfile(db, earlier)
    grant = protected(grant_id="8" * 64, nonce="9" * 64,
                      attempt_id="attempt-2",
                      network_name="ea4e-kilo-" + "8" * 32,
                      labels={**protected()["labels"], "hermes.ea4e.attempt": "attempt-2"})
    assert issue(executable, store, tmp_path, grant).returncode == 0
    shutil.copyfile(earlier, db)
    assert call(executable, "open", db, anchor).returncode == 1


def test_row_tamper_denied(executable, store, tmp_path):
    assert issue(executable, store, tmp_path).returncode == 0
    with sqlite3.connect(store[0]) as connection:
        connection.execute("UPDATE network_grant_v5_rows SET state='CLAIMED'")
    assert call(executable, "open", *store).returncode == 1


def test_journal_and_schema_tamper_denied(executable, store):
    with sqlite3.connect(store[0]) as connection:
        connection.execute(
            "CREATE TRIGGER injected AFTER UPDATE ON network_grant_v5_rows "
            "BEGIN DELETE FROM network_grant_v5_journal; END"
        )
    assert call(executable, "open", *store).returncode == 1


def test_modified_anchor_denied(executable, store):
    anchor = store[1].parent / (store[1].name + ".g00000000")
    with anchor.open("ab") as handle:
        handle.write(b"tamper")
    assert call(executable, "open", *store).returncode == 1


def test_duplicate_attempt_identity_denied(executable, store, tmp_path):
    assert issue(executable, store, tmp_path).returncode == 0
    second = protected(grant_id="8" * 64, nonce="9" * 64,
                       network_name="ea4e-kilo-" + "8" * 32)
    assert issue(executable, store, tmp_path, second).returncode == 1
    assert call(executable, "open", *store).returncode == 0


def test_v4_database_cannot_open_as_v5(executable, tmp_path):
    from tests.hermes_core.test_ea4e92kt_network_grant_v4_store import SOURCES as V4

    old = tmp_path / "v4.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{old}",
         "/r:System.Web.Extensions.dll", *(str(source) for source in V4)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    db, anchor = tmp_path / "v4.sqlite", tmp_path / "v4.anchor"
    assert call(old, "init", db, anchor, "c" * 64, 1).returncode == 0
    assert call(executable, "open", db, anchor).returncode == 1
    assert call(old, "open", db, anchor).returncode == 0
    db5, anchor5 = tmp_path / "v5.sqlite", tmp_path / "v5.anchor"
    assert call(executable, "init", db5, anchor5, "c" * 64, 1).returncode == 0
    assert call(old, "open", db5, anchor5).returncode == 1
