"""Fake read client only; no Docker daemon or receiver is contacted."""

from copy import deepcopy

from tests.hermes_core.test_ea4e92jb_agent_local_kilo_host_policy_review import (
    fixture,
)
from tools.hermes_core.agent_local_kilo_daemon_observer import (
    AgentLocalKiloDaemonObserver,
)
from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    build_provisional_kilo_launch_spec,
)


class FakeReadClient:
    def __init__(self, container, image, network):
        self.container = container
        self.image = image
        self.network = network
        self.calls = []

    def inspect_container(self, identity):
        self.calls.append(("container", identity))
        return deepcopy(self.container)

    def inspect_image(self, index, manifest):
        self.calls.append(("image", index, manifest))
        return deepcopy(self.image)

    def inspect_network(self, identity):
        self.calls.append(("network", identity))
        return deepcopy(self.network)


def setup(tmp_path):
    start, values = fixture(tmp_path)
    spec = build_provisional_kilo_launch_spec(
        values["records"].intents, values["attempt_id"],
        values["v1_plan"], values["prepared"],
    )
    client = FakeReadClient(values["container"], values["image"], values["network"])
    observer = AgentLocalKiloDaemonObserver(values["records"], read_client=client)
    args = (values["attempt_id"], values["v1_plan"], values["prepared"], spec)
    return start, values, spec, client, observer, args


def test_reads_exact_recorded_ids_and_remains_review_only(tmp_path):
    start, values, spec, client, observer, args = setup(tmp_path)
    try:
        result = observer.review(*args, gateway_id=values["gateway_id"])
        report = values["records"].get(values["attempt_id"])
        assert client.calls == [
            ("container", report.container_id),
            ("image", spec["image_index"], spec["image_manifest"]),
            ("network", report.network_id),
        ]
        assert result.decision == "MATCH"
        assert result.reason == "CREATE_SPEC_REVIEW_ONLY_START_DENIED"
        assert result.receiver_executed is False
        assert result.provenance_checked is False
        assert not hasattr(client, "start_container")
    finally:
        start.close()


def test_default_disabled_does_not_inspect(tmp_path):
    start, values, _, client, _, args = setup(tmp_path)
    try:
        observer = AgentLocalKiloDaemonObserver(values["records"])
        result = observer.review(*args, gateway_id=values["gateway_id"])
        assert result.decision == "DENY"
        assert result.reason == "NO_DAEMON_READ_CLIENT"
        assert client.calls == []
    finally:
        start.close()


def test_read_failure_and_swapped_metadata_deny(tmp_path):
    start, values, _, client, observer, args = setup(tmp_path)
    try:
        client.container = deepcopy(client.container)
        client.container["Name"] = "/swapped"
        assert observer.review(*args, gateway_id=values["gateway_id"]).decision == "DENY"

        def fail(_identity):
            raise OSError("synthetic read error")

        client.inspect_container = fail
        result = observer.review(*args, gateway_id=values["gateway_id"])
        assert result.decision == "DENY"
        assert result.reason == "DAEMON_READ_FAILED"
    finally:
        start.close()
