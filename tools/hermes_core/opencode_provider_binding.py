"""Pure versioned OpenCode provider-binding contract; no runtime authority."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import PureWindowsPath
import re
from urllib.parse import urlsplit

from tools.hermes_core.hashing import canonical_json


class ProviderBindingError(ValueError):
    pass


_FIELDS = {
    "": ("schema_id", "artifact_version", "receiver_id", "receiver_class",
         "transport_contract_id", "runtime", "selection", "provider", "deployment"),
    "runtime": ("executable_path", "executable_sha256", "executable_version"),
    "selection": ("provider_id", "model_id", "agent_id", "mechanism", "config_path",
                  "config_sha256", "ambient_config_allowed", "project_config_allowed",
                  "task_model_override_allowed", "task_provider_override_allowed",
                  "task_agent_override_allowed", "session_inheritance_allowed"),
    "provider": ("package_id", "receiver_base_url", "gate_route", "upstream_base_url",
                 "credential_policy", "stream_allowed", "redirect_limit",
                 "network_retry_limit", "max_provider_calls", "max_request_bytes",
                 "max_response_bytes"),
    "deployment": ("gate_contract_sha256", "egress_policy_sha256",
                   "cpu_policy_sha256", "cleanup_contract_sha256"),
}
_FIXED = {
    "schema_id": "hermes.opencode-provider-binding/v1", "artifact_version": 1,
    "receiver_id": "opencode-cli-agent", "receiver_class": "OPENCODE",
    "selection.provider_id": "ollama", "selection.agent_id": "hermes-ea4e-opencode-receiver",
    "selection.mechanism": "ISOLATED_CONFIG_AGENT_MODEL",
    "provider.package_id": "@ai-sdk/openai-compatible",
    "provider.gate_route": "/v1/chat/completions",
    "provider.credential_policy": "NO_PROVIDER_API_KEY", "provider.stream_allowed": False,
    "provider.redirect_limit": 0, "provider.network_retry_limit": 0,
    "provider.max_provider_calls": 1,
}
for _key in _FIELDS["selection"]:
    if _key.endswith("_allowed"):
        _FIXED["selection." + _key] = False


def _deny(reason):
    raise ProviderBindingError(reason)


def _text(value):
    if type(value) is not str or not value or not value.isascii() or value.strip() != value:
        _deny("invalid ASCII string")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        _deny("control character")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _deny("invalid SHA-256")


def _path(value):
    path = PureWindowsPath(value)
    if re.match(r"^[A-Za-z]:\\", value) is None or not path.is_absolute() or "/" in value:
        _deny("invalid absolute Windows path")
    components = value[3:].split("\\")
    if any(not part or part in (".", "..") or part.endswith((" ", "."))
           or any(char in '<>:"/|?*' for char in part) for part in components):
        _deny("invalid path component")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{i}" for prefix in ("COM", "LPT")
                                                    for i in range(1, 10)}
    if any(part.split(".")[0].upper() in reserved for part in components):
        _deny("device path forbidden")


def _url(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _deny("invalid endpoint")
    if port is None or not 1 <= port <= 65535 or value != f"http://127.0.0.1:{port}/v1":
        _deny("endpoint not canonical loopback")
    return port


def _validate(material, prefix=""):
    if type(material) is not dict or set(material) != set(_FIELDS[prefix]):
        _deny("field set mismatch")
    for key, value in material.items():
        name = prefix + "." + key if prefix else key
        if name in _FIELDS:
            _validate(value, name)
        elif name in _FIXED:
            fixed = _FIXED[name]
            if type(value) is not type(fixed) or value != fixed:
                _deny("frozen policy mismatch")
        elif key in ("max_request_bytes", "max_response_bytes"):
            if type(value) is not int or not 1 <= value <= 65536:
                _deny("invalid byte limit")
        else:
            _text(value)
            if key.endswith("_sha256") or key == "transport_contract_id":
                _hash(value)
            elif key.endswith("_path"):
                _path(value)
            elif key.endswith("_base_url"):
                _url(value)
    if not prefix and _url(material["provider"]["receiver_base_url"]) == _url(
            material["provider"]["upstream_base_url"]):
        _deny("gate and upstream must differ")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _deny("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    _deny("nonfinite JSON constant")


@dataclass(frozen=True)
class ProviderBinding:
    canonical_bytes: bytes
    model_binding_id: str


def build_provider_binding(material):
    """Validate a caller-owned dictionary; return an immutable canonical snapshot."""
    try:
        _validate(material)
        raw = canonical_json(material).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProviderBindingError("binding material denied") from exc
    return ProviderBinding(raw, hashlib.sha256(raw).hexdigest())


def parse_provider_binding(raw):
    """Parse exact UTF-8 JSON bytes, rejecting duplicates and unqualified fields."""
    if type(raw) is not bytes:
        _deny("byte JSON required")
    try:
        material = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                              parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProviderBindingError("binding JSON denied") from exc
    return build_provider_binding(material)


def verify_supplied_binding_evidence(material, *, expected_binding_id,
                                     runtime_bytes, config_bytes, policy_bytes):
    """Check supplied snapshots only; does not discover files or enforce policies."""
    binding = build_provider_binding(material)
    _hash(expected_binding_id)
    if binding.model_binding_id != expected_binding_id:
        _deny("expected binding mismatch")
    snapshot = json.loads(binding.canonical_bytes)
    expected = snapshot["deployment"]
    if type(policy_bytes) is not dict or set(policy_bytes) != set(expected):
        _deny("policy evidence missing or extra")
    checks = [(runtime_bytes, snapshot["runtime"]["executable_sha256"]),
              (config_bytes, snapshot["selection"]["config_sha256"])]
    checks.extend((policy_bytes[key], digest) for key, digest in expected.items())
    for raw, digest in checks:
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
            _deny("supplied snapshot hash mismatch")
    return binding
