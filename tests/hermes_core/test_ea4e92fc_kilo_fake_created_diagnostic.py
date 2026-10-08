"""Fake-only ordering and cleanup; no Docker daemon calls."""

import pytest

from tools.hermes_core import kilo_fake_created_diagnostic as subject


NETWORK_ID = "1" * 64
GATEWAY_ID = "2" * 64
CLIENT_ID = "3" * 64


class FakeDriver:
    def __init__(self, *, fail_at=None, leftovers=False):
        self.calls = []
        self.fail_at = fail_at
        self.leftovers = leftovers
        self.owned = set()

    def inspect_image(self, image):
        self.calls.append("image")
        return {"Id": image}

    def network_names(self):
        self.calls.append("network-names")
        return []

    def container_names(self):
        self.calls.append("container-names")
        return []

    def create_network(self, argv):
        self.calls.append("create-network")
        self.owned.add(NETWORK_ID)
        if self.fail_at == "create-network":
            raise RuntimeError("create result lost")
        return NETWORK_ID

    def create_container(self, argv):
        role = "gateway" if "--network-alias" in argv else "client"
        self.calls.append("create-" + role)
        identity = GATEWAY_ID if role == "gateway" else CLIENT_ID
        self.owned.add(identity)
        if self.fail_at == "create-" + role:
            raise RuntimeError("create result lost")
        return identity

    def inspect_network(self, identity):
        self.calls.append("inspect-network")
        return {"Id": identity}

    def inspect_container(self, identity):
        self.calls.append("inspect-container")
        if self.fail_at == "inspect-container":
            raise RuntimeError("inspect denied")
        return {"Id": identity}

    def cleanup_owned(self, plan, network_id, gateway_id, client_id):
        self.calls.append("cleanup-owned")
        assert plan["run_id"] == "a" * 32
        if self.leftovers:
            return {"remaining_network_ids": [NETWORK_ID],
                    "remaining_container_ids": []}
        self.owned.clear()
        return {"remaining_network_ids": [], "remaining_container_ids": []}


@pytest.fixture(autouse=True)
def fake_checks(monkeypatch):
    monkeypatch.setattr(subject, "inspect_fake_gateway_preflight",
                        lambda *args: {"decision": "FAKE_IMAGE_PREFLIGHT_ONLY"})
    monkeypatch.setattr(subject, "inspect_fake_gateway_created",
                        lambda *args: {"decision": "FAKE_CREATED_METADATA_MATCH_ONLY"})


def test_success_only_inspects_never_starts_and_cleans_owned_ids():
    driver = FakeDriver()
    result = subject.run_fake_created_diagnostic(driver, "a" * 32)
    assert result["decision"] == "FAKE_CREATED_DIAGNOSTIC_ONLY"
    assert result["containers_started"] == 0
    assert result["peer_qualified"] is False
    assert result["production_ready"] is False
    assert driver.calls[-1] == "cleanup-owned"
    assert driver.owned == set()
    assert not any("start" in call or "signal" in call for call in driver.calls)


@pytest.mark.parametrize("fail_at", ["create-network", "create-gateway",
                                          "create-client", "inspect-container"])
def test_partial_or_unknown_create_result_still_reconciles_owned_objects(fail_at):
    driver = FakeDriver(fail_at=fail_at)
    with pytest.raises(RuntimeError):
        subject.run_fake_created_diagnostic(driver, "a" * 32)
    assert driver.calls[-1] == "cleanup-owned"
    assert driver.owned == set()


def test_unconfirmed_cleanup_is_terminal_denial():
    driver = FakeDriver(leftovers=True)
    with pytest.raises(subject.FakeCreatedDiagnosticDenied,
                       match="cleanup unconfirmed"):
        subject.run_fake_created_diagnostic(driver, "a" * 32)


def test_preflight_denial_creates_nothing(monkeypatch):
    driver = FakeDriver()
    def deny(*args):
        raise ValueError("collision")
    monkeypatch.setattr(subject, "inspect_fake_gateway_preflight", deny)
    with pytest.raises(ValueError, match="collision"):
        subject.run_fake_created_diagnostic(driver, "a" * 32)
    assert not any(call.startswith("create-") for call in driver.calls)
