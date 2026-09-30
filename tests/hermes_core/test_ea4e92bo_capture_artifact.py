import hashlib

import pytest

from tools.hermes_core.capture_qualification_authority import (
    CaptureArtifactInvalid, CaptureQualificationArtifact, SCHEMA_ID,
)


TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."


def artifact(**changes):
    value = dict(
        schema_id=SCHEMA_ID,
        authorization_id="cap-auth:one", issue_request_id="cap-issue:one",
        approval_id="cap-approval:one", operator_id="operator:one",
        run_id="cap-run:one", receiver_id="opencode-cli-agent",
        task_sha256=hashlib.sha256(TASK).hexdigest(), source_commit="a" * 40,
        executable_sha256="b" * 64, config_sha256="c" * 64,
        transport_id="d" * 64, model_binding_id="e" * 64,
        provider_budget_id="cap-budget:one",
        issued_at="2026-09-30T00:00:00Z", expires_at="2026-09-30T00:05:00Z",
        process_start_limit=1, nonce="nonce:one",
    )
    value.update(changes)
    return value


def current(value, **changes):
    observed = dict(
        task=TASK, now="2026-09-30T00:00:01Z",
        receiver_id=value.receiver_id, source_commit=value.source_commit,
        executable_sha256=value.executable_sha256,
        config_sha256=value.config_sha256, transport_id=value.transport_id,
        model_binding_id=value.model_binding_id,
        provider_budget_id=value.provider_budget_id,
    )
    observed.update(changes)
    return observed


def test_exact_schema_hash_and_current_material():
    value = CaptureQualificationArtifact.from_mapping(artifact())
    assert value.sha256() == hashlib.sha256(value.canonical_bytes()).hexdigest()
    assert value.canonical_bytes().startswith(b'{"approval_id":')
    assert CaptureQualificationArtifact.from_canonical_bytes(value.canonical_bytes()) == value
    value.check_current_material(**current(value))


@pytest.mark.parametrize("change", [
    {"schema_id": "production"}, {"receiver_id": "kilo-agent"},
    {"process_start_limit": True}, {"process_start_limit": 2},
    {"source_commit": "A" * 40}, {"task_sha256": "F" * 64},
    {"authorization_id": "bad/id"}, {"operator_id": ""},
    {"nonce": "cap-auth:one"},
    {"issued_at": "2026-09-30T00:00:00+00:00"},
    {"expires_at": "2026-09-30T00:00:00Z"},
    {"expires_at": "2026-09-30T00:05:01Z"},
])
def test_invalid_artifact_denied(change):
    with pytest.raises(CaptureArtifactInvalid):
        CaptureQualificationArtifact.from_mapping(artifact(**change))


def test_extra_or_missing_field_denied():
    with pytest.raises(CaptureArtifactInvalid):
        CaptureQualificationArtifact.from_mapping(artifact(runtime_scope="production"))
    value = artifact()
    value.pop("approval_id")
    with pytest.raises(CaptureArtifactInvalid):
        CaptureQualificationArtifact.from_mapping(value)


def test_direct_construction_cannot_bypass_validation():
    with pytest.raises(CaptureArtifactInvalid):
        CaptureQualificationArtifact(**artifact(source_commit="A" * 40))
    with pytest.raises(CaptureArtifactInvalid):
        CaptureQualificationArtifact(**artifact(process_start_limit=2))


@pytest.mark.parametrize("raw", [
    b'{"schema_id":"production","schema_id":"production"}',
    b'{}', b'not-json', b'\xff',
])
def test_noncanonical_or_duplicate_json_denied(raw):
    with pytest.raises(CaptureArtifactInvalid):
        CaptureQualificationArtifact.from_canonical_bytes(raw)


def test_pretty_json_denied_even_when_fields_match():
    value = CaptureQualificationArtifact.from_mapping(artifact())
    with pytest.raises(CaptureArtifactInvalid, match="canonical"):
        CaptureQualificationArtifact.from_canonical_bytes(value.canonical_bytes() + b" ")


@pytest.mark.parametrize("change", [
    {"task": b"changed"}, {"task": b""}, {"task": b"x" * 65537},
    {"now": "2026-09-29T23:59:59Z"},
    {"now": "2026-09-30T00:05:00Z"},
    {"source_commit": "f" * 40}, {"executable_sha256": "f" * 64},
    {"config_sha256": "f" * 64}, {"transport_id": "f" * 64},
    {"model_binding_id": "f" * 64}, {"provider_budget_id": "other"},
    {"receiver_id": "kilo-agent"},
])
def test_current_material_mismatch_denied(change):
    value = CaptureQualificationArtifact.from_mapping(artifact())
    with pytest.raises(CaptureArtifactInvalid):
        value.check_current_material(**current(value, **change))
