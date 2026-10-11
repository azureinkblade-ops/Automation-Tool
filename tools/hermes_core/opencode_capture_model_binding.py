"""Canonical, non-live OpenCode capture model binding; no runtime authority."""

from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import urlsplit


SCHEMA_ID = "hermes.opencode-capture-model-binding/v1"
FIELDS = frozenset({
    "schema_id", "receiver_id", "provider_id", "model_id",
    "request_model_id", "provider_base_url", "route", "stream",
    "runtime_sha256", "config_sha256", "transport_id",
    "credential_policy_sha256", "egress_policy_sha256",
    "qualification_status",
})
HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
FIXED = {
    "schema_id": SCHEMA_ID,
    "receiver_id": "opencode-cli-agent",
    "route": "/v1/chat/completions",
    "stream": True,
    "qualification_status": "UNQUALIFIED_NONLIVE",
}


class CaptureModelBindingError(ValueError):
    pass


@dataclass(frozen=True)
class CaptureModelBinding:
    canonical_bytes: bytes
    binding_id: str
    provider_id: str
    model_id: str
    request_model_id: str
    runtime_sha256: str
    config_sha256: str
    transport_id: str


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureModelBindingError("duplicate binding field")
        result[key] = value
    return result


def _deny_constant(_value):
    raise CaptureModelBindingError("nonfinite binding value")


def _validate(material):
    if type(material) is not dict or set(material) != FIELDS:
        raise CaptureModelBindingError("binding field set mismatch")
    for key, expected in FIXED.items():
        if type(material[key]) is not type(expected) or material[key] != expected:
            raise CaptureModelBindingError("frozen binding policy mismatch")
    for key in ("provider_id", "model_id", "request_model_id"):
        value = material[key]
        if (type(value) is not str or not value.isascii() or not 1 <= len(value) <= 256
                or value.strip() != value or any(ord(c) < 33 or ord(c) == 127 for c in value)):
            raise CaptureModelBindingError("invalid model identity")
    for key in ("runtime_sha256", "config_sha256", "transport_id",
                "credential_policy_sha256", "egress_policy_sha256"):
        if type(material[key]) is not str or HASH.fullmatch(material[key]) is None:
            raise CaptureModelBindingError("invalid binding digest")
    url = material["provider_base_url"]
    if type(url) is not str or not url.isascii():
        raise CaptureModelBindingError("invalid provider base URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise CaptureModelBindingError("invalid provider base URL") from exc
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment
            or parts.path.endswith("/") or port == 0 or parts.geturl() != url
            or "\\" in url or "@" in url or "?" in url or "#" in url
            or any(ord(c) < 33 or ord(c) == 127 for c in url)):
        raise CaptureModelBindingError("provider base URL must be a clean HTTPS endpoint")


def build_binding(material):
    _validate(material)
    raw = json.dumps(material, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    return CaptureModelBinding(
        raw, hashlib.sha256(raw).hexdigest(), material["provider_id"],
        material["model_id"], material["request_model_id"],
        material["runtime_sha256"], material["config_sha256"],
        material["transport_id"],
    )


def parse_binding(raw):
    if type(raw) is not bytes:
        raise CaptureModelBindingError("binding must be bytes")
    try:
        material = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                              parse_constant=_deny_constant)
        binding = build_binding(material)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CaptureModelBindingError("binding denied") from exc
    if raw != binding.canonical_bytes:
        raise CaptureModelBindingError("binding bytes are not canonical")
    return binding
