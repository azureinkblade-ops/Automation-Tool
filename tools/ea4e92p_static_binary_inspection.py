"""Read-only qualification inspection; marker receipts are not SDK provenance."""

from dataclasses import dataclass
import hashlib
import re


MARKERS = (b"B:/~BUN/root", b"@ai-sdk/openai-compatible",
           b"openai-compatible-chat-language-model", b"stream_options")
MAX_BYTES = 200_000_000
CHUNK_BYTES = 1_048_576


class StaticInspectionDenied(ValueError):
    pass


@dataclass(frozen=True)
class StaticInspectionReceipt:
    binary_sha256: str
    byte_count: int
    marker_offsets: tuple


def inspect_stream(stream, *, expected_sha256, chunk_bytes=CHUNK_BYTES,
                   max_bytes=MAX_BYTES):
    """Hash one bounded binary stream; retain only first fixed-marker offsets.

    The caller supplies a fresh stream at byte zero and owns its lifetime.
    No source extraction, file discovery, process launch or authority is performed.
    """
    if type(expected_sha256) is not str or re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256) is None:
        raise StaticInspectionDenied("invalid expected SHA-256")
    if (type(chunk_bytes) is not int or not 1 <= chunk_bytes <= CHUNK_BYTES
            or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES):
        raise StaticInspectionDenied("invalid inspection bounds")
    digest = hashlib.sha256()
    offsets = {marker: None for marker in MARKERS}
    overlap = max(map(len, MARKERS)) - 1
    tail = b""
    count = 0
    while True:
        requested = min(chunk_bytes, max_bytes - count + 1)
        raw = stream.read(requested)
        if type(raw) is not bytes or len(raw) > requested:
            raise StaticInspectionDenied("invalid binary stream response")
        if not raw:
            break
        if count + len(raw) > max_bytes:
            raise StaticInspectionDenied("binary exceeds inspection bound")
        digest.update(raw)
        window = tail + raw
        for marker in MARKERS:
            if offsets[marker] is None:
                found = window.find(marker)
                if found >= 0:
                    offsets[marker] = count - len(tail) + found
        count += len(raw)
        tail = window[-overlap:]
    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise StaticInspectionDenied("binary identity mismatch")
    return StaticInspectionReceipt(actual, count, tuple(
        (marker.decode("ascii"), offsets[marker]) for marker in MARKERS))
