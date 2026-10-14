"""Synthetic created-object review never authorizes receiver start."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92jb_agent_local_kilo_host_policy_review import fixture
from tools.hermes_core.agent_local_kilo_created_spec_review import (
    review_provisional_kilo_created_spec,
)
from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    build_provisional_kilo_launch_spec,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


def values_with_spec(tmp_path, *, mutate_before_record=None):
    start, values = fixture(tmp_path, mutate_before_record=mutate_before_record)
    spec = build_provisional_kilo_launch_spec(
        values["records"].intents, values["attempt_id"],
        values["v1_plan"], values["prepared"],
    )
    return start, {**values, "spec": spec}


def test_created_spec_match_is_still_not_start_authority(tmp_path):
    start, values = values_with_spec(tmp_path)
    try:
        result = review_provisional_kilo_created_spec(**values)
        assert result.decision == "MATCH"
        assert result.reason == "CREATE_SPEC_REVIEW_ONLY_START_DENIED"
        assert result.receiver_executed is False
        assert result.provenance_checked is False
        assert values["records"].get(values["attempt_id"]).launch_authorized is False
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    lambda c: c.update(Name="/other"),
    lambda c: c["Config"]["Labels"].update({"hermes.ea4e.attempt": "other"}),
    lambda c: c["HostConfig"].update(RestartPolicy={"Name": "always"}),
    lambda c: c["HostConfig"].update(UsernsMode="host"),
    lambda c: c["HostConfig"].update(Ulimits=[{"Name": "nofile"}]),
    lambda c: c["HostConfig"].update(DNS=["8.8.8.8"]),
])
def test_persistently_reported_policy_drift_denies(tmp_path, change):
    start, values = values_with_spec(tmp_path, mutate_before_record=change)
    try:
        assert review_provisional_kilo_created_spec(**values).decision == "DENY"
    finally:
        start.close()


def test_after_record_container_mutation_denies(tmp_path):
    start, values = values_with_spec(tmp_path)
    try:
        changed = values.copy()
        changed["container"] = deepcopy(values["container"])
        changed["container"]["Name"] = "/other"
        result = review_provisional_kilo_created_spec(**changed)
        assert result.decision == "DENY"
        assert result.reason == "HOST_POLICY_REVIEW_MISMATCH"
    finally:
        start.close()


def test_rehashed_caller_spec_mutation_denies(tmp_path):
    start, values = values_with_spec(tmp_path)
    try:
        changed = values.copy()
        changed["spec"] = deepcopy(values["spec"])
        changed["spec"]["labels"]["hermes.ea4e.attempt"] = "other"
        from tools.hermes_core.hashing import sha256_payload
        changed["spec"]["spec_hash"] = sha256_payload({
            key: value for key, value in changed["spec"].items()
            if key != "spec_hash"
        })
        with pytest.raises(DelegationIntegrityError, match="spec mismatch"):
            review_provisional_kilo_created_spec(**changed)
    finally:
        start.close()
