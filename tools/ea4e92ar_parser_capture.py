"""Validate untrusted fixture stdout offline; this is not launch evidence."""

import json


MAX_STDOUT_BYTES = 262144


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate fixture field")
        value[key] = item
    return value


def parse_fixture_stdout(raw, expected_argv):
    """Require one canonical record matching an independently admitted argv."""
    if (type(raw) is not bytes or not raw or len(raw) > MAX_STDOUT_BYTES
            or type(expected_argv) is not tuple or len(expected_argv) != 8
            or any(type(item) is not str for item in expected_argv)):
        raise ValueError("fixture capture input invalid")
    try:
        text = raw.decode("utf-8", errors="strict")
        record = json.loads(text, object_pairs_hook=_unique_object)
        canonical = json.dumps(
            record, ensure_ascii=False, separators=(",", ":"),
        ) + "\n"
        if text != canonical:
            raise ValueError("fixture record noncanonical")
    except (UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError) as error:
        raise ValueError("fixture record malformed") from error
    if (type(record) is not dict or set(record) != {"schemaVersion", "argv"}
            or type(record["schemaVersion"]) is not int
            or record["schemaVersion"] != 1
            or type(record["argv"]) is not list
            or any(type(item) is not str for item in record["argv"])
            or tuple(record["argv"]) != expected_argv):
        raise ValueError("fixture argv mismatch")
    return expected_argv
