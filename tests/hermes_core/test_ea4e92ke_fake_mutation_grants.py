"""Isolated fake-only mutation grant transitions; never calls Docker or an agent."""

import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SOURCES = [
    ROOT / "tools" / "Ea4eProtectedSqlite.cs",
    ROOT / "tools" / "Ea4eDockerMutationStoreIdentity.cs",
    ROOT / "tools" / "Ea4eFakeDockerMutationGrants.cs",
    ROOT / "tests" / "hermes_core" / "fixtures" / "ea4e92ke_grant_probe.cs",
]
GRANT = "a" * 64
NONCE = "b" * 64
ATTEMPT = "attempt-1"
REQUEST = "d" * 64
PREDECESSOR = "e" * 64
COMMIT = "f" * 64


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("mutation-grants") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(source) for source in SOURCES)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, action, database, anchor, *extra):
    return subprocess.run(
        [str(executable), action, str(database), str(anchor), *map(str, extra)],
        capture_output=True, text=True, timeout=10, check=False,
    )


@pytest.fixture
def store(executable, tmp_path):
    database = tmp_path / "mutation.sqlite"
    anchor = tmp_path / "mutation.anchor"
    assert call(executable, "init", database, anchor, "1" * 64, 1).returncode == 0
    return database, anchor


def issue(executable, store, **changes):
    fields = dict(grant=GRANT, nonce=NONCE, action="network_create",
                  attempt=ATTEMPT, request=REQUEST, predecessor=PREDECESSOR,
                  commit=COMMIT, sid="S-1-5-21-123", issued=1000, expires=1100)
    fields.update(changes)
    return call(executable, "issue", *store, *fields.values())


def claim(executable, store, **changes):
    fields = dict(grant=GRANT, action="network_create", attempt=ATTEMPT,
                  request=REQUEST, predecessor=PREDECESSOR, now=1050)
    fields.update(changes)
    return call(executable, "claim", *store, *fields.values())


def generation(database):
    with sqlite3.connect(database) as connection:
        return int(connection.execute(
            "SELECT generation FROM mutation_store_metadata"
        ).fetchone()[0])


def state(database):
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT state FROM mutation_fake_grants WHERE grant_id=?", (GRANT,)
        ).fetchone()[0]


def test_issue_claim_and_reopen(executable, store):
    assert issue(executable, store).returncode == 0
    assert generation(store[0]) == 1
    assert claim(executable, store).returncode == 0
    assert generation(store[0]) == 2
    assert state(store[0]) == "CLAIMED"
    assert call(executable, "open", *store).returncode == 0


def test_issue_accepts_existing_network_request_identity_shape(executable, store, tmp_path):
    from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
    from tests.hermes_core.test_ea4e92jv_agent_local_kilo_network_issue_request import _build

    source = tmp_path / "network-request"
    source.mkdir()
    start, values, spec, _, _, _ = setup(source)
    try:
        request = _build(values, spec)
    finally:
        start.close()
    assert issue(
        executable, store, attempt=request["attempt_id"],
        request=request["request_hash"], commit=request["governing_commit"],
    ).returncode == 0


def test_exact_duplicate_issue_does_not_replenish(executable, store):
    assert issue(executable, store).returncode == 0
    assert issue(executable, store).returncode == 1
    assert generation(store[0]) == 1
    assert claim(executable, store).returncode == 0
    assert issue(executable, store).returncode == 1
    assert claim(executable, store).returncode == 1
    assert generation(store[0]) == 2
    assert call(executable, "open", *store).returncode == 0


def test_concurrent_issue_has_one_winner(executable, store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: issue(executable, store), range(2)))
    assert sorted(result.returncode for result in results) == [0, 1]
    assert generation(store[0]) == 1
    assert call(executable, "open", *store).returncode == 0


@pytest.mark.parametrize("change", [
    {"nonce": NONCE}, {"attempt": ATTEMPT},
])
def test_unique_nonce_and_attempt_action(executable, store, change):
    assert issue(executable, store).returncode == 0
    fields = {"grant": "2" * 64, "nonce": "3" * 64, "attempt": "4" * 64}
    fields.update(change)
    assert issue(executable, store, **fields).returncode == 1
    assert generation(store[0]) == 1


@pytest.mark.parametrize("change", [
    {"action": "gateway_create"}, {"attempt": "2" * 64},
    {"request": "2" * 64}, {"predecessor": "2" * 64},
    {"now": 999}, {"now": 1100},
])
def test_wrong_scope_or_time_cannot_claim(executable, store, change):
    assert issue(executable, store).returncode == 0
    assert claim(executable, store, **change).returncode == 1
    assert state(store[0]) == "ISSUED"
    assert generation(store[0]) == 1


def test_revoke_before_claim(executable, store):
    assert issue(executable, store).returncode == 0
    assert call(executable, "revoke", *store, GRANT).returncode == 0
    assert state(store[0]) == "REVOKED"
    assert claim(executable, store).returncode == 1
    assert call(executable, "revoke", *store, GRANT).returncode == 1
    assert generation(store[0]) == 2


def test_revoke_after_claim_does_not_erase_spend(executable, store):
    assert issue(executable, store).returncode == 0
    assert claim(executable, store).returncode == 0
    assert call(executable, "revoke", *store, GRANT).returncode == 1
    assert state(store[0]) == "CLAIMED"
    assert generation(store[0]) == 2


def test_grant_row_tamper_cannot_replenish_claim(executable, store):
    assert issue(executable, store).returncode == 0
    assert claim(executable, store).returncode == 0
    with sqlite3.connect(store[0]) as connection:
        connection.execute(
            "UPDATE mutation_fake_grants SET state='ISSUED' WHERE grant_id=?",
            (GRANT,),
        )
    assert call(executable, "open", *store).returncode == 1
    assert claim(executable, store).returncode == 1


def test_missing_anchor_after_issue_fails_closed(executable, store):
    database, anchor = store
    assert issue(executable, store).returncode == 0
    issued_anchor = anchor.parent / (anchor.name + ".g00000001")
    issued_anchor.rename(anchor.parent / "preserved-issued-anchor")
    assert generation(database) == 1
    assert state(database) == "ISSUED"
    assert call(executable, "open", *store).returncode == 1
    assert issue(executable, store).returncode == 1


def test_missing_anchor_after_claim_never_replays(executable, store):
    database, anchor = store
    assert issue(executable, store).returncode == 0
    assert claim(executable, store).returncode == 0
    claimed_anchor = anchor.parent / (anchor.name + ".g00000002")
    claimed_anchor.rename(anchor.parent / "preserved-claimed-anchor")
    assert generation(database) == 2
    assert state(database) == "CLAIMED"
    assert call(executable, "open", *store).returncode == 1
    assert claim(executable, store).returncode == 1


@pytest.mark.parametrize("changes", [
    {"grant": "bad"}, {"action": "model_run"},
    {"sid": "unverified"}, {"expires": 1400},
    {"commit": "f" * 40}, {"attempt": "bad attempt"},
])
def test_invalid_issue_has_no_row_or_generation(executable, store, changes):
    assert issue(executable, store, **changes).returncode == 1
    assert generation(store[0]) == 0
    assert call(executable, "open", *store).returncode == 0
