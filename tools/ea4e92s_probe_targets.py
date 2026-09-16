"""Value-only target-fixture contract for EA-4E.92S containment probes."""

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import PureWindowsPath

from tools.ea4e92s_probe_admission import (
    ArtifactIdentity,
    DirectoryIdentity,
    ProbeAdmissionEvidence,
    SHA256_PATTERN,
)
from tools.ea4e92s_profile_preflight import ProfileSnapshot, canonical_local_path


LISTENER_ID_PATTERN = re.compile(r"ea4e92s-listener-[a-z0-9-]{8,48}")
REQUEST_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")
IPV4_PRIVATE = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
IPV6_LOCAL = ipaddress.ip_network("fc00::/7")


class ProbeTargetDenied(ValueError):
    """The candidate target set does not match the reviewed fixture contract."""


@dataclass(frozen=True)
class NetworkFixture:
    probe_id: str
    host: str
    port: int
    address_family: str
    listener_id: str
    listener_nonce_sha256: str
    harness_owned: bool
    accepted_connection_budget: int


@dataclass(frozen=True)
class FileFixture:
    probe_id: str
    artifact: ArtifactIdentity
    fixture_root: DirectoryIdentity
    harness_owned: bool
    expected_readable: bool


@dataclass(frozen=True)
class ProbeTargetContract:
    request_id: str
    request_root: DirectoryIdentity
    profile: ProfileSnapshot
    harness_root: DirectoryIdentity
    loopback: NetworkFixture
    non_loopback: NetworkFixture
    forbidden_file: FileFixture
    allowed_file: FileFixture


@dataclass(frozen=True)
class ProbeTargetEvidence:
    request_id: str
    target_contract_sha256: str
    loopback_listener_id: str
    non_loopback_listener_id: str
    forbidden_file_sha256: str
    allowed_file_sha256: str
    admission_config_hashes: tuple
    accepted_connection_budget: int
    filesystem_escape_success_budget: int


def _deny(message):
    raise ProbeTargetDenied(message)


def _path(value, label):
    if type(value) is not str:
        _deny(f"{label} path malformed")
    try:
        return PureWindowsPath(canonical_local_path(value))
    except ValueError as error:
        raise ProbeTargetDenied(f"{label} path must be absolute local path") from error


def _descendant(child, root):
    try:
        relative = child.relative_to(root)
    except ValueError:
        return False
    return bool(relative.parts)


def _directory(value, label):
    if type(value) is not DirectoryIdentity:
        _deny(f"exact {label} identity required")
    path = _path(value.path, label)
    if type(value.volume_serial) is not int or not 0 <= value.volume_serial < 1 << 64:
        _deny(f"{label} volume identity invalid")
    if type(value.file_id) is not bytes or len(value.file_id) != 16:
        _deny(f"{label} file identity invalid")
    if value.reparse is not False:
        _deny(f"{label} reparse path denied")
    return path


def _artifact(value, label):
    if type(value) is not ArtifactIdentity:
        _deny(f"exact {label} artifact identity required")
    path = _path(value.path, label)
    if type(value.size) is not int or not 0 < value.size <= 64 * 1024:
        _deny(f"{label} size invalid")
    if type(value.sha256) is not str or SHA256_PATTERN.fullmatch(value.sha256) is None:
        _deny(f"{label} sha256 invalid")
    return path


def _profile(value):
    if type(value) is not ProfileSnapshot:
        _deny("exact profile snapshot required")
    path = _path(value.storage_path, "profile storage")
    if type(value.profile_name) is not str or not value.profile_name:
        _deny("profile name malformed")
    if type(value.sid) is not bytes or not 8 <= len(value.sid) <= 68:
        _deny("profile SID malformed")
    if type(value.volume_serial) is not int or not 0 <= value.volume_serial < 1 << 64:
        _deny("profile volume identity invalid")
    if type(value.file_id) is not bytes or len(value.file_id) != 16:
        _deny("profile file identity invalid")
    if value.is_reparse_point is not False:
        _deny("profile reparse path denied")
    return path


def _network(value, probe_id, loopback):
    if type(value) is not NetworkFixture or value.probe_id != probe_id:
        _deny(f"exact {probe_id} network fixture required")
    if type(value.host) is not str:
        _deny("network host malformed")
    try:
        address = ipaddress.ip_address(value.host)
    except ValueError as error:
        raise ProbeTargetDenied("network host must be literal IP") from error
    expected_family = "AF_INET" if address.version == 4 else "AF_INET6"
    if value.address_family != expected_family:
        _deny("network address family mismatch")
    if loopback != address.is_loopback:
        _deny("network address class mismatch")
    if not loopback:
        local_only = (
            any(address in network for network in IPV4_PRIVATE)
            if address.version == 4 else address in IPV6_LOCAL
        )
        if not local_only:
            _deny("non-loopback target must be private harness address")
    if type(value.port) is not int or not 49152 <= value.port <= 65535:
        _deny("network port outside harness range")
    if (type(value.listener_id) is not str
            or LISTENER_ID_PATTERN.fullmatch(value.listener_id) is None):
        _deny("listener identity malformed")
    if (type(value.listener_nonce_sha256) is not str
            or SHA256_PATTERN.fullmatch(value.listener_nonce_sha256) is None):
        _deny("listener nonce identity malformed")
    if value.harness_owned is not True:
        _deny("listener must be harness owned")
    if value.accepted_connection_budget != 0:
        _deny("network success budget must be zero")


def _file(value, probe_id, expected_readable):
    if type(value) is not FileFixture or value.probe_id != probe_id:
        _deny(f"exact {probe_id} file fixture required")
    root = _directory(value.fixture_root, f"{probe_id} fixture root")
    artifact = _artifact(value.artifact, f"{probe_id} fixture")
    if not _descendant(artifact, root):
        _deny("file fixture must be inside its exact root")
    if value.harness_owned is not True:
        _deny("file fixture must be harness owned")
    if value.expected_readable is not expected_readable:
        _deny("file fixture readability differs from probe contract")
    return artifact, root


def _canonical_contract(value):
    def directory(item):
        return {
            "fileId": item.file_id.hex(),
            "path": item.path,
            "reparse": item.reparse,
            "volumeSerial": item.volume_serial,
        }

    def network(item):
        return {
            "acceptedConnectionBudget": item.accepted_connection_budget,
            "addressFamily": item.address_family,
            "harnessOwned": item.harness_owned,
            "host": item.host,
            "listenerId": item.listener_id,
            "listenerNonceSha256": item.listener_nonce_sha256,
            "port": item.port,
            "probeId": item.probe_id,
        }

    def file_fixture(item):
        return {
            "artifact": {
                "path": item.artifact.path,
                "sha256": item.artifact.sha256,
                "size": item.artifact.size,
            },
            "expectedReadable": item.expected_readable,
            "fixtureRoot": directory(item.fixture_root),
            "harnessOwned": item.harness_owned,
            "probeId": item.probe_id,
        }

    return {
        "allowedFile": file_fixture(value.allowed_file),
        "forbiddenFile": file_fixture(value.forbidden_file),
        "harnessRoot": directory(value.harness_root),
        "loopback": network(value.loopback),
        "nonLoopback": network(value.non_loopback),
        "profile": {
            "fileId": value.profile.file_id.hex(),
            "name": value.profile.profile_name,
            "reparse": value.profile.is_reparse_point,
            "sid": value.profile.sid.hex(),
            "storagePath": value.profile.storage_path,
            "volumeSerial": value.profile.volume_serial,
        },
        "requestId": value.request_id,
        "requestRoot": directory(value.request_root),
        "schemaVersion": 1,
    }


def _config_hash(config):
    content = json.dumps(
        config, ensure_ascii=True, separators=(",", ":"),
        sort_keys=True).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _expected_admission_hashes(value):
    return (
        ("NQ-04", _config_hash({
            "host": value.loopback.host, "port": value.loopback.port})),
        ("NQ-05", _config_hash({
            "host": value.non_loopback.host, "port": value.non_loopback.port})),
        ("NQ-06", _config_hash({
            "path": value.forbidden_file.artifact.path,
            "sha256": value.forbidden_file.artifact.sha256})),
        ("NQ-07", _config_hash({
            "path": value.allowed_file.artifact.path,
            "sha256": value.allowed_file.artifact.sha256})),
    )


def _validate_admissions(value, admissions):
    if type(admissions) is not tuple or len(admissions) != 4:
        _deny("exact four admission evidence records required")
    expected = dict(_expected_admission_hashes(value))
    seen = set()
    for admission in admissions:
        if type(admission) is not ProbeAdmissionEvidence:
            _deny("exact admission evidence required")
        if admission.probe_id not in expected or admission.probe_id in seen:
            _deny("admission probe identity mismatch or duplicate")
        if admission.request_id != value.request_id:
            _deny("admission request identity mismatch")
        if (admission.profile_name != value.profile.profile_name
                or admission.appcontainer_sid != value.profile.sid):
            _deny("admission profile identity mismatch")
        if (admission.request_root_volume_serial != value.request_root.volume_serial
                or admission.request_root_file_id != value.request_root.file_id):
            _deny("admission request root identity mismatch")
        if admission.probe_config_sha256 != expected[admission.probe_id]:
            _deny("admission probe config identity mismatch")
        seen.add(admission.probe_id)
    if seen != set(expected):
        _deny("admission probe set incomplete")
    return tuple((probe_id, expected[probe_id]) for probe_id in sorted(expected))


def _validate(value):
    if type(value) is not ProbeTargetContract:
        _deny("exact probe target contract required")
    if (type(value.request_id) is not str
            or REQUEST_ID_PATTERN.fullmatch(value.request_id) is None):
        _deny("request identity malformed")
    request_root = _directory(value.request_root, "request root")
    harness_root = _directory(value.harness_root, "harness root")
    profile_root = _profile(value.profile)
    if request_root.name != value.request_id:
        _deny("request root identity mismatch")
    if request_root == harness_root or _descendant(harness_root, request_root):
        _deny("harness root must contain request root, not be contained by it")
    if not _descendant(request_root, harness_root):
        _deny("request root must be inside harness root")
    if (harness_root == profile_root
            or _descendant(harness_root, profile_root)
            or _descendant(profile_root, harness_root)):
        _deny("harness and profile roots must be disjoint")

    _network(value.loopback, "NQ-04", True)
    _network(value.non_loopback, "NQ-05", False)
    if value.loopback.port == value.non_loopback.port:
        _deny("network fixtures must use distinct ports")
    if value.loopback.listener_id == value.non_loopback.listener_id:
        _deny("network listener identities must be distinct")
    if value.loopback.listener_nonce_sha256 == value.non_loopback.listener_nonce_sha256:
        _deny("network listener nonces must be distinct")

    forbidden_path, forbidden_root = _file(value.forbidden_file, "NQ-06", False)
    allowed_path, allowed_root = _file(value.allowed_file, "NQ-07", True)
    if allowed_root != request_root or not _descendant(allowed_path, request_root):
        _deny("allowed fixture must be inside exact request root")
    if forbidden_root != harness_root:
        _deny("forbidden fixture root must be exact harness root")
    if (_descendant(forbidden_path, request_root)
            or forbidden_path == profile_root
            or _descendant(forbidden_path, profile_root)):
        _deny("forbidden fixture must be outside allowed roots")
    if forbidden_path == allowed_path:
        _deny("file fixture paths must be distinct")


def validate_probe_targets(reviewed, candidate, *, admissions):
    """Return immutable evidence for exact, value-only target identities."""
    _validate(reviewed)
    if type(candidate) is not ProbeTargetContract:
        _deny("exact candidate target contract required")
    if candidate != reviewed:
        _deny("candidate target contract differs from review")
    admission_hashes = _validate_admissions(reviewed, admissions)
    canonical = json.dumps(
        _canonical_contract(reviewed), ensure_ascii=True,
        separators=(",", ":"), sort_keys=True).encode("utf-8")
    return ProbeTargetEvidence(
        request_id=reviewed.request_id,
        target_contract_sha256=hashlib.sha256(canonical).hexdigest(),
        loopback_listener_id=reviewed.loopback.listener_id,
        non_loopback_listener_id=reviewed.non_loopback.listener_id,
        forbidden_file_sha256=reviewed.forbidden_file.artifact.sha256,
        allowed_file_sha256=reviewed.allowed_file.artifact.sha256,
        admission_config_hashes=admission_hashes,
        accepted_connection_budget=0,
        filesystem_escape_success_budget=0,
    )
