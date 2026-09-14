import copy
import hashlib
import json
from pathlib import Path
import re

import pytest

from tools.hermes_core.opencode_provider_binding import (
    ProviderBindingError, build_provider_binding, parse_provider_binding,
    verify_supplied_binding_evidence,
)


DESIGN = Path(__file__).resolve().parents[2] / ".hermes/handoffs/ea4e/EA-4E.92I-VERSIONED-OPENCODE-BINDING-DESIGN.md"
GOLDEN = "a7bfd43b26e706c78ae43b0c8880ce80dae5d82b167e2fac666c3c49ea57ff37"


def material():
    text = DESIGN.read_text(encoding="utf-8")
    return json.loads(re.findall(r"```json\s*(.*?)```", text, re.S)[0])


def set_value(value, path, replacement):
    keys = path.split(".")
    for key in keys[:-1]:
        value = value[key]
    value[keys[-1]] = replacement


def test_golden_roundtrip_reordered_and_snapshot():
    value = material()
    binding = build_provider_binding(value)
    assert binding.model_binding_id == GOLDEN
    assert len(binding.canonical_bytes) == 1646
    assert parse_provider_binding(binding.canonical_bytes) == binding
    assert build_provider_binding(dict(reversed(list(value.items())))) == binding
    value["selection"]["model_id"] = "changed"
    assert build_provider_binding(value).model_binding_id != GOLDEN
    assert json.loads(binding.canonical_bytes)["selection"]["model_id"] == "fixture-model"


@pytest.mark.parametrize("path,replacement", [
    ("schema_id", "unknown"), ("artifact_version", True), ("artifact_version", 2),
    ("receiver_id", "kilo-cli-agent"), ("receiver_class", "KILO"),
    ("transport_contract_id", "A" * 64), ("transport_contract_id", "a" * 63),
    ("runtime.executable_version", ""), ("runtime.executable_version", " x"),
    ("runtime.executable_version", "x\n"), ("runtime.executable_version", "\u00e9"),
    ("selection.model_id", None), ("selection.provider_id", "other"),
    ("selection.agent_id", "other"), ("selection.mechanism", "CONFIG"),
    ("selection.ambient_config_allowed", True), ("selection.project_config_allowed", 0),
    ("selection.task_model_override_allowed", True),
    ("selection.task_provider_override_allowed", True),
    ("selection.task_agent_override_allowed", True),
    ("selection.session_inheritance_allowed", True),
    ("provider.package_id", "other"), ("provider.gate_route", "/other"),
    ("provider.credential_policy", "API_KEY"), ("provider.stream_allowed", True),
    ("provider.redirect_limit", False), ("provider.network_retry_limit", 1),
    ("provider.max_provider_calls", 2), ("provider.max_request_bytes", True),
    ("provider.max_request_bytes", 0), ("provider.max_request_bytes", 65537),
    ("provider.max_response_bytes", 1.0),
    ("deployment.cpu_policy_sha256", "x" * 64),
], ids=[f"invalid-{i}" for i in range(33)])
def test_invalid_fields(path, replacement):
    value = material()
    set_value(value, path, replacement)
    with pytest.raises(ProviderBindingError):
        build_provider_binding(value)


@pytest.mark.parametrize("prefix", ["", "runtime", "selection", "provider", "deployment"])
@pytest.mark.parametrize("change", ["missing", "extra", "wrong-type"])
def test_exact_recursive_schema(prefix, change):
    value = material()
    target = value if not prefix else value[prefix]
    if change == "missing":
        target.pop(next(iter(target)))
    elif change == "extra":
        target["model_binding_id"] = GOLDEN
    elif prefix:
        value[prefix] = []
    else:
        value = []
    with pytest.raises(ProviderBindingError):
        build_provider_binding(value)


@pytest.mark.parametrize("path", ["relative", "C:relative", "C:/file", "\\\\server\\file",
    "\\\\?\\C:\\file", "C:\\a\\..\\file", "C:\\a\\.\\file", "C:\\\\file",
    "C:\\file.", "C:\\file ", "C:\\CON.txt", "C:\\x:file", "C:\\*.exe"])
@pytest.mark.parametrize("field", ["runtime.executable_path", "selection.config_path"])
def test_path_denials(path, field):
    value = material()
    set_value(value, field, path)
    with pytest.raises(ProviderBindingError):
        build_provider_binding(value)


@pytest.mark.parametrize("url", ["http://localhost:19001/v1", "https://127.0.0.1:19001/v1",
    "http://127.0.0.1/v1", "http://127.0.0.1:0/v1", "http://127.0.0.1:65536/v1",
    "http://127.0.0.1:019001/v1", "http://user@127.0.0.1:19001/v1",
    "http://127.0.0.1:19001/v1?x=1", "http://127.0.0.1:19001/v1#x",
    "http://127.0.0.1:19001/other", "http://[::1]:19001/v1"])
@pytest.mark.parametrize("field", ["receiver_base_url", "upstream_base_url"])
def test_endpoint_denials(url, field):
    value = material()
    value["provider"][field] = url
    with pytest.raises(ProviderBindingError):
        build_provider_binding(value)


def test_same_endpoint_denied_and_limits_inclusive():
    value = material()
    value["provider"]["upstream_base_url"] = value["provider"]["receiver_base_url"]
    with pytest.raises(ProviderBindingError):
        build_provider_binding(value)
    value = material()
    for limit in (1, 65536):
        value["provider"]["max_request_bytes"] = limit
        value["provider"]["max_response_bytes"] = limit
        build_provider_binding(value)


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"[]", b"null", b'{"x":NaN}',
    b'{"x":Infinity}', b'{"x":1,"x":2}', b'{"outer":{"x":1,"x":2}}', "{}"])
def test_parser_denies(raw):
    with pytest.raises(ProviderBindingError):
        parse_provider_binding(raw)


def evidence():
    value = material()
    runtime, config = b"fixture executable", b"fixture config"
    policies = {key: key.encode("ascii") for key in value["deployment"]}
    value["runtime"]["executable_sha256"] = hashlib.sha256(runtime).hexdigest()
    value["selection"]["config_sha256"] = hashlib.sha256(config).hexdigest()
    value["deployment"] = {key: hashlib.sha256(raw).hexdigest() for key, raw in policies.items()}
    return value, dict(expected_binding_id=build_provider_binding(value).model_binding_id,
                       runtime_bytes=runtime, config_bytes=config, policy_bytes=policies)


def test_supplied_evidence_success():
    value, kwargs = evidence()
    assert verify_supplied_binding_evidence(value, **kwargs) == build_provider_binding(value)


@pytest.mark.parametrize("change", ["legacy-id", "absent-id", "runtime", "config",
    "missing-policy", "extra-policy", "changed-policy", "wrong-policy-type"])
def test_supplied_evidence_denials(change):
    value, kwargs = evidence()
    if change == "legacy-id":
        kwargs["expected_binding_id"] = "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371"
    elif change == "absent-id":
        kwargs["expected_binding_id"] = None
    elif change in ("runtime", "config"):
        kwargs[change + "_bytes"] += b" "
    elif change == "missing-policy":
        kwargs["policy_bytes"].pop(next(iter(kwargs["policy_bytes"])))
    elif change == "extra-policy":
        kwargs["policy_bytes"]["extra"] = b"x"
    elif change == "changed-policy":
        kwargs["policy_bytes"][next(iter(kwargs["policy_bytes"]))] += b" "
    else:
        kwargs["policy_bytes"] = []
    with pytest.raises(ProviderBindingError):
        verify_supplied_binding_evidence(value, **kwargs)


def test_all_leaf_hashes_sensitive():
    value = material()
    leaves = []

    def walk(target, prefix):
        for key, item in target.items():
            path = prefix + [key]
            if isinstance(item, dict):
                walk(item, path)
            else:
                leaves.append(path)

    walk(value, [])
    for path in leaves:
        changed = copy.deepcopy(value)
        target = changed
        for key in path[:-1]:
            target = target[key]
        old = target[path[-1]]
        target[path[-1]] = not old if type(old) is bool else old + 1 if type(old) is int else old + "X"
        raw = json.dumps(changed, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        assert hashlib.sha256(raw).hexdigest() != GOLDEN
    assert len(leaves) == 35
