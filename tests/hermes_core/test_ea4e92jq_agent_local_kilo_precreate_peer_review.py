"""Pre-create metadata can match but cannot attest ownership or permit create."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tools.hermes_core.agent_local_kilo_create_issue_request import (
    build_kilo_create_issue_request,
)
from tools.hermes_core.agent_local_kilo_precreate_peer_review import (
    review_precreate_kilo_peer,
)


class FakeReadClient:
    def __init__(self, network, gateway, image):
        self.network = network
        self.gateway = gateway
        self.image = image
        self.calls = []

    def inspect_network(self, identity):
        self.calls.append(("network", identity))
        return deepcopy(self.network)

    def inspect_container(self, identity):
        self.calls.append(("gateway", identity))
        return deepcopy(self.gateway)

    def inspect_image(self, index, manifest):
        self.calls.append(("image", index, manifest))
        return deepcopy(self.image)


def fixture(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    request = build_kilo_create_issue_request(
        values["records"].intents, values["attempt_id"],
        values["v1_plan"], values["prepared"], spec,
        governing_commit="a" * 64, docker_executable_sha256="b" * 64,
        network_id=values["network"]["Id"], gateway_id=values["gateway_id"],
        operator_id="candidate-operator", nonce="one-shot-candidate",
        requested_ttl_seconds=60,
    )
    network = deepcopy(values["network"])
    network["Containers"] = {values["gateway_id"]: {"Name": "gateway-test"}}
    gateway = {
        "Id": values["gateway_id"], "Name": "/gateway-test",
        "Config": {"Image": request["gateway_image"]},
        "State": {"Running": True},
        "NetworkSettings": {"Networks": {spec["network"]["name"]: {
            "NetworkID": request["network_id"],
            "Aliases": ["ea4e-fake-gateway"],
        }}},
    }
    image = {"Id": request["gateway_image_manifest"],
             "Os": "linux", "Architecture": "amd64"}
    client = FakeReadClient(network, gateway, image)
    args = (values["records"].intents, values["attempt_id"],
            values["v1_plan"], values["prepared"], spec, request)
    return start, args, client


def test_matching_metadata_is_not_ownership_or_authority(tmp_path):
    start, args, client = fixture(tmp_path)
    try:
        result = review_precreate_kilo_peer(*args, read_client=client)
        assert (result.decision, result.reason) == (
            "MATCH", "PRECREATE_METADATA_MATCH_OWNERSHIP_UNPROVEN",
        )
        assert result.receiver_executed is False
        assert result.provenance_checked is False
        assert client.calls == [
            ("network", args[-1]["network_id"]),
            ("gateway", args[-1]["gateway_id"]),
            ("image", args[-1]["gateway_image_index"],
             args[-1]["gateway_image_manifest"]),
        ]
        assert not hasattr(client, "create_container")
        assert not hasattr(client, "start_container")
    finally:
        start.close()


def test_default_disabled_and_tampered_request_do_not_inspect(tmp_path):
    start, args, client = fixture(tmp_path)
    try:
        assert review_precreate_kilo_peer(*args).decision == "DENY"
        tampered = deepcopy(args[-1])
        tampered["gateway_image"] = "other"
        assert review_precreate_kilo_peer(
            *args[:-1], tampered, read_client=client,
        ).decision == "DENY"
        assert client.calls == []
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    lambda c: c.network.update(Internal=False),
    lambda c: c.network["Containers"].update({"f" * 64: {}}),
    lambda c: c.network["Containers"]["c" * 64].update(Name="other"),
    lambda c: c.gateway["State"].update(Running=False),
    lambda c: c.gateway["Config"].update(Image="other"),
    lambda c: c.gateway["NetworkSettings"]["Networks"].clear(),
    lambda c: c.gateway.update(NetworkSettings=None),
    lambda c: c.image.update(Id="sha256:" + "0" * 64),
])
def test_peer_metadata_drift_denied(tmp_path, change):
    start, args, client = fixture(tmp_path)
    try:
        change(client)
        assert review_precreate_kilo_peer(
            *args, read_client=client,
        ).decision == "DENY"
    finally:
        start.close()
