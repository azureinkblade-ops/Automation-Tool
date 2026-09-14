"""Synthetic extraction fixtures only; these do not qualify parser execution."""

import hashlib

import pytest

from tools import ea4e92s_parser_source as subject


def pin_fixture(monkeypatch, bundle, region, offset=0):
    monkeypatch.setattr(subject, "BUNDLE_BYTES", len(bundle))
    monkeypatch.setattr(subject, "BUNDLE_SHA256", hashlib.sha256(bundle).hexdigest())
    monkeypatch.setattr(subject, "REGION_OFFSET", offset)
    monkeypatch.setattr(subject, "REGION_BYTES", len(region))
    monkeypatch.setattr(subject, "REGION_SHA256", hashlib.sha256(region).hexdigest())


@pytest.fixture
def sample(monkeypatch):
    region = subject.START + b"\nvar inert = 1;\n"
    bundle = region + subject.END
    pin_fixture(monkeypatch, bundle, region)
    return bundle, region


def test_exact_source_bytes(sample):
    bundle, region = sample
    assert subject.extract_parser_source(bundle) == region


@pytest.mark.parametrize("value", [None, "text", bytearray(b"text"), memoryview(b"text")])
def test_nonbytes_denied(value):
    with pytest.raises(ValueError, match="must be bytes"):
        subject.extract_parser_source(value)


def test_length_drift(sample):
    with pytest.raises(ValueError, match="length mismatch"):
        subject.extract_parser_source(sample[0] + b"x")


def test_parent_hash_drift(sample):
    with pytest.raises(ValueError, match="bundle hash mismatch"):
        subject.extract_parser_source(sample[0].replace(b"inert", b"other"))


@pytest.mark.parametrize("marker", [subject.START, subject.END])
def test_duplicate_boundaries(monkeypatch, sample, marker):
    bundle, region = sample
    bundle += marker
    pin_fixture(monkeypatch, bundle, region)
    with pytest.raises(ValueError, match="ambiguous"):
        subject.extract_parser_source(bundle)


def test_region_offset_drift(monkeypatch, sample):
    monkeypatch.setattr(subject, "REGION_OFFSET", 1)
    with pytest.raises(ValueError, match="region mismatch"):
        subject.extract_parser_source(sample[0])


def test_region_hash_drift(monkeypatch, sample):
    monkeypatch.setattr(subject, "REGION_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="region hash mismatch"):
        subject.extract_parser_source(sample[0])


@pytest.mark.parametrize("marker", [subject.START, subject.END])
def test_missing_boundaries(monkeypatch, sample, marker):
    bundle, region = sample
    bundle = bundle.replace(marker, b"x" * len(marker))
    pin_fixture(monkeypatch, bundle, region)
    with pytest.raises(ValueError, match="ambiguous"):
        subject.extract_parser_source(bundle)


def test_reversed_boundaries(monkeypatch):
    bundle = subject.END + subject.START
    pin_fixture(monkeypatch, bundle, subject.START, offset=len(subject.END))
    with pytest.raises(ValueError, match="region mismatch"):
        subject.extract_parser_source(bundle)


def test_region_length_drift(monkeypatch, sample):
    monkeypatch.setattr(subject, "REGION_BYTES", 1)
    with pytest.raises(ValueError, match="region mismatch"):
        subject.extract_parser_source(sample[0])


def test_invalid_utf8(monkeypatch):
    region = subject.START + b"\xff"
    bundle = region + subject.END
    pin_fixture(monkeypatch, bundle, region)
    with pytest.raises(UnicodeDecodeError):
        subject.extract_parser_source(bundle)
