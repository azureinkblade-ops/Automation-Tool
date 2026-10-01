"""Pure, bounded SSE response inspection for non-live OpenCode qualification."""

from dataclasses import dataclass
import hashlib
import json


MAX_RESPONSE_BYTES = 65536
MAX_EVENTS = 128
MAX_LINE_BYTES = 4096
MAX_DURATION_MS = 30000
MAX_CHUNKS = 1024


class SseResponseDenied(ValueError):
    pass


@dataclass(frozen=True)
class SseResponseEvidence:
    raw_bytes: bytes
    sha256: str
    event_count: int
    chunk_count: int


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SseResponseDenied("duplicate JSON key")
        value[key] = item
    return value


def _deny_constant(_value):
    raise SseResponseDenied("nonfinite JSON constant")


def inspect_sse_response(*, status, content_type, content_encoding, chunks):
    """Inspect injected ``(bytes, elapsed_ms)`` chunks; never fetch or forward."""
    if (type(status) is not int or status != 200
            or content_type != "text/event-stream" or content_encoding is not None):
        raise SseResponseDenied("response metadata denied")

    raw = bytearray()
    line = bytearray()
    event_count = 0
    chunk_count = 0
    previous_elapsed = -1
    terminal = False
    event_data = None

    for chunk, elapsed in chunks:
        if type(chunk) is not bytes or type(elapsed) is not int:
            raise SseResponseDenied("invalid chunk")
        if elapsed < previous_elapsed or elapsed < 0 or elapsed > MAX_DURATION_MS:
            raise SseResponseDenied("response deadline denied")
        previous_elapsed = elapsed
        chunk_count += 1
        if chunk_count > MAX_CHUNKS:
            raise SseResponseDenied("too many chunks")
        if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
            raise SseResponseDenied("response too large")
        raw.extend(chunk)
        for byte in chunk:
            if terminal:
                if byte not in b" \t\r\n":
                    raise SseResponseDenied("trailing response bytes")
                continue
            if byte != 10:
                line.append(byte)
                if len(line) > MAX_LINE_BYTES + 1:
                    raise SseResponseDenied("event line too long")
                continue
            current = bytes(line)
            line.clear()
            if current.endswith(b"\r"):
                current = current[:-1]
            if len(current) > MAX_LINE_BYTES:
                raise SseResponseDenied("event line too long")
            if current:
                if not current.startswith(b"data: "):
                    raise SseResponseDenied("unsupported SSE field")
                if event_data is not None:
                    raise SseResponseDenied("multiple data lines")
                event_data = current[6:]
                continue
            if event_data is None:
                raise SseResponseDenied("empty event")
            event_count += 1
            if event_count > MAX_EVENTS:
                raise SseResponseDenied("too many events")
            if event_data == b"[DONE]":
                terminal = True
            else:
                try:
                    value = json.loads(event_data.decode("utf-8"),
                                       object_pairs_hook=_unique_object,
                                       parse_constant=_deny_constant)
                except (UnicodeError, ValueError, RecursionError) as exc:
                    raise SseResponseDenied("invalid event JSON") from exc
                if type(value) is not dict or value.get("error") is not None:
                    raise SseResponseDenied("event payload denied")
            event_data = None
    if not terminal or line or event_data is not None:
        raise SseResponseDenied("missing terminal event")
    response = bytes(raw)
    return SseResponseEvidence(response, hashlib.sha256(response).hexdigest(),
                               event_count, chunk_count)
