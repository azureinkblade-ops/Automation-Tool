"""Fake-only running sequence; no Docker daemon or real receiver."""

import pytest

from tools.hermes_core import kilo_fake_running_diagnostic as subject


NETWORK_ID, GATEWAY_ID, CLIENT_ID = "1" * 64, "2" * 64, "3" * 64
RUN_ID = "a" * 32


class Driver:
    def __init__(self, fail_at=None, leftovers=False):
        self.calls = []
        self.fail_at = fail_at
        self.leftovers = leftovers
        self.snapshots = 0

    def inspect_image(self, image):
        self.calls.append("image")
        return {"Id": image}

    def network_names(self):
        return []

    def container_names(self):
        return []

    def create_network(self, argv):
        self.calls.append("create-network")
        return NETWORK_ID

    def create_container(self, argv):
        role = "gateway" if "--network-alias" in argv else "client"
        self.calls.append("create-" + role)
        return GATEWAY_ID if role == "gateway" else CLIENT_ID

    def inspect_network(self, identity):
        self.calls.append("inspect-network")
        self.snapshots += 1
        return {"Id": identity}

    def inspect_container(self, identity):
        self.calls.append("inspect-container")
        return {"Id": identity}

    def start_container(self, identity):
        self.calls.append("start-" + ("gateway" if identity == GATEWAY_ID else "client"))
        if self.fail_at == "start-client" and identity == CLIENT_ID:
            raise RuntimeError("start denied")

    def pending_line(self, identity):
        self.calls.append("pending-line")
        if self.fail_at == "pending-line":
            return b"bad\n"
        return b'{"event":"FAKE_REQUEST_PENDING","peer":"172.20.0.2","body_bytes":1,"body_sha256":"' + b"a" * 64 + b'"}\n'

    def cleanup_running_owned(self, plan, network_id, gateway_id, client_id):
        self.calls.append("cleanup")
        assert plan["run_id"] == RUN_ID
        return {"remaining_network_ids": [NETWORK_ID] if self.leftovers else [],
                "remaining_container_ids": []}


@pytest.fixture(autouse=True)
def fake_checks(monkeypatch):
    monkeypatch.setattr(subject, "inspect_fake_gateway_preflight", lambda *args: None)
    monkeypatch.setattr(subject, "inspect_fake_gateway_created", lambda *args: None)
    monkeypatch.setattr(subject, "inspect_fake_gateway_running", lambda *args: None)


def test_two_fresh_running_reads_and_no_release():
    driver = Driver()
    result = subject.run_fake_running_diagnostic(driver, RUN_ID)
    assert result == {"decision": "FAKE_RUNNING_DIAGNOSTIC_ONLY",
                      "running_matches": 2, "release_signals": 0,
                      "peer_qualified": False, "production_ready": False}
    assert driver.snapshots == 3
    assert driver.calls.index("start-gateway") < driver.calls.index("start-client")
    assert driver.calls.index("start-client") < driver.calls.index("pending-line")
    assert driver.calls[-1] == "cleanup"
    assert not any("signal" in call or "release" in call for call in driver.calls)


@pytest.mark.parametrize("fail_at", ["start-client", "pending-line"])
def test_failure_cleans_owned_objects(fail_at):
    driver = Driver(fail_at=fail_at)
    with pytest.raises(Exception):
        subject.run_fake_running_diagnostic(driver, RUN_ID)
    assert driver.calls[-1] == "cleanup"


def test_running_match_denial_cleans_owned_objects(monkeypatch):
    driver = Driver()
    def deny(*args):
        raise ValueError("peer denied")
    monkeypatch.setattr(subject, "inspect_fake_gateway_running", deny)
    with pytest.raises(ValueError, match="peer denied"):
        subject.run_fake_running_diagnostic(driver, RUN_ID)
    assert driver.calls[-1] == "cleanup"


def test_second_running_snapshot_identity_drift_denied():
    driver = Driver()
    original = driver.inspect_network
    def drift(identity):
        record = original(identity)
        if driver.snapshots == 3:
            record["Id"] = "f" * 64
        return record
    driver.inspect_network = drift
    with pytest.raises(subject.FakeRunningDiagnosticDenied,
                       match="snapshot identity denied"):
        subject.run_fake_running_diagnostic(driver, RUN_ID)
    assert driver.calls[-1] == "cleanup"


def test_created_denial_never_starts(monkeypatch):
    driver = Driver()
    def deny(*args):
        raise ValueError("created denied")
    monkeypatch.setattr(subject, "inspect_fake_gateway_created", deny)
    with pytest.raises(ValueError, match="created denied"):
        subject.run_fake_running_diagnostic(driver, RUN_ID)
    assert driver.calls[-1] == "cleanup"
    assert not any(call.startswith("start-") for call in driver.calls)


def test_preflight_denial_creates_nothing(monkeypatch):
    driver = Driver()
    def deny(*args):
        raise ValueError("preflight denied")
    monkeypatch.setattr(subject, "inspect_fake_gateway_preflight", deny)
    with pytest.raises(ValueError, match="preflight denied"):
        subject.run_fake_running_diagnostic(driver, RUN_ID)
    assert not any(call.startswith("create-") for call in driver.calls)


def test_unconfirmed_cleanup_is_terminal():
    with pytest.raises(subject.FakeRunningDiagnosticDenied,
                       match="cleanup unconfirmed"):
        subject.run_fake_running_diagnostic(Driver(leftovers=True), RUN_ID)


def test_invalid_run_id_creates_nothing():
    driver = Driver()
    with pytest.raises(ValueError):
        subject.run_fake_running_diagnostic(driver, "bad")
    assert driver.calls == []
