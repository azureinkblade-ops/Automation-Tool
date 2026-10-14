"""No Docker create/start: task-bound fake Kilo launch-spec proposal."""

from copy import deepcopy
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ig_agent_local_kilo_fake_prestart import fixture
from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    build_provisional_kilo_launch_spec,
    verify_provisional_kilo_launch_spec,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


def test_spec_binds_dummy_inputs_and_remains_non_launchable(tmp_path):
    start, intents, attempt, plan, prepared, _, _ = fixture(tmp_path)
    try:
        spec = build_provisional_kilo_launch_spec(
            intents, attempt, plan, prepared,
        )
        assert spec == build_provisional_kilo_launch_spec(
            intents, attempt, plan, prepared,
        )
        assert spec["spec_hash"] == sha256_payload({
            key: value for key, value in spec.items() if key != "spec_hash"
        })
        assert spec["attempt_id"] == attempt
        assert spec["labels"]["hermes.ea4e.attempt"] == attempt
        assert spec["candidate_hash"] == prepared["candidate_hash"]
        assert spec["image_index"] == plan["image_index"]
        assert spec["network"]["internal"] is True
        assert spec["credential_class"] == "DUMMY_LOCAL_ONLY"
        assert spec["create_authorized"] is False
        assert spec["launch_authorized"] is False
        assert spec["provenance_checked"] is False
        assert spec["mounts"][0]["source"].startswith(prepared["root"])
        assert spec["mounts"][1]["source"].startswith(prepared["root"])
        assert verify_provisional_kilo_launch_spec(
            intents, attempt, plan, prepared, spec,
        ) == spec
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    lambda spec: spec.update(create_authorized=True),
    lambda spec: spec["labels"].update({"hermes.ea4e.attempt": "other"}),
    lambda spec: spec["mounts"][0].update(source="C:/other"),
    lambda spec: spec["host_policy"].update(memory_bytes=0),
    lambda spec: spec["host_policy"]["cap_drop"].clear(),
    lambda spec: spec["network"].update(internal=False),
    lambda spec: spec.update(spec_hash="0" * 64),
])
def test_modified_spec_denied(tmp_path, change):
    start, intents, attempt, plan, prepared, _, _ = fixture(tmp_path)
    try:
        spec = build_provisional_kilo_launch_spec(
            intents, attempt, plan, prepared,
        )
        modified = deepcopy(spec)
        change(modified)
        with pytest.raises(DelegationIntegrityError, match="spec mismatch"):
            verify_provisional_kilo_launch_spec(
                intents, attempt, plan, prepared, modified,
            )
    finally:
        start.close()


def test_changed_prepared_bytes_denied(tmp_path):
    start, intents, attempt, plan, prepared, _, _ = fixture(tmp_path)
    try:
        spec = build_provisional_kilo_launch_spec(
            intents, attempt, plan, prepared,
        )
        Path(prepared["files"][0]["runtime_path"]).write_bytes(b"changed")
        with pytest.raises(DelegationIntegrityError, match="input bytes denied"):
            verify_provisional_kilo_launch_spec(
                intents, attempt, plan, prepared, spec,
            )
    finally:
        start.close()
