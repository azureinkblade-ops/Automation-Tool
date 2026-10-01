"""Fake-only SSE inspection; no listener, receiver, or provider transport."""

import hashlib

import pytest

from tools.hermes_core.opencode_sse_response import (
    MAX_CHUNKS, MAX_DURATION_MS, MAX_EVENTS, MAX_LINE_BYTES, MAX_RESPONSE_BYTES,
    SseResponseDenied, inspect_sse_response,
)


EVENT = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
DONE = b"data: [DONE]\n\n"


def inspect(raw=None, **changes):
    args = dict(status=200, content_type="text/event-stream",
                content_encoding=None, chunks=[(EVENT + DONE if raw is None else raw, 0)])
    args.update(changes)
    return inspect_sse_response(**args)


def test_valid_raw_bytes_and_chunk_splits():
    raw = EVENT.replace(b"\n", b"\r\n") + DONE.replace(b"\n", b"\r\n")
    chunks = [(raw[index:index + 1], index) for index in range(len(raw))]
    result = inspect(chunks=chunks)
    assert result.raw_bytes == raw
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.event_count == 2
    assert result.chunk_count == len(raw)


def test_utf8_split_across_chunks():
    raw = 'data: {"content":"caf\u00e9"}\n\ndata: [DONE]\n\n'.encode("utf-8")
    split = raw.index(b"\xc3") + 1
    assert inspect(chunks=[(raw[:split], 1), (raw[split:], 2)]).raw_bytes == raw


@pytest.mark.parametrize("changes", [
    {"status": 503}, {"content_type": "application/json"},
    {"content_type": "text/event-stream; charset=utf-8"},
    {"content_encoding": "gzip"},
])
def test_metadata_denied(changes):
    with pytest.raises(SseResponseDenied):
        inspect(**changes)


@pytest.mark.parametrize("raw", [
    b"", EVENT, DONE + EVENT, DONE + DONE,
    EVENT + b"data: [DONE]\n", EVENT + b"data: [DONE]\r",
    b"event: error\n" + EVENT + DONE,
    b"data: {\"error\":\"bad\"}\n\n" + DONE,
    b"data: {\"a\":1,\"a\":2}\n\n" + DONE,
    b"data: {\"a\":NaN}\n\n" + DONE,
    b"data: [1]\n\n" + DONE,
    b"data: \xff\n\n" + DONE,
    b"data: {}\ndata: {}\n\n" + DONE,
    b"\n" + DONE,
    DONE + b"x", DONE + b"\n" + EVENT,
])
def test_invalid_framing_and_payload_denied(raw):
    with pytest.raises(SseResponseDenied):
        inspect(raw)


def test_line_limit_inclusive_and_exclusive():
    prefix = b"data: "
    payload = b'{"x":"' + b"a" * (MAX_LINE_BYTES - len(prefix) - 8) + b'"}'
    valid = prefix + payload + b"\n\n" + DONE
    assert len(valid.split(b"\n", 1)[0]) == MAX_LINE_BYTES
    assert inspect(valid).event_count == 2
    with pytest.raises(SseResponseDenied):
        inspect(prefix + payload[:-2] + b'a"}\n\n' + DONE)


def test_response_byte_limit_and_event_limit():
    valid = b"data: " + b'{"x":"' + b"a" * 4000 + b'"}\n\n'
    raw = valid * 15 + DONE
    assert len(raw) < MAX_RESPONSE_BYTES
    assert inspect(raw).event_count == 16
    with pytest.raises(SseResponseDenied):
        inspect(chunks=[(raw, 0), (b" " * (MAX_RESPONSE_BYTES - len(raw) + 1), 1)])
    assert len(inspect(DONE + b" " * (MAX_RESPONSE_BYTES - len(DONE))).raw_bytes) == MAX_RESPONSE_BYTES
    assert inspect(b"data: {}\n\n" * (MAX_EVENTS - 1) + DONE).event_count == MAX_EVENTS
    with pytest.raises(SseResponseDenied):
        inspect(b"data: {}\n\n" * MAX_EVENTS + DONE)


def test_deadline_and_monotonic_clock():
    assert inspect(chunks=[(EVENT, 0), (DONE, MAX_DURATION_MS)]).event_count == 2
    for chunks in ([(EVENT, 0), (DONE, MAX_DURATION_MS + 1)],
                   [(EVENT, 2), (DONE, 1)], [(EVENT, -1), (DONE, 0)],
                   [(EVENT, True), (DONE, 0)]):
        with pytest.raises(SseResponseDenied):
            inspect(chunks=chunks)


def test_chunk_type_and_truncation_denied():
    for chunks in ([("not bytes", 0)], [(EVENT, 0), (b"data: [DONE]", 1)],
                   [(EVENT, 0), (DONE, 1), (b"bad", 2)]):
        with pytest.raises(SseResponseDenied):
            inspect(chunks=chunks)


def test_empty_chunk_flood_denied():
    assert inspect(chunks=[(b"", 0)] * (MAX_CHUNKS - 1) + [(DONE, 0)]).event_count == 1
    with pytest.raises(SseResponseDenied):
        inspect(chunks=[(b"", 0)] * MAX_CHUNKS + [(DONE, 0)])
