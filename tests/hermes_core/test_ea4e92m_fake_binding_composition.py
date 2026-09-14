"""Test-owned composition only; supplied fixtures are not deployment authority."""

import copy
import hashlib
import json
from pathlib import Path
import re

import pytest

from tools.ea4e92c_provider_call_control import (
    QualificationProviderGate, QualificationScope, ProviderAdmissionDenied,
    provision_budget,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.opencode_provider_binding import (
    ProviderBindingError, build_provider_binding, verify_supplied_binding_evidence,
)


DESIGN = Path(__file__).resolve().parents[2] / (
    ".hermes/handoffs/ea4e/EA-4E.92I-VERSIONED-OPENCODE-BINDING-DESIGN.md"
)
NOW = "2026-09-14T00:00:01Z"


def supplied_fixture():
    material = json.loads(re.findall(r"```json\s*(.*?)```", DESIGN.read_text(
        encoding="utf-8"), re.S)[0])
    config = json.dumps({"model": "ollama/fixture-model"}).encode("utf-8")
    policies = {key: ("fixture-only:" + key).encode("ascii")
                for key in material["deployment"]}
    supplied = dict(runtime_bytes=b"fixture executable", config_bytes=config,
                    policy_bytes=policies)
    material["runtime"]["executable_sha256"] = hashlib.sha256(
        supplied["runtime_bytes"]).hexdigest()
    material["selection"]["config_sha256"] = hashlib.sha256(config).hexdigest()
    material["deployment"] = {key: hashlib.sha256(raw).hexdigest()
                              for key, raw in policies.items()}
    expected_id = build_provider_binding(material).model_binding_id
    return material, supplied, expected_id


def fixture_gate(root, material, expected_id, forward):
    body = json.dumps({"model": material["selection"]["model_id"],
                       "messages": [{"role": "user", "content": "fixture task"}],
                       "stream": False}, separators=(",", ":")).encode("utf-8")
    scope = QualificationScope(
        "fixture-composition", "a" * 40, "b" * 64, expected_id, "c" * 64,
        material["provider"]["receiver_base_url"] + "/chat/completions",
        material["selection"]["model_id"], hashlib.sha256(body).hexdigest(),
        "2026-09-14T00:00:00Z", "2026-09-14T00:05:00Z",
    )
    store = DurableInvocationAuthorizationStore.initialize(
        root / "budget.sqlite3", anchor_path=root / "anchor.json")
    provision_budget(store, scope)
    return QualificationProviderGate(store, scope, forward=forward), body


def compose_fixture(material, supplied, expected_id, gate, captured_body, **changes):
    binding = verify_supplied_binding_evidence(
        material, expected_binding_id=expected_id, **supplied)
    # This check is a test-owned integration model, not production admission.
    if binding.model_binding_id != gate.scope.model_binding_id:
        raise ProviderBindingError("fixture scope binding mismatch")
    request = dict(run_id=gate.scope.run_id, method="POST",
                   endpoint=gate.scope.endpoint, model=gate.scope.model,
                   body=captured_body, now=NOW)
    request.update(changes)
    return gate.request(**request)


@pytest.mark.parametrize("changed", ["runtime", "config", "expected-id", "scope-id",
    "missing-policy", "extra-policy", "gate_contract_sha256", "egress_policy_sha256",
    "cpu_policy_sha256", "cleanup_contract_sha256"])
def test_evidence_denial_precedes_consumption(tmp_path, changed):
    material, supplied, expected_id = supplied_fixture()
    calls = []
    gate_id = "d" * 64 if changed == "scope-id" else expected_id
    gate, body = fixture_gate(tmp_path, material, gate_id,
                              lambda raw: calls.append(raw) or b"ok")
    if changed in ("runtime", "config"):
        supplied[changed + "_bytes"] += b"changed"
    elif changed == "expected-id":
        expected_id = "e" * 64
    elif changed == "missing-policy":
        supplied["policy_bytes"].pop("cpu_policy_sha256")
    elif changed == "extra-policy":
        supplied["policy_bytes"]["extra"] = b"unreviewed"
    elif changed != "scope-id":
        supplied["policy_bytes"][changed] += b"changed"
    with pytest.raises(ProviderBindingError):
        compose_fixture(material, supplied, expected_id, gate, body)
    assert calls == []
    assert gate.store.consumed_count() == 0


@pytest.mark.parametrize("change", [{"body": b"different body"}, {"model": "other"},
    {"endpoint": "http://127.0.0.1:19002/v1/chat/completions"},
    {"cancelled": True}, {"revoked": True}, {"now": "2026-09-14T00:05:00Z"}])
def test_bound_request_denial_never_forwards(tmp_path, change):
    material, supplied, expected_id = supplied_fixture()
    calls = []
    gate, body = fixture_gate(tmp_path, material, expected_id,
                              lambda raw: calls.append(raw) or b"ok")
    with pytest.raises(ProviderAdmissionDenied):
        compose_fixture(material, supplied, expected_id, gate, body, **change)
    assert calls == []
    assert gate.store.consumed_count() == 0


def test_verified_fixture_once_after_reopen(tmp_path):
    material, supplied, expected_id = supplied_fixture()
    calls = []
    gate, body = fixture_gate(tmp_path, material, expected_id,
                              lambda raw: calls.append(raw) or b"fixture response")
    assert compose_fixture(material, supplied, expected_id, gate, body) == b"fixture response"
    reopened = DurableInvocationAuthorizationStore(
        gate.store.path, anchor_path=gate.store.anchor_path)
    retry = QualificationProviderGate(reopened, gate.scope, forward=gate.forward)
    with pytest.raises(ProviderAdmissionDenied):
        compose_fixture(material, supplied, expected_id, retry, body)
    assert calls == [body]
    assert reopened.consumed_count() == 1


def test_supplied_snapshot_mutation_does_not_change_verified_binding():
    material, supplied, expected_id = supplied_fixture()
    binding = verify_supplied_binding_evidence(material,
                                               expected_binding_id=expected_id, **supplied)
    original = copy.deepcopy(material)
    material["selection"]["model_id"] = "other"
    supplied["policy_bytes"]["cpu_policy_sha256"] += b"changed"
    assert json.loads(binding.canonical_bytes) == original
    with pytest.raises(ProviderBindingError):
        verify_supplied_binding_evidence(material, expected_binding_id=expected_id, **supplied)
