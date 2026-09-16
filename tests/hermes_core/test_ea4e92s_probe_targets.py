"""Value-only target-fixture tests; no socket or filesystem action occurs."""

from dataclasses import replace
from pathlib import Path

import pytest

from tools.ea4e92s_probe_admission import (
    ArtifactIdentity,
    DirectoryIdentity,
    ProbeAdmissionEvidence,
)
from tools import ea4e92s_probe_targets as subject
from tools.ea4e92s_profile_preflight import ProfileSnapshot


def directory(path, serial, start):
    return DirectoryIdentity(path, serial, bytes(range(start, start + 16)), False)


def artifact(path, marker):
    return ArtifactIdentity(path, 7, marker * 64)


def network(probe_id, host, port, marker):
    return subject.NetworkFixture(
        probe_id=probe_id,
        host=host,
        port=port,
        address_family="AF_INET6" if ":" in host else "AF_INET",
        listener_id=f"ea4e92s-listener-{marker * 8}",
        listener_nonce_sha256=marker * 64,
        harness_owned=True,
        accepted_connection_budget=0,
    )


def contract(**changes):
    request_id = "ea4e92s-request-0001"
    harness = directory(r"C:\EA4E92S", 7, 0)
    request = directory(rf"C:\EA4E92S\{request_id}", 7, 16)
    profile = ProfileSnapshot(
        "ea4e92s-profile", b"\x01" * 12, r"C:\Profiles\ea4e92s", 8,
        bytes(range(32, 48)), False)
    forbidden_root = harness
    allowed_root = request
    base = subject.ProbeTargetContract(
        request_id=request_id,
        request_root=request,
        profile=profile,
        harness_root=harness,
        loopback=network("NQ-04", "127.0.0.1", 53192, "a"),
        non_loopback=network("NQ-05", "192.168.50.10", 53193, "b"),
        forbidden_file=subject.FileFixture(
            "NQ-06", artifact(r"C:\EA4E92S\forbidden.bin", "c"),
            forbidden_root, True, False),
        allowed_file=subject.FileFixture(
            "NQ-07", artifact(
                rf"C:\EA4E92S\{request_id}\allowed.bin", "d"),
            allowed_root, True, True),
    )
    return replace(base, **changes)


def admission_evidence(reviewed, probe_id, config_hash):
    return ProbeAdmissionEvidence(
        request_id=reviewed.request_id,
        probe_id=probe_id,
        runtime_sha256="1" * 64,
        bootstrap_sha256="2" * 64,
        request_sha256="3" * 64,
        probe_config_sha256=config_hash,
        profile_name=reviewed.profile.profile_name,
        appcontainer_sid=reviewed.profile.sid,
        request_root_volume_serial=reviewed.request_root.volume_serial,
        request_root_file_id=reviewed.request_root.file_id,
        wall_clock_ms=10_000,
        process_memory_bytes=256 * 1024 * 1024,
        stdout_bytes=4 * 1024 * 1024,
        stderr_bytes=64 * 1024,
        active_process_limit=1,
        descendant_limit=0,
    )


def admissions(reviewed):
    return tuple(
        admission_evidence(reviewed, probe_id, config_hash)
        for probe_id, config_hash in subject._expected_admission_hashes(reviewed)
    )


def validate(reviewed=None, candidate=None, evidence=None):
    reviewed = reviewed or contract()
    evidence = admissions(reviewed) if evidence is None else evidence
    return subject.validate_probe_targets(
        reviewed, candidate or reviewed, admissions=evidence)


def test_exact_target_contract_returns_zero_success_budgets():
    evidence = validate()
    assert evidence.request_id == "ea4e92s-request-0001"
    assert len(evidence.target_contract_sha256) == 64
    assert evidence.loopback_listener_id == "ea4e92s-listener-aaaaaaaa"
    assert evidence.non_loopback_listener_id == "ea4e92s-listener-bbbbbbbb"
    assert tuple(item[0] for item in evidence.admission_config_hashes) == (
        "NQ-04", "NQ-05", "NQ-06", "NQ-07")
    assert evidence.accepted_connection_budget == 0
    assert evidence.filesystem_escape_success_budget == 0


@pytest.mark.parametrize("field,value", [
    ("request_id", "bad"),
    ("profile", ProfileSnapshot(
        "ea4e92s-profile", b"\x01" * 12, "relative", 8,
        bytes(range(32, 48)), False)),
    ("request_root", directory(r"C:\Other\request", 7, 16)),
    ("harness_root", directory(r"C:\EA4E92S\ea4e92s-request-0001\nested", 7, 32)),
])
def test_malformed_or_misplaced_roots_denied(field, value):
    with pytest.raises(subject.ProbeTargetDenied):
        validate(contract(**{field: value}))


@pytest.mark.parametrize("fixture", [
    network("NQ-04", "192.168.50.10", 53192, "a"),
    network("NQ-04", "localhost", 53192, "a"),
    replace(network("NQ-04", "127.0.0.1", 53192, "a"), address_family="AF_INET6"),
    replace(network("NQ-04", "127.0.0.1", 80, "a"), port=80),
    replace(network("NQ-04", "127.0.0.1", 53192, "a"), harness_owned=False),
    replace(network("NQ-04", "127.0.0.1", 53192, "a"), accepted_connection_budget=1),
])
def test_invalid_loopback_fixture_denied(fixture):
    with pytest.raises(subject.ProbeTargetDenied):
        validate(contract(loopback=fixture))


@pytest.mark.parametrize("host", [
    "127.0.0.1", "0.0.0.0", "8.8.8.8", "192.0.2.1", "ff02::1",
])
def test_non_loopback_target_must_be_private_literal(host):
    fixture = network("NQ-05", host, 53193, "b")
    with pytest.raises(subject.ProbeTargetDenied):
        validate(contract(non_loopback=fixture))


@pytest.mark.parametrize("field", ["port", "listener_id", "listener_nonce_sha256"])
def test_network_fixture_identity_must_be_distinct(field):
    reviewed = contract()
    value = getattr(reviewed.loopback, field)
    changed = replace(reviewed.non_loopback, **{field: value})
    with pytest.raises(subject.ProbeTargetDenied, match="distinct"):
        validate(replace(reviewed, non_loopback=changed))


@pytest.mark.parametrize("field,value", [
    ("probe_id", "NQ-07"),
    ("harness_owned", False),
    ("expected_readable", True),
])
def test_forbidden_fixture_contract_is_exact(field, value):
    reviewed = contract()
    changed = replace(reviewed.forbidden_file, **{field: value})
    with pytest.raises(subject.ProbeTargetDenied):
        validate(replace(reviewed, forbidden_file=changed))


@pytest.mark.parametrize("field,value", [
    ("probe_id", "NQ-06"),
    ("harness_owned", False),
    ("expected_readable", False),
])
def test_allowed_fixture_contract_is_exact(field, value):
    reviewed = contract()
    changed = replace(reviewed.allowed_file, **{field: value})
    with pytest.raises(subject.ProbeTargetDenied):
        validate(replace(reviewed, allowed_file=changed))


def test_allowed_fixture_must_be_inside_exact_request_root():
    reviewed = contract()
    changed = replace(
        reviewed.allowed_file,
        artifact=artifact(r"C:\EA4E92S\outside.bin", "d"))
    with pytest.raises(subject.ProbeTargetDenied, match="exact request root|inside"):
        validate(replace(reviewed, allowed_file=changed))


@pytest.mark.parametrize("path", [
    r"C:\EA4E92S\ea4e92s-request-0001\forbidden.bin",
    r"C:\Profiles\ea4e92s\forbidden.bin",
])
def test_forbidden_fixture_must_be_outside_allowed_roots(path):
    reviewed = contract()
    changed = replace(reviewed.forbidden_file, artifact=artifact(path, "c"))
    with pytest.raises(subject.ProbeTargetDenied):
        validate(replace(reviewed, forbidden_file=changed))


def test_reparse_fixture_root_denied():
    reviewed = contract()
    root = replace(reviewed.allowed_file.fixture_root, reparse=True)
    changed = replace(reviewed.allowed_file, fixture_root=root)
    with pytest.raises(subject.ProbeTargetDenied, match="reparse"):
        validate(replace(reviewed, allowed_file=changed))


@pytest.mark.parametrize("storage_path", [
    r"C:\EA4E92S\profile",
    r"C:\EA4E92S",
])
def test_harness_and_profile_roots_must_be_disjoint(storage_path):
    reviewed = contract()
    profile = replace(reviewed.profile, storage_path=storage_path)
    with pytest.raises(subject.ProbeTargetDenied, match="disjoint"):
        validate(replace(reviewed, profile=profile))


def test_candidate_drift_denied_before_evidence():
    reviewed = contract()
    candidate = replace(
        reviewed,
        allowed_file=replace(
            reviewed.allowed_file,
            artifact=replace(reviewed.allowed_file.artifact, sha256="e" * 64)))
    with pytest.raises(subject.ProbeTargetDenied, match="candidate"):
        validate(reviewed, candidate)


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "request", "profile", "root_serial", "root_file", "config",
])
def test_admission_evidence_must_exactly_bind_targets(mutation):
    reviewed = contract()
    evidence = list(admissions(reviewed))
    if mutation == "missing":
        evidence.pop()
    elif mutation == "duplicate":
        evidence[-1] = evidence[0]
    elif mutation == "request":
        evidence[0] = replace(evidence[0], request_id="ea4e92s-request-other")
    elif mutation == "profile":
        evidence[0] = replace(evidence[0], profile_name="other-profile")
    elif mutation == "root_serial":
        evidence[0] = replace(evidence[0], request_root_volume_serial=999)
    elif mutation == "root_file":
        evidence[0] = replace(evidence[0], request_root_file_id=b"x" * 16)
    elif mutation == "config":
        evidence[0] = replace(evidence[0], probe_config_sha256="f" * 64)
    with pytest.raises(subject.ProbeTargetDenied, match="admission"):
        validate(reviewed, evidence=tuple(evidence))


def test_non_tuple_or_forged_admission_evidence_denied():
    reviewed = contract()
    with pytest.raises(subject.ProbeTargetDenied, match="admission"):
        validate(reviewed, evidence=list(admissions(reviewed)))
    with pytest.raises(subject.ProbeTargetDenied, match="admission"):
        validate(reviewed, evidence=(object(),) * 4)


class ForgedContract(subject.ProbeTargetContract):
    pass


def test_subclassed_contract_denied():
    reviewed = contract()
    forged = ForgedContract(**reviewed.__dict__)
    with pytest.raises(subject.ProbeTargetDenied, match="exact"):
        validate(reviewed, forged)


def test_source_has_no_runtime_capability():
    text = Path(subject.__file__).read_text(encoding="utf-8")
    for forbidden in (
            "subprocess", "Popen", "WinDLL", "CreateProcessW", "ResumeThread",
            "socket", "requests", "urllib", "open("):
        assert forbidden not in text
