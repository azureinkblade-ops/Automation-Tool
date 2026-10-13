"""Synthetic metadata checks only; no container or receiver is started."""

from copy import deepcopy
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92dh_local_kilo_image_admission import metadata as image_metadata
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW
from tests.hermes_core.test_ea4e92ib_local_kilo_ping_intent import accepted
from tools.hermes_core.agent_local_kilo_fake_inputs import prepare_agent_local_kilo_fake_inputs
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import build_agent_local_kilo_fake_launch_candidate
from tools.hermes_core.agent_local_kilo_fake_prestart import inspect_agent_local_kilo_fake_prestart
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.local_kilo_image_admission import IMAGE_INDEX_ID


def fixture(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
    intents.reserve(lease.attempt_id, plan)
    prepared = prepare_agent_local_kilo_fake_inputs(
        intents, lease.attempt_id, plan, tmp_path / "revised",
    )
    candidate = build_agent_local_kilo_fake_launch_candidate(intents, lease.attempt_id, plan)
    root = Path(prepared["root"])
    image = image_metadata()
    image["RepoDigests"] = [f"hermes/kilo@{IMAGE_INDEX_ID}"]
    image["Config"]["Env"] = ["PATH=/usr/bin:/bin", "HOME=/tmp/kilo-home"]
    container = {
        "Image": IMAGE_INDEX_ID,
        "State": {"Status": "created"},
        "Config": {
            "Entrypoint": candidate["entrypoint"],
            "Cmd": candidate["argv"],
            "User": candidate["user"],
            "WorkingDir": candidate["workdir"],
            "Env": ["PATH=/usr/bin:/bin"] + [
                f"{key}={value}" for key, value in candidate["env"].items()
            ],
        },
        "HostConfig": {
            "NetworkMode": candidate["network"]["name"],
            "ReadonlyRootfs": True,
            "Privileged": False,
        },
        "NetworkSettings": {"Networks": {candidate["network"]["name"]: {}}},
        "Mounts": [
            {"Type": "bind", "Source": str(root / "input"),
             "Destination": "/reviewed-input", "RW": False},
            {"Type": "bind", "Source": str(root / "runtime"),
             "Destination": "/tmp/kilo-home", "RW": True},
            {"Type": "tmpfs", "Source": "", "Destination": "/work", "RW": True},
        ],
    }
    return start, intents, lease.attempt_id, plan, prepared, container, image


def test_candidate_metadata_match_is_not_start_authority(tmp_path):
    start, intents, attempt, plan, prepared, container, image = fixture(tmp_path)
    try:
        result = inspect_agent_local_kilo_fake_prestart(
            intents, attempt, plan, prepared, container, image,
        )
        assert result.decision == "MATCH"
        assert result.reason == "CANDIDATE_METADATA_ONLY_START_DENIED"
        assert result.receiver_executed is False
        assert result.provenance_checked is False
    finally:
        start.close()


@pytest.mark.parametrize("mutate", [
    lambda c: c["Config"].update(Cmd=["run", "other"]),
    lambda c: c["Config"].update(Entrypoint=["/bin/sh"]),
    lambda c: c["Config"].update(User="0:0"),
    lambda c: c["Config"].update(Env=[]),
    lambda c: c["Config"]["Env"].append("HOME=/wrong"),
    lambda c: c["Config"]["Env"].append(c["Config"]["Env"][0]),
    lambda c: c["Config"]["Env"].append("OPENAI_API_KEY=unreviewed"),
    lambda c: c["HostConfig"].update(NetworkMode="bridge"),
    lambda c: c["HostConfig"].update(ReadonlyRootfs=False),
    lambda c: c["HostConfig"].update(Privileged=True),
    lambda c: c["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
    lambda c: c["HostConfig"].update(PortBindings={"80/tcp": []}),
    lambda c: c["NetworkSettings"].update(Networks={}),
    lambda c: c.update(NetworkSettings=None),
    lambda c: c["Mounts"][0].update(RW=True),
    lambda c: c["Mounts"][1].update(Source="/other"),
    lambda c: c["Mounts"].append({"Type": "bind", "Source": "/secret", "Destination": "/secret", "RW": True}),
    lambda c: c["State"].update(Status="running"),
])
def test_mismatch_denied(tmp_path, mutate):
    start, intents, attempt, plan, prepared, container, image = fixture(tmp_path)
    try:
        changed = deepcopy(container)
        mutate(changed)
        assert inspect_agent_local_kilo_fake_prestart(
            intents, attempt, plan, prepared, changed, image,
        ).decision == "DENY"
    finally:
        start.close()


def test_changed_prepared_bytes_denied(tmp_path):
    start, intents, attempt, plan, prepared, container, image = fixture(tmp_path)
    try:
        Path(prepared["files"][0]["runtime_path"]).write_bytes(b"changed")
        assert inspect_agent_local_kilo_fake_prestart(
            intents, attempt, plan, prepared, container, image,
        ).decision == "DENY"
    finally:
        start.close()


def test_missing_image_environment_denied(tmp_path):
    start, intents, attempt, plan, prepared, container, image = fixture(tmp_path)
    try:
        del image["Config"]["Env"]
        assert inspect_agent_local_kilo_fake_prestart(
            intents, attempt, plan, prepared, container, image,
        ).reason == "RECEIVER_ENV_MISMATCH"
    finally:
        start.close()
