"""Fresh metadata can detect report drift but cannot establish ownership."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92jq_agent_local_kilo_precreate_peer_review import fixture
from tools.hermes_core.agent_local_kilo_fresh_peer_review import (
    review_fresh_precreate_kilo_peer,
)
from tools.hermes_core.agent_local_kilo_precreate_peer_report import (
    SQLiteAgentLocalKiloPrecreatePeerReportStore,
)


def _setup(tmp_path):
    start, args, client = fixture(tmp_path)
    reports = SQLiteAgentLocalKiloPrecreatePeerReportStore(args[0])
    reports.record(*args[1:], client.network, client.gateway, client.image)
    return start, args, client, reports


def test_fresh_match_is_not_owner_or_create_authority(tmp_path):
    start, args, client, reports = _setup(tmp_path)
    try:
        result = review_fresh_precreate_kilo_peer(
            reports, *args[1:], read_client=client,
        )
        assert (result.decision, result.reason) == (
            "MATCH", "FRESH_PRECREATE_REPORT_MATCH_OWNERSHIP_UNPROVEN",
        )
        assert result.receiver_executed is False
        assert result.provenance_checked is False
        assert client.calls == [
            ("network", args[-1]["network_id"]),
            ("gateway", args[-1]["gateway_id"]),
            ("image", args[-1]["gateway_image_index"],
             args[-1]["gateway_image_manifest"]),
        ]
        assert reports.get(args[1]).ownership_verified is False
        assert not hasattr(client, "create_container")
    finally:
        start.close()


def test_fresh_optional_byte_drift_denied(tmp_path):
    start, args, client, reports = _setup(tmp_path)
    try:
        client.network["Options"] = {"unreviewed": "changed"}
        result = review_fresh_precreate_kilo_peer(
            reports, *args[1:], read_client=client,
        )
        assert (result.decision, result.reason) == (
            "DENY", "FRESH_PEER_BYTES_CHANGED",
        )
    finally:
        start.close()


@pytest.mark.parametrize("field", ["network", "gateway", "image"])
def test_fresh_metadata_drift_denied(tmp_path, field):
    start, args, client, reports = _setup(tmp_path)
    try:
        if field == "network":
            client.network["Internal"] = False
        elif field == "gateway":
            client.gateway["State"]["Running"] = False
        else:
            client.image["Architecture"] = "arm64"
        result = review_fresh_precreate_kilo_peer(
            reports, *args[1:], read_client=client,
        )
        assert (result.decision, result.reason) == (
            "DENY", "FRESH_PEER_METADATA_MISMATCH",
        )
    finally:
        start.close()


def test_default_disabled_and_request_drift_do_not_read(tmp_path):
    start, args, client, reports = _setup(tmp_path)
    try:
        assert review_fresh_precreate_kilo_peer(reports, *args[1:]).decision == "DENY"
        changed = deepcopy(args[-1])
        changed["request_hash"] = "0" * 64
        result = review_fresh_precreate_kilo_peer(
            reports, *args[1:-1], changed, read_client=client,
        )
        assert (result.decision, result.reason) == (
            "DENY", "PRECREATE_REPORT_ABSENT_OR_CHANGED",
        )
        assert client.calls == []
    finally:
        start.close()
