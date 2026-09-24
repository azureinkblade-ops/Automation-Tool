"""Current successor qualification, separate from historical 64B evidence."""

from dataclasses import replace
from pathlib import Path
import runpy

import pytest

from tools.hermes_core import kilo_adapter as adapter
from tools.hermes_core import kilo_successor_binding as binding
from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.production_deployment_composition import ProductionDeploymentCompositionError


@pytest.fixture
def harness():
    return runpy.run_path(str(Path(__file__).with_name("test_ea4e64b_nonlive_kilo_7_5_16_successor.py")))


def test_current_binary_and_binding_are_exact():
    identity = adapter.resolve_pinned_binary({})
    assert identity.version == "7.7.9"
    assert identity.sha256 == "9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07"
    assert identity.size_bytes == 175458816
    assert identity.metadata_probe_spawned is False
    assert adapter.KILO_TRANSPORT_CONTRACT_ID == "b97e4902056689fd7655c75955dcecb906d372b1a7dce012d9d0a1891472be06"
    assert binding.KILO_EXECUTABLE_SUCCESSOR_BINDING_ID == "653317206aaba6161ff67d2a199ded169daa19869ea578fd4e8ccb2413570ddd"
    material = binding.kilo_executable_successor_binding_material()
    assert material["predecessor_executable_version"] == "7.7.2"
    assert material["automatic_substitution"] is False


def predecessor(deployment):
    payload = deployment.binding_store.load()
    old_id = payload["binding_id"]
    payload["binary_path"] = binding.HISTORICAL_KILO_7_7_2_PATH
    payload["binary_sha256"] = binding.HISTORICAL_KILO_7_7_2_SHA256
    payload["binary_version"] = "7.7.2"
    payload["executable_binding_id"] = binding.HISTORICAL_KILO_7_7_2_EXECUTABLE_BINDING_ID
    payload["enablement"]["transport_contract_id"] = binding.HISTORICAL_KILO_7_7_2_TRANSPORT_CONTRACT_ID
    with deployment.binding_store._connect() as connection:
        connection.execute(
            "UPDATE production_executor_binding_state SET payload_json=?, payload_hash=? WHERE singleton=1",
            (canonical_json(payload), sha256_payload(payload)),
        )
        connection.commit()
    return old_id


def test_old_binding_requires_explicit_roll(tmp_path, harness):
    counter = {"calls": 0}
    deployment = harness["provision"](tmp_path, counter)
    predecessor(deployment)
    with pytest.raises(ProductionDeploymentCompositionError, match="PERSISTED_KILO_BINDING_IDENTITY_MISMATCH"):
        harness["provision"](tmp_path, counter)
    assert counter["calls"] == 0


def test_roll_replay_lineage_and_old_authority_rejection(tmp_path, harness):
    counter = {"calls": 0}
    original = harness["provision"](tmp_path, counter)
    lineage = original.activation_store.lineage()
    old_id = predecessor(original)
    successor = harness["provision"](tmp_path, counter, successor_roll_explicit=True)
    assert successor.binding_handle.binding_id != old_id
    assert successor.activation_store.lineage() == lineage
    reopened = harness["provision"](tmp_path, counter)
    assert reopened.binding_handle.binding_id == successor.binding_handle.binding_id
    request = replace(harness["activation_request"](successor), executor_binding_id=old_id)
    assert harness["activation_policy"](successor).evaluate(request)[1] == "EXECUTOR_BINDING_ID_MISMATCH"
    assert successor.activation_store.has_outstanding() is False
    assert counter["calls"] == 0


def test_current_contracts_match_frozen_candidate():
    baseline = runpy.run_path(str(Path(__file__).with_name("test_ea4e34b_kilo_successor_contract_roll.py")))
    candidate = runpy.run_path(str(Path(__file__).with_name("test_ea4e92ag_kilo779_static_candidate.py")))
    assert baseline["_current_ids"]() == candidate["CANDIDATE_IDS"]
    assert binding.HISTORICAL_EA4E_7_7_2_CONTRACT_IDS != candidate["CANDIDATE_IDS"]


def test_stale_imported_cache_changes_invocation_identity(monkeypatch):
    from tools.hermes_core import production_invocation_authorization as invocation

    assert invocation.CURRENT_EA4E17_ISSUANCE_CONTRACT_ID == binding.CURRENT_EA4E17_ISSUANCE_CONTRACT_ID
    assert invocation.CURRENT_EA4E21_BINDING_CONTRACT_ID == binding.CURRENT_EA4E21_BINDING_CONTRACT_ID
    assert invocation.CURRENT_EA4E22_INTEGRATION_CONTRACT_ID == binding.CURRENT_EA4E22_INTEGRATION_CONTRACT_ID
    current = invocation.compute_ea4e23_invocation_contract_id()
    monkeypatch.setattr(invocation, "CURRENT_EA4E17_ISSUANCE_CONTRACT_ID", binding.HISTORICAL_EA4E_7_7_2_CONTRACT_IDS["EA-4E.17"])
    assert invocation.compute_ea4e23_invocation_contract_id() != current
