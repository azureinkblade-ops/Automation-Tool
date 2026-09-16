"""Value-only admission for reviewed containment probes; no runtime capability."""

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import PureWindowsPath

from tools.ea4e92s_profile_preflight import ProfileSnapshot, canonical_local_path


PROBE_IDS = tuple(f"NQ-{number:02d}" for number in range(1, 13))
ENVIRONMENT_NAMES = frozenset({"systemroot", "temp", "tmp", "windir"})
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUEST_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")


class ProbeAdmissionDenied(ValueError):
    """The candidate does not exactly match the reviewed probe contract."""


@dataclass(frozen=True)
class ArtifactIdentity:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class DirectoryIdentity:
    path: str
    volume_serial: int
    file_id: bytes
    reparse: bool


@dataclass(frozen=True)
class ProbeBudgets:
    wall_clock_ms: int = 10_000
    process_memory_bytes: int = 256 * 1024 * 1024
    input_bytes: int = 64 * 1024
    stdout_bytes: int = 4 * 1024 * 1024
    stderr_bytes: int = 64 * 1024
    active_processes: int = 1
    descendants: int = 0


@dataclass(frozen=True)
class ProbeAdmissionContract:
    request_id: str
    probe_id: str
    runtime: ArtifactIdentity
    bootstrap: ArtifactIdentity
    request_artifact: ArtifactIdentity
    request_root: DirectoryIdentity
    profile: ProfileSnapshot
    probe_config: tuple
    argv: tuple
    environment: tuple
    budgets: ProbeBudgets


@dataclass(frozen=True)
class ProbeAdmissionEvidence:
    request_id: str
    probe_id: str
    runtime_sha256: str
    bootstrap_sha256: str
    request_sha256: str
    probe_config_sha256: str
    profile_name: str
    appcontainer_sid: bytes
    request_root_volume_serial: int
    request_root_file_id: bytes
    wall_clock_ms: int
    process_memory_bytes: int
    stdout_bytes: int
    stderr_bytes: int
    active_process_limit: int
    descendant_limit: int


def _deny(message):
    raise ProbeAdmissionDenied(message)


def _absolute_local_path(value, label):
    try:
        canonical = canonical_local_path(value)
    except ValueError:
        _deny(f"{label} path must be absolute local path")
    return PureWindowsPath(canonical)


def _artifact(value, label, maximum):
    if type(value) is not ArtifactIdentity:
        _deny(f"exact {label} identity required")
    _absolute_local_path(value.path, label)
    if type(value.size) is not int or not 0 < value.size <= maximum:
        _deny(f"{label} size invalid")
    if type(value.sha256) is not str or SHA256_PATTERN.fullmatch(value.sha256) is None:
        _deny(f"{label} sha256 invalid")


def _directory(value, label):
    if type(value) is not DirectoryIdentity:
        _deny(f"exact {label} identity required")
    _absolute_local_path(value.path, label)
    if (type(value.volume_serial) is not int
            or not 0 <= value.volume_serial < 1 << 64):
        _deny(f"{label} volume identity invalid")
    if type(value.file_id) is not bytes or len(value.file_id) != 16:
        _deny(f"{label} file identity invalid")
    if value.reparse is not False:
        _deny(f"{label} reparse path denied")


def _profile(value):
    if type(value) is not ProfileSnapshot:
        _deny("exact profile snapshot required")
    if type(value.profile_name) is not str or not value.profile_name or "\0" in value.profile_name:
        _deny("profile name invalid")
    _absolute_local_path(value.storage_path, "profile")
    if type(value.sid) is not bytes or not 8 <= len(value.sid) <= 68:
        _deny("profile SID invalid")
    if (type(value.volume_serial) is not int
            or not 0 <= value.volume_serial < 1 << 64):
        _deny("profile volume identity invalid")
    if type(value.file_id) is not bytes or len(value.file_id) != 16:
        _deny("profile file identity invalid")
    if value.is_reparse_point is not False:
        _deny("profile reparse path denied")


def _is_descendant(child, root):
    try:
        relative = child.relative_to(root)
    except ValueError:
        return False
    return bool(relative.parts)


def _validate_environment(value, request_root):
    if type(value) is not tuple:
        _deny("environment must be canonical tuple")
    names = []
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            _deny("environment entry malformed")
        name, content = item
        if type(name) is not str or type(content) is not str:
            _deny("environment entry malformed")
        folded = name.casefold()
        if folded not in ENVIRONMENT_NAMES or folded in names:
            _deny("environment name denied")
        if not content or "\0" in content:
            _deny("environment value malformed")
        _absolute_local_path(content, f"environment {name}")
        names.append(folded)
    if set(names) != ENVIRONMENT_NAMES:
        _deny("environment names must match exact allowlist")
    if value != tuple(sorted(value, key=lambda pair: pair[0].casefold())):
        _deny("environment order is not canonical")
    environment = {name.casefold(): content for name, content in value}
    if PureWindowsPath(environment["systemroot"]) != PureWindowsPath(environment["windir"]):
        _deny("environment Windows roots mismatch")
    if PureWindowsPath(environment["temp"]) != PureWindowsPath(environment["tmp"]):
        _deny("environment temporary roots mismatch")
    if not _is_descendant(
            PureWindowsPath(environment["temp"]), PureWindowsPath(request_root.path)):
        _deny("environment temporary root must be inside request root")


def _validate_budgets(value):
    if type(value) is not ProbeBudgets or value != ProbeBudgets():
        _deny("exact probe budget required")


def _probe_config_dict(probe_id, value):
    if type(value) is not tuple:
        _deny("probe config must be canonical tuple")
    if any(type(item) is not tuple or len(item) != 2 for item in value):
        _deny("probe config entry malformed")
    names = [item[0] for item in value]
    if any(type(name) is not str for name in names) or len(set(names)) != len(names):
        _deny("probe config names malformed")
    if value != tuple(sorted(value)):
        _deny("probe config order is not canonical")
    config = dict(value)
    expected_names = (
        {"host", "port"} if probe_id in {"NQ-04", "NQ-05"}
        else {"path", "sha256"} if probe_id in {"NQ-06", "NQ-07"}
        else set()
    )
    if set(config) != expected_names:
        _deny("probe config keys differ from probe contract")
    if probe_id in {"NQ-04", "NQ-05"}:
        if type(config["host"]) is not str or type(config["port"]) is not int:
            _deny("network probe config malformed")
        if not 1 <= config["port"] <= 65535:
            _deny("network probe port invalid")
        try:
            address = ipaddress.ip_address(config["host"])
        except ValueError as error:
            raise ProbeAdmissionDenied("network probe host must be literal IP") from error
        if probe_id == "NQ-04" and not address.is_loopback:
            _deny("loopback probe requires loopback target")
        if probe_id == "NQ-05" and (
                address.is_loopback or address.is_unspecified or address.is_multicast):
            _deny("non-loopback probe target invalid")
    if probe_id in {"NQ-06", "NQ-07"}:
        if type(config["path"]) is not str:
            _deny("filesystem probe path malformed")
        _absolute_local_path(config["path"], "filesystem probe target")
        if (type(config["sha256"]) is not str
                or SHA256_PATTERN.fullmatch(config["sha256"]) is None):
            _deny("filesystem probe sha256 malformed")
    return config


def _validate_contract(value):
    if type(value) is not ProbeAdmissionContract:
        _deny("exact probe admission contract required")
    if type(value.request_id) is not str or REQUEST_ID_PATTERN.fullmatch(value.request_id) is None:
        _deny("request identity malformed")
    if type(value.probe_id) is not str or value.probe_id not in PROBE_IDS:
        _deny("probe identity malformed")

    _artifact(value.runtime, "runtime", 256 * 1024 * 1024)
    _artifact(value.bootstrap, "bootstrap", 1024 * 1024)
    _artifact(value.request_artifact, "request artifact", 64 * 1024)
    _directory(value.request_root, "request root")
    _profile(value.profile)
    _probe_config_dict(value.probe_id, value.probe_config)

    root = PureWindowsPath(value.request_root.path)
    if root.name != value.request_id:
        _deny("request root identity mismatch")
    for artifact, label in (
            (value.bootstrap, "bootstrap"),
            (value.request_artifact, "request artifact")):
        if not _is_descendant(PureWindowsPath(artifact.path), root):
            _deny(f"{label} must be inside request root")
    if len({value.runtime.path.casefold(), value.bootstrap.path.casefold(),
            value.request_artifact.path.casefold()}) != 3:
        _deny("artifact paths must be distinct")

    expected_argv = (
        value.runtime.path, value.bootstrap.path,
        "--probe-id", value.probe_id,
        "--request-id", value.request_id,
        "--request", value.request_artifact.path,
    )
    if type(value.argv) is not tuple or value.argv != expected_argv:
        _deny("exact ordered argv required")
    if any(type(item) is not str or not item or "\0" in item for item in value.argv):
        _deny("argv entry malformed")

    _validate_environment(value.environment, value.request_root)
    _validate_budgets(value.budgets)


def _match_content(identity, content, label):
    if type(content) is not bytes:
        _deny(f"{label} content must be immutable bytes")
    if len(content) != identity.size or hashlib.sha256(content).hexdigest() != identity.sha256:
        _deny(f"{label} identity mismatch")


def _validate_request_content(contract, content):
    budgets = contract.budgets
    expected = {
        "budgets": {
            "activeProcesses": budgets.active_processes,
            "descendants": budgets.descendants,
            "inputBytes": budgets.input_bytes,
            "processMemoryBytes": budgets.process_memory_bytes,
            "stderrBytes": budgets.stderr_bytes,
            "stdoutBytes": budgets.stdout_bytes,
            "wallClockMs": budgets.wall_clock_ms,
        },
        "probeConfig": _probe_config_dict(contract.probe_id, contract.probe_config),
        "probeId": contract.probe_id,
        "requestId": contract.request_id,
        "schemaVersion": 1,
    }
    try:
        decoded = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeAdmissionDenied("request schema invalid") from error
    canonical = json.dumps(
        expected, ensure_ascii=True, separators=(",", ":"),
        sort_keys=True).encode("utf-8")
    if decoded != expected or content != canonical:
        _deny("request schema or canonical encoding mismatch")


def validate_probe_admission(reviewed, candidate, *, runtime_bytes,
                             bootstrap_bytes, request_bytes):
    """Return value-only evidence for an exact reviewed candidate.

    Byte acquisition and handle/path race protection belong to a later native
    boundary. This function has no filesystem, process, network or probe
    execution capability and its result is not launch authority.
    """
    _validate_contract(reviewed)
    if type(candidate) is not ProbeAdmissionContract:
        _deny("exact candidate contract required")
    if candidate != reviewed:
        _deny("candidate differs from reviewed contract")

    _match_content(reviewed.runtime, runtime_bytes, "runtime")
    _match_content(reviewed.bootstrap, bootstrap_bytes, "bootstrap")
    _match_content(reviewed.request_artifact, request_bytes, "request artifact")
    _validate_request_content(reviewed, request_bytes)

    budgets = reviewed.budgets
    config_bytes = json.dumps(
        _probe_config_dict(reviewed.probe_id, reviewed.probe_config),
        ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return ProbeAdmissionEvidence(
        reviewed.request_id,
        reviewed.probe_id,
        reviewed.runtime.sha256,
        reviewed.bootstrap.sha256,
        reviewed.request_artifact.sha256,
        hashlib.sha256(config_bytes).hexdigest(),
        reviewed.profile.profile_name,
        reviewed.profile.sid,
        reviewed.request_root.volume_serial,
        reviewed.request_root.file_id,
        budgets.wall_clock_ms,
        budgets.process_memory_bytes,
        budgets.stdout_bytes,
        budgets.stderr_bytes,
        budgets.active_processes,
        budgets.descendants,
    )
