import hashlib
from io import BytesIO

import pytest

from tools.ea4e92p_static_binary_inspection import (
    MARKERS, StaticInspectionDenied, inspect_stream,
)


def inspect(raw, **kwargs):
    return inspect_stream(BytesIO(raw), expected_sha256=hashlib.sha256(raw).hexdigest(),
                          **kwargs)


@pytest.mark.parametrize("chunk", [1, 7, 32, 1024])
def test_chunk_boundaries_first_occurrence_and_order(chunk):
    raw = b"xx" + b"|".join(MARKERS) + b"|" + MARKERS[0]
    receipt = inspect(raw, chunk_bytes=chunk)
    assert receipt.byte_count == len(raw)
    assert receipt.binary_sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.marker_offsets == tuple((m.decode("ascii"), raw.find(m)) for m in MARKERS)


def test_absent_markers_and_empty_stream():
    for raw in (b"", b"no SDK implementation here"):
        assert all(offset is None for _, offset in inspect(raw).marker_offsets)


def test_exact_limit_and_over_limit():
    assert inspect(b"123", max_bytes=3).byte_count == 3
    with pytest.raises(StaticInspectionDenied, match="exceeds"):
        inspect(b"1234", max_bytes=3)


@pytest.mark.parametrize("kwargs", [{"chunk_bytes": True}, {"chunk_bytes": 0},
    {"chunk_bytes": 1_048_577}, {"max_bytes": False}, {"max_bytes": 0},
    {"max_bytes": 200_000_001}])
def test_invalid_bounds(kwargs):
    with pytest.raises(StaticInspectionDenied):
        inspect(b"", **kwargs)


@pytest.mark.parametrize("expected", [None, "a" * 63, "A" * 64, "a" * 64])
def test_bad_or_mismatched_expected_identity(expected):
    with pytest.raises(StaticInspectionDenied):
        inspect_stream(BytesIO(b"fixture"), expected_sha256=expected)


def test_nonbyte_stream_and_oversized_read_response():
    class BadStream:
        def __init__(self, response):
            self.response = response

        def read(self, requested):
            return self.response

    for response in (None, "text", b"oversized"):
        with pytest.raises(StaticInspectionDenied):
            inspect_stream(BadStream(response), expected_sha256="a" * 64, chunk_bytes=1)


def test_read_error_propagates_without_receipt():
    class FailedStream:
        def read(self, requested):
            raise OSError("fixture read failure")

    with pytest.raises(OSError):
        inspect_stream(FailedStream(), expected_sha256="a" * 64)
