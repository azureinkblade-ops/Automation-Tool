"""Shape-only check for synthetic Kilo dummy requests; no gateway authority."""

from tools.ea4e92cp_kilo_request_shape import RequestShapeDenied, summarize_request_shape


EXPECTED_FIELDS = {
    "model": "string",
    "messages": "array",
    "stream": "boolean",
    "stream_options": "object",
    "tools": "array",
    "tool_choice": "string",
    "max_tokens": "number",
}


class InertRequestDenied(ValueError):
    pass


def inspect_inert_kilo_request(raw: bytes) -> dict:
    """Match the 92CR dummy shape without exposing content or granting a send."""
    try:
        shape = summarize_request_shape(raw, expected_model="ea4e-inert")
    except RequestShapeDenied as exc:
        raise InertRequestDenied("dummy request shape denied") from exc
    if (shape["field_types"] != EXPECTED_FIELDS
            or shape["unknown_field_count"] != 0
            or shape["message_unknown_field_count"] != 0
            or shape["message_count"] != 2
            or shape["role_counts"]["system"] != 1
            or shape["role_counts"]["user"] != 1
            or sum(shape["role_counts"].values()) != 2
            or shape["content_kind_counts"]["string"] != 1
            or shape["content_kind_counts"]["array"] != 1
            or sum(shape["content_kind_counts"].values()) != 2
            or not shape["stream_true"]):
        raise InertRequestDenied("dummy request shape denied")
    return {
        "decision": "SHAPE_MATCH_ONLY",
        "body_bytes": shape["body_bytes"],
        "body_sha256": shape["body_sha256"],
        "forward_authorized": False,
    }
