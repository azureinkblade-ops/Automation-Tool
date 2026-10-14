"""A durable pre-create report records untrusted metadata, never ownership."""

import sqlite3

import pytest

from tests.hermes_core.test_ea4e92jq_agent_local_kilo_precreate_peer_review import (
    fixture,
)
from tools.hermes_core.agent_local_kilo_precreate_peer_report import (
    SQLiteAgentLocalKiloPrecreatePeerReportStore,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


def _record(store, args, client):
    return store.record(*args[1:], client.network, client.gateway, client.image)


def test_report_is_durable_unique_and_not_authority(tmp_path):
    start, args, client = fixture(tmp_path)
    try:
        store = SQLiteAgentLocalKiloPrecreatePeerReportStore(args[0])
        reported = _record(store, args, client)
        reopened = SQLiteAgentLocalKiloPrecreatePeerReportStore(args[0])
        assert reopened.get(args[1]) == reported
        assert reported.issue_request_hash == args[-1]["request_hash"]
        assert reported.ownership_verified is False
        assert reported.create_authorized is False
        assert reported.launch_authorized is False
        with pytest.raises(DelegationIntegrityError, match="already recorded"):
            _record(reopened, args, client)
        assert reopened.get(args[1]) == reported
    finally:
        start.close()


def test_mismatched_peer_metadata_cannot_be_recorded(tmp_path):
    start, args, client = fixture(tmp_path)
    try:
        store = SQLiteAgentLocalKiloPrecreatePeerReportStore(args[0])
        client.network["Internal"] = False
        with pytest.raises(DelegationIntegrityError, match="metadata denied"):
            _record(store, args, client)
        assert store.get(args[1]) is None
    finally:
        start.close()


def test_changed_report_row_is_rejected_on_read(tmp_path):
    start, args, client = fixture(tmp_path)
    try:
        store = SQLiteAgentLocalKiloPrecreatePeerReportStore(args[0])
        _record(store, args, client)
        with sqlite3.connect(args[0].bridge_store.authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_precreate_peer_reports "
                "SET canonical_payload=REPLACE(canonical_payload, ?, ?) "
                "WHERE attempt_id=?",
                ('"ownership_verified":false', '"ownership_verified":true', args[1]),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            store.get(args[1])
    finally:
        start.close()
