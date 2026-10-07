"""Fake-only diagnostic sequence; no Docker command is invoked."""

import pytest

from tools.hermes_core import inert_peer_prestart_diagnostic as subject
from tools.hermes_core.inert_peer_created_check import InertPeerCreatedDenied


class FakeDriver:
    def __init__(self):
        self.calls = []

    def inspect_image(self, identity):
        self.calls.append("image")
        return {}

    def network_names(self):
        return []

    def container_names(self):
        return []

    def create_network(self, argv):
        self.calls.append("create-network")
        return "network-id"

    def create_container(self, argv):
        role = argv[-1]
        self.calls.append("create-" + role)
        return role + "-id"

    def inspect_network(self, identity):
        return {"Id": identity}

    def inspect_container(self, identity):
        role = identity.removesuffix("-id")
        return {"Id": identity,
                "NetworkSettings": {"Networks": {
                    f"ea4e-peer-{'a' * 32}": {
                        "NetworkID": "" if role == "client" else "network-id",
                    },
                }}}

    def remove_container(self, identity):
        self.calls.append("remove-" + identity)

    def remove_network(self, identity):
        self.calls.append("remove-network")


def test_diagnostic_reports_exact_denial_and_never_starts(monkeypatch):
    monkeypatch.setattr(subject, "inspect_inert_peer_preflight",
                        lambda *args: None)
    def deny(*args):
        raise InertPeerCreatedDenied("client endpoint network ID denied")
    monkeypatch.setattr(subject, "inspect_inert_peer_created", deny)
    driver = FakeDriver()
    result = subject.diagnose_prestart(driver, "a" * 32)
    assert result["decision"] == "PRESTART_HOLD"
    assert result["reason"] == "client endpoint network ID denied"
    assert result["client"]["endpoint_network_id"] == ""
    assert result["gateway"]["endpoint_network_id_matches"] is True
    assert result["containers_started"] == 0
    assert result["release_signals_sent"] == 0
    assert driver.calls == ["image", "create-network", "create-gateway",
                            "create-client", "remove-client-id",
                            "remove-gateway-id", "remove-network"]


def test_matching_prestart_still_never_starts(monkeypatch):
    monkeypatch.setattr(subject, "inspect_inert_peer_preflight",
                        lambda *args: None)
    monkeypatch.setattr(subject, "inspect_inert_peer_created",
                        lambda *args: None)
    result = subject.diagnose_prestart(FakeDriver(), "a" * 32)
    assert result["decision"] == "PRESTART_MATCH_ONLY"
    assert result["containers_started"] == 0


def test_exact_acknowledgement_before_driver(monkeypatch):
    monkeypatch.setattr(subject, "DockerProbeDriver",
                        lambda: pytest.fail("driver constructed"))
    with pytest.raises(ValueError):
        subject.main(["--approved-diagnostic-once", "wrong-image"])
