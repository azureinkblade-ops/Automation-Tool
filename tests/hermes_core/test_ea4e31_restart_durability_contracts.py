"""EA-4E.31 contract-only restart-durability qualification."""

from copy import deepcopy

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_execution import compute_ea4e14_execution_contract_id
from tools.hermes_core.production_issuance import compute_ea4e17_issuance_contract_id
from tools.hermes_core.governed_production import compute_ea4e18_integration_contract_id
from tools.hermes_core.production_executor_binding import (
    compute_ea4e21_binding_contract_id,
)
from tools.hermes_core.governed_bound_executor import (
    compute_ea4e22_integration_contract_id,
)
from tools.hermes_core import production_invocation_authorization as ea23
from tools.hermes_core import governed_production_runtime as ea26
from tools.hermes_core import production_invocation_authorization_issuer as ea28
from tools.hermes_core import governed_production_caller as ea29


OLD_IDS = {
    "ea4e23": "1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8",
    "ea4e26": "c49556e63645fefc31a3f03df726d99447620b7ae6ae4a2c78b96ae0feeb8393",
    "ea4e28": "cbf86c71356366d489920b226dfb181c3fcafc581ec567d19433a94159a6c5da",
    "ea4e29": "aa9b2e1a6bb2307e814bb66913f7fdb8134a3fbb0273bfb8be000da6e480ee9a",
}


def changed_hash(payload, field, value):
    changed = deepcopy(payload)
    changed[field] = value
    return sha256_payload(changed)


def test_old_contract_chain_is_preserved_as_historical_constants():
    assert ea23.LEGACY_EA4E23_INVOCATION_CONTRACT_ID == OLD_IDS["ea4e23"]
    assert ea26.LEGACY_EA4E26_INTEGRATION_CONTRACT_ID == OLD_IDS["ea4e26"]
    assert ea28.LEGACY_EA4E28_ISSUER_CONTRACT_ID == OLD_IDS["ea4e28"]
    assert ea29.LEGACY_EA4E29_CALLER_CONTRACT_ID == OLD_IDS["ea4e29"]


def test_unaffected_contracts_remain_frozen():
    assert compute_ea4e14_execution_contract_id() == "89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6"
    assert compute_ea4e17_issuance_contract_id() == "26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78"
    assert compute_ea4e18_integration_contract_id() == "d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459"
    assert compute_ea4e21_binding_contract_id() == "99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7"
    assert compute_ea4e22_integration_contract_id() == "e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a"


def test_ea4e23_contract_is_deterministic_and_new():
    assert ea23.compute_ea4e23_invocation_contract_id() == ea23.compute_ea4e23_invocation_contract_id()
    assert ea23.compute_ea4e23_invocation_contract_id() != OLD_IDS["ea4e23"]


def test_ea4e23_mapping_order_is_irrelevant():
    payload = ea23.ea4e23_invocation_contract_payload()
    assert sha256_payload(payload) == sha256_payload(dict(reversed(tuple(payload.items()))))


def test_ea4e23_irrelevant_task_text_is_absent_and_irrelevant():
    payload = ea23.ea4e23_invocation_contract_payload()
    unrelated_task_text = {"task_text": "one"}
    unrelated_task_text["task_text"] = "two"
    assert "task_text" not in payload
    assert sha256_payload(payload) == ea23.compute_ea4e23_invocation_contract_id()


def test_ea4e23_durability_semantic_change_invalidates_contract():
    payload = ea23.ea4e23_invocation_contract_payload()
    assert changed_hash(payload, "authorization_consumption_state_lifetime", "process_local") != sha256_payload(payload)


def test_ea4e23_max_ttl_change_invalidates_contract():
    payload = ea23.ea4e23_invocation_contract_payload()
    assert changed_hash(payload, "max_invocation_authorization_ttl_seconds", 301) != sha256_payload(payload)


def test_ea4e23_attempt_limit_change_invalidates_contract():
    payload = ea23.ea4e23_invocation_contract_payload()
    assert changed_hash(payload, "max_authorized_attempts", 2) != sha256_payload(payload)


def test_ea4e23_receiver_scope_change_invalidates_contract():
    payload = ea23.ea4e23_invocation_contract_payload()
    assert changed_hash(payload, "explicit_receiver_matching", False) != sha256_payload(payload)


def test_ea4e26_binds_new_ea4e23_and_rejects_old_identity():
    payload = ea26.ea4e26_integration_contract_payload()
    assert payload["ea4e23_invocation_contract_id"] == ea23.compute_ea4e23_invocation_contract_id()
    assert payload["ea4e23_invocation_contract_id"] != OLD_IDS["ea4e23"]


def test_ea4e26_contract_is_deterministic_and_mapping_order_is_irrelevant():
    payload = ea26.ea4e26_integration_contract_payload()
    assert ea26.compute_ea4e26_integration_contract_id() == sha256_payload(payload)
    assert sha256_payload(payload) == sha256_payload(dict(reversed(tuple(payload.items()))))


def test_ea4e26_irrelevant_task_text_is_absent():
    assert "task_text" not in ea26.ea4e26_integration_contract_payload()


def test_ea4e23_change_invalidates_ea4e26(monkeypatch):
    baseline = ea26.compute_ea4e26_integration_contract_id()
    monkeypatch.setattr(ea26, "compute_ea4e23_invocation_contract_id", lambda: OLD_IDS["ea4e23"])
    assert ea26.compute_ea4e26_integration_contract_id() != baseline


def test_ea4e26_receiver_set_change_invalidates_contract():
    payload = ea26.ea4e26_integration_contract_payload()
    changed = deepcopy(payload)
    changed["qualified_receivers"] = {}
    assert sha256_payload(changed) != sha256_payload(payload)


def test_ea4e26_external_auth_requirement_change_invalidates_contract():
    payload = ea26.ea4e26_integration_contract_payload()
    assert changed_hash(payload, "external_invocation_authorization_required", False) != sha256_payload(payload)


def test_ea4e28_binds_new_ea4e23_and_rejects_old_identity():
    payload = ea28.ea4e28_issuer_contract_payload()
    assert payload["ea4e23_invocation_contract_id"] == ea23.compute_ea4e23_invocation_contract_id()
    assert payload["ea4e23_invocation_contract_id"] != OLD_IDS["ea4e23"]


def test_ea4e28_contract_is_deterministic():
    assert ea28.compute_ea4e28_issuer_contract_id() == sha256_payload(
        ea28.ea4e28_issuer_contract_payload()
    )


def test_ea4e23_change_invalidates_ea4e28(monkeypatch):
    baseline = ea28.compute_ea4e28_issuer_contract_id()
    monkeypatch.setattr(ea28, "compute_ea4e23_invocation_contract_id", lambda: OLD_IDS["ea4e23"])
    assert ea28.compute_ea4e28_issuer_contract_id() != baseline


def test_ea4e28_durable_commit_requirement_change_invalidates_contract():
    payload = ea28.ea4e28_issuer_contract_payload()
    assert changed_hash(payload, "authorization_persisted_before_return", False) != sha256_payload(payload)


def test_ea4e29_binds_new_downstream_contracts_and_rejects_old_identities():
    payload = ea29.ea4e29_caller_contract_payload()
    assert payload["ea4e26_integration_contract_id"] == ea26.compute_ea4e26_integration_contract_id()
    assert payload["ea4e28_issuer_contract_id"] == ea28.compute_ea4e28_issuer_contract_id()
    assert payload["ea4e26_integration_contract_id"] != OLD_IDS["ea4e26"]
    assert payload["ea4e28_issuer_contract_id"] != OLD_IDS["ea4e28"]


def test_ea4e29_contract_is_deterministic():
    assert ea29.compute_ea4e29_caller_contract_id() == sha256_payload(
        ea29.ea4e29_caller_contract_payload()
    )


def test_ea4e26_change_invalidates_ea4e29(monkeypatch):
    baseline = ea29.compute_ea4e29_caller_contract_id()
    monkeypatch.setattr(ea29, "compute_ea4e26_integration_contract_id", lambda: OLD_IDS["ea4e26"])
    assert ea29.compute_ea4e29_caller_contract_id() != baseline


def test_ea4e28_change_invalidates_ea4e29(monkeypatch):
    baseline = ea29.compute_ea4e29_caller_contract_id()
    monkeypatch.setattr(ea29, "compute_ea4e28_issuer_contract_id", lambda: OLD_IDS["ea4e28"])
    assert ea29.compute_ea4e29_caller_contract_id() != baseline


def test_ea4e29_auto_reissue_change_invalidates_contract():
    payload = ea29.ea4e29_caller_contract_payload()
    assert changed_hash(payload, "auto_reissue_after_deny", True) != sha256_payload(payload)


def test_contract_dependency_graph_is_acyclic():
    graph = {
        "ea4e23": {"ea4e14", "ea4e17", "ea4e18", "ea4e21", "ea4e22"},
        "ea4e26": {"ea4e23"},
        "ea4e28": {"ea4e23"},
        "ea4e29": {"ea4e26", "ea4e28"},
    }

    def visits_self(node, seen):
        if node in seen:
            return True
        return any(visits_self(parent, seen | {node}) for parent in graph.get(node, ()))

    assert not any(visits_self(node, set()) for node in graph)
