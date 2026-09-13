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
    assert identity.version == "7.6.2"
    assert identity.sha256 == "5d54b522d8a59228951d141cd70438c29115963ecb38d7cdfcf313f59c0f865b"
    assert identity.size_bytes == 173595648
    assert identity.metadata_probe_spawned is False
    assert adapter.KILO_TRANSPORT_CONTRACT_ID == "3c54405378c314e52afc95fbe055fd0a4249f0d78a515a108126b8e4fd73363e"
    assert binding.KILO_EXECUTABLE_SUCCESSOR_BINDING_ID == "b89f9f02f3e99cf70a98de8b4fb02b545e51855bb7340ed829ece749256b9be1"
    material = binding.kilo_executable_successor_binding_material()
    assert material["predecessor_executable_version"] == "7.5.16"
    assert material["automatic_substitution"] is False


def predecessor(deployment):
    payload = deployment.binding_store.load()
    old_id = payload["binding_id"]
    payload["binary_path"] = binding.HISTORICAL_KILO_7_5_16_PATH
    payload["binary_sha256"] = binding.HISTORICAL_KILO_7_5_16_SHA256
    payload["binary_version"] = "7.5.16"
    payload["executable_binding_id"] = binding.HISTORICAL_KILO_7_5_16_EXECUTABLE_BINDING_ID
    payload["enablement"]["transport_contract_id"] = binding.HISTORICAL_KILO_7_5_16_TRANSPORT_CONTRACT_ID
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
    candidate = runpy.run_path(str(Path(__file__).with_name("test_ea4e67c_successor_candidate_contract_diff.py")))
    assert baseline["_current_ids"]() == candidate["EXPECTED_IDS"]
    assert binding.HISTORICAL_EA4E_7_5_16_CONTRACT_IDS != candidate["EXPECTED_IDS"]


def test_stale_imported_cache_changes_invocation_identity(monkeypatch):
    from tools.hermes_core import production_invocation_authorization as invocation

    assert invocation.CURRENT_EA4E17_ISSUANCE_CONTRACT_ID == binding.CURRENT_EA4E17_ISSUANCE_CONTRACT_ID
    assert invocation.CURRENT_EA4E21_BINDING_CONTRACT_ID == binding.CURRENT_EA4E21_BINDING_CONTRACT_ID
    assert invocation.CURRENT_EA4E22_INTEGRATION_CONTRACT_ID == binding.CURRENT_EA4E22_INTEGRATION_CONTRACT_ID
    current = invocation.compute_ea4e23_invocation_contract_id()
    monkeypatch.setattr(invocation, "CURRENT_EA4E17_ISSUANCE_CONTRACT_ID", binding.HISTORICAL_EA4E_7_5_16_CONTRACT_IDS["EA-4E.17"])
    assert invocation.compute_ea4e23_invocation_contract_id() != current
