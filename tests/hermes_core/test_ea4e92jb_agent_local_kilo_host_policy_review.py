"""Synthetic Docker metadata only; host-policy MATCH never permits start."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92ij_agent_local_kilo_container_record import (
    observed,
)
from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_host_policy_review import (
    review_reported_kilo_host_policy,
)


GATEWAY_ID = "c" * 64


def fixture(tmp_path):
    start, intents, attempt, plan, prepared, container, image = observed(tmp_path)
    records = SQLiteAgentLocalKiloContainerRecordStore(intents)
    report = records.record(attempt, plan, prepared, container, image)
    candidate = build_agent_local_kilo_fake_launch_candidate(intents, attempt, plan)
    name = candidate["network"]["name"]
    container["State"]["Running"] = False
    container["HostConfig"].update({
        "NanoCpus": 2_000_000_000,
        "Memory": 2 * 1024 * 1024 * 1024,
        "PidsLimit": 64,
        "PublishAllPorts": False,
        "AutoRemove": False,
        "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges"],
        "Tmpfs": {
            "/work": "rw,nosuid,nodev,noexec,uid=65532,gid=65532,mode=0700,size=134217728",
        },
    })
    network = {
        "Id": report.network_id, "Name": name, "Driver": "bridge",
        "Internal": True, "EnableIPv6": False,
        "Containers": {report.container_id: {}, GATEWAY_ID: {}},
    }
    return start, {
        "records": records, "attempt_id": attempt, "v1_plan": plan,
        "prepared": prepared, "container": container, "image": image,
        "network": network, "gateway_id": GATEWAY_ID,
    }


def test_complete_report_is_still_not_start_authority(tmp_path):
    start, values = fixture(tmp_path)
    try:
        result = review_reported_kilo_host_policy(**values)
        assert result.decision == "MATCH"
        assert result.reason == "HOST_POLICY_REVIEW_ONLY_START_DENIED"
        assert values["records"].get(values["attempt_id"]).launch_authorized is False
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    lambda v: v["container"]["State"].update(Running=True),
    lambda v: v["container"]["Config"].update(User="0:0"),
    lambda v: v["container"]["HostConfig"].update(NanoCpus=0),
    lambda v: v["container"]["HostConfig"].update(Memory=0),
    lambda v: v["container"]["HostConfig"].update(PidsLimit=0),
    lambda v: v["container"]["HostConfig"].update(CapDrop=[]),
    lambda v: v["container"]["HostConfig"].update(SecurityOpt=[]),
    lambda v: v["container"]["HostConfig"].update(AutoRemove=True),
    lambda v: v["container"]["HostConfig"].update(PublishAllPorts=True),
    lambda v: v["container"]["HostConfig"].update(Tmpfs={}),
    lambda v: v["container"]["HostConfig"]["Tmpfs"].update({"/work": "rw,exec"}),
    lambda v: v["container"]["HostConfig"].update(ExtraHosts=["host:1.2.3.4"]),
    lambda v: v["container"].update(Id="d" * 64),
    lambda v: v["network"].update(Id="d" * 64),
    lambda v: v["network"].update(Internal=False),
    lambda v: v["network"]["Containers"].update({"d" * 64: {}}),
])
def test_policy_drift_denied(tmp_path, change):
    start, original = fixture(tmp_path)
    try:
        values = original.copy()
        values["container"] = deepcopy(original["container"])
        values["network"] = deepcopy(original["network"])
        change(values)
        assert review_reported_kilo_host_policy(**values).decision == "DENY"
    finally:
        start.close()
