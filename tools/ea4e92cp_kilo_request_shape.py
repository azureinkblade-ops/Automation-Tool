"""Pure, bounded request-shape summary for a dummy-only Kilo provider probe."""

import hashlib
import json


MAX_BODY_BYTES = 65536
FIELDS = ("model", "messages", "stream", "stream_options", "tools",
          "tool_choice", "temperature", "max_tokens", "max_completion_tokens")
ROLES = ("system", "developer", "user", "assistant", "tool")


class RequestShapeDenied(ValueError):
    pass


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise RequestShapeDenied("duplicate JSON key")
        value[key] = item
    return value


def _constant(_value):
    raise RequestShapeDenied("nonfinite JSON constant")


def _kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    return "object"


def summarize_request_shape(raw: bytes, *, expected_model: str) -> dict:
    """Return only fixed vocabulary, counts, and a digest; never echo values."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BODY_BYTES:
        raise RequestShapeDenied("invalid bounded body")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                             parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RequestShapeDenied("invalid JSON body") from exc
    if type(payload) is not dict or payload.get("model") != expected_model:
        raise RequestShapeDenied("unexpected model or body")
    messages = payload.get("messages")
    if type(messages) is not list or len(messages) > 128:
        raise RequestShapeDenied("invalid message list")
    roles = {role: 0 for role in ROLES}
    roles["other"] = 0
    content_kinds = {kind: 0 for kind in ("null", "boolean", "string", "number", "array", "object")}
    message_unknown_fields = 0
    for message in messages:
        if type(message) is not dict:
            raise RequestShapeDenied("invalid message")
        role = message.get("role")
        roles[role if type(role) is str and role in ROLES else "other"] += 1
        content_kinds[_kind(message.get("content"))] += 1
        message_unknown_fields += len(set(message) - {"role", "content", "name", "tool_calls", "tool_call_id"})
    return {
        "body_bytes": len(raw),
        "body_sha256": hashlib.sha256(raw).hexdigest(),
        "field_types": {field: _kind(payload[field]) for field in FIELDS if field in payload},
        "unknown_field_count": len(set(payload) - set(FIELDS)),
        "message_count": len(messages),
        "message_unknown_field_count": message_unknown_fields,
        "role_counts": roles,
        "content_kind_counts": content_kinds,
        "stream_true": payload.get("stream") is True,
        "model_matches_expected": True,
    }
