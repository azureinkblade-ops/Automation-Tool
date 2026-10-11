"""Pure model-binding qualification; no OpenCode process or provider call."""

import hashlib
import json

import pytest

from tools.hermes_core.opencode_capture_model_binding import (
    CaptureModelBindingError, build_binding, parse_binding,
)


def material(**changes):
    value = dict(
        schema_id="hermes.opencode-capture-model-binding/v1",
        receiver_id="opencode-cli-agent", provider_id="opencode",
        model_id="nemotron-3-ultra-free", request_model_id="nemotron-3-ultra-free",
        provider_base_url="https://example.invalid/v1",
        route="/v1/chat/completions", stream=True,
        runtime_sha256="a" * 64, config_sha256="b" * 64,
        transport_id="c" * 64, credential_policy_sha256="d" * 64,
        egress_policy_sha256="e" * 64,
        qualification_status="UNQUALIFIED_NONLIVE",
    )
    value.update(changes)
    return value


def test_canonical_binding_hashes_exact_nonlive_material():
    binding = build_binding(material())
    assert parse_binding(binding.canonical_bytes) == binding
    assert binding.binding_id == hashlib.sha256(binding.canonical_bytes).hexdigest()
    assert binding.provider_id == "opencode"
    assert binding.request_model_id == "nemotron-3-ultra-free"


@pytest.mark.parametrize("change", [
    {"model_id": "qwen3:14b"}, {"request_model_id": "qwen3:14b"},
    {"provider_id": "ollama"}, {"provider_base_url": "https://other.invalid/v1"},
    {"runtime_sha256": "f" * 64}, {"config_sha256": "f" * 64},
    {"transport_id": "f" * 64}, {"credential_policy_sha256": "f" * 64},
    {"egress_policy_sha256": "f" * 64},
])
def test_identity_or_policy_change_rolls_binding_hash(change):
    assert build_binding(material(**change)).binding_id != build_binding(material()).binding_id


@pytest.mark.parametrize("change", [
    {"schema_id": "other"}, {"receiver_id": "kilo-cli-agent"},
    {"route": "/other"}, {"stream": False}, {"stream": 1},
    {"runtime_sha256": "bad"}, {"config_sha256": "A" * 64},
    {"qualification_status": "QUALIFIED"},
    {"provider_base_url": "http://example.invalid/v1"},
    {"provider_base_url": "https://user:pass@example.invalid/v1"},
    {"provider_base_url": "https://example.invalid/v1?key=x"},
    {"provider_base_url": "https://example.invalid/v1#fragment"},
    {"provider_base_url": "https://example.invalid/v1?"},
    {"provider_base_url": "https://example.invalid\\extra"},
])
def test_invalid_or_unreviewed_policy_denied(change):
    with pytest.raises(CaptureModelBindingError):
        build_binding(material(**change))


def test_extra_missing_duplicate_or_noncanonical_bytes_denied():
    good = build_binding(material()).canonical_bytes
    for value in (good + b"\n", b"not json", b"\xff", b"[]",
                  b'{"schema_id":"x","schema_id":"y"}'):
        with pytest.raises(CaptureModelBindingError):
            parse_binding(value)
    for changed in ({**material(), "extra": True},
                    {k: v for k, v in material().items() if k != "model_id"}):
        with pytest.raises(CaptureModelBindingError):
            build_binding(changed)
    with pytest.raises(CaptureModelBindingError):
        parse_binding(json.dumps(material(), indent=2).encode())
