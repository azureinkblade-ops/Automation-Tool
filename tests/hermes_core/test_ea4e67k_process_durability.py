"""Actual abrupt-crash and clean-denial process qualification."""

import json
import sqlite3
import subprocess
import sys

import pytest

from tests.hermes_core.test_ea4e33a_store_rollback_detection import (
    NOW, PROCESS_HELPER, authorization, initialize, paths, persist, reopen,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableAuthorizationStoreIntegrityError,
)


def helper_argv(tmp_path, mode):
    database, anchor = paths(tmp_path)
    return [sys.executable, str(PROCESS_HELPER), mode, str(database),
            str(anchor), json.dumps(authorization()), NOW]


def test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed(tmp_path):
    persist(initialize(tmp_path))
    database, anchor = paths(tmp_path)
    previous_anchor = anchor.read_bytes()
    process = subprocess.run(helper_argv(tmp_path, "postcommit-crash"),
                             capture_output=True, text=True, timeout=10)
    assert process.returncode == 23
    assert not process.stdout.strip()
    assert anchor.read_bytes() == previous_anchor
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT consumed_state FROM invocation_authorizations"
        ).fetchone()[0] == "CONSUMED"
    finally:
        connection.close()
    # Abrupt exit released the coordination lock, but incomplete publication
    # must not silently repair the anchor or grant a second claim.
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path).claim(authorization(), consumed_at=NOW, validate=lambda: None)


def test_simultaneous_claims_have_one_winner_and_three_clean_denials(tmp_path):
    persist(initialize(tmp_path))
    children = []
    results = []
    try:
        for _ in range(4):
            children.append(subprocess.Popen(helper_argv(tmp_path, "claim"),
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, text=True))
        for child in children:
            stdout, stderr = child.communicate(timeout=15)
            assert child.returncode == 0, stderr
            assert not stderr.strip()
            results.append(stdout.strip())
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)
    assert results.count("ALLOW") == 1
    assert results.count("DENY") == 3
    assert reopen(tmp_path).consumed_count() == 1
