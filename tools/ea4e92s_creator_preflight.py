"""Source-only path and creation-argument preflight; no process launcher."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_creation_provenance import (
    CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT, EXTENDED_STARTUPINFO_PRESENT,
)
from tools.ea4e92s_native_buffers import validate_prepared_probe_buffers
from tools.ea4e92s_probe_admission import ProbeAdmissionContract
from tools.ea4e92s_profile_preflight import canonical_local_path


@dataclass(frozen=True)
class FilePin:
    path: str
    volume_serial: int
    file_id: bytes
    size: int
    sha256: str


@dataclass(frozen=True)
class PathSnapshot:
    path: str
    volume_serial: int
    file_id: bytes
    reparse: bool
    directory: bool
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class CreationCallPlan:
    reviewed: ProbeAdmissionContract
    buffers: object
    file_pins: tuple
    snapshots: tuple
    application_name_address: int
    command_line_address: int
    environment_address: int
    current_directory_address: int
    startup_address: int
    creation_flags: int
    inherit_handles: bool = False
    process_security_attributes: None = None
    thread_security_attributes: None = None


def _identity(path, volume, file_id):
    if type(path) is not str:
        raise ValueError("invalid path identity")
    canonical_local_path(path)
    if (type(volume) is not int or not 0 <= volume < 1 << 64
            or type(file_id) is not bytes or len(file_id) != 16):
        raise ValueError("invalid path identity")


def inspect_exact_paths(reviewed, file_pins, inspector):
    """Compare injected snapshots with reviewed pins; no OS inspection here."""
    if type(reviewed) is not ProbeAdmissionContract or type(file_pins) is not tuple or len(file_pins) != 3:
        raise ValueError("exact reviewed contract and three file pins required")
    if not callable(getattr(inspector, "inspect", None)):
        raise ValueError("path inspector required")
    expected = (reviewed.runtime, reviewed.bootstrap, reviewed.request_artifact)
    paths = []
    for artifact, pin in zip(expected, file_pins):
        if type(pin) is not FilePin:
            raise ValueError("exact file pin required")
        _identity(pin.path, pin.volume_serial, pin.file_id)
        if (pin.path != artifact.path or pin.size != artifact.size
                or pin.sha256 != artifact.sha256):
            raise ValueError("file pin differs from reviewed artifact")
        paths.append((pin.path, pin.volume_serial, pin.file_id, False,
                      pin.size, pin.sha256))
    root = reviewed.request_root
    profile = reviewed.profile
    paths.extend(((root.path, root.volume_serial, root.file_id, True, None, None),
                  (profile.storage_path, profile.volume_serial, profile.file_id,
                   True, None, None)))
    if len({path.casefold() for path, *_ in paths}) != len(paths):
        raise ValueError("path identities overlap")
    snapshots = []
    for path, volume, file_id, directory, size, sha256 in paths:
        _identity(path, volume, file_id)
        snapshot = inspector.inspect(path)
        if (type(snapshot) is not PathSnapshot or snapshot.path != path
                or type(snapshot.volume_serial) is not int
                or snapshot.volume_serial != volume
                or type(snapshot.file_id) is not bytes or snapshot.file_id != file_id
                or snapshot.reparse is not False
                or snapshot.directory is not directory
                or snapshot.size != size or snapshot.sha256 != sha256):
            raise ValueError("inspected path differs from reviewed identity")
        snapshots.append(snapshot)
    return tuple(snapshots)


def prepare_creation_call_plan(reviewed, buffers, file_pins, inspector):
    """Freeze exact pointer arguments without binding or invoking a native API."""
    validate_prepared_probe_buffers(buffers)
    environment = ("\0".join(f"{name}={value}" for name, value in reviewed.environment)
                   + "\0\0").encode("utf-16-le")
    admission = buffers.inputs.admission
    if (type(reviewed) is not ProbeAdmissionContract
            or buffers.inputs.application_name != reviewed.runtime.path
            or buffers.inputs.argv != reviewed.argv
            or buffers.inputs.environment_block != environment
            or buffers.inputs.creation_flags != (CREATE_SUSPENDED
                | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT)
            or buffers.request_root is not reviewed.request_root
            or admission.request_id != reviewed.request_id
            or admission.probe_id != reviewed.probe_id
            or admission.runtime_sha256 != reviewed.runtime.sha256
            or admission.bootstrap_sha256 != reviewed.bootstrap.sha256
            or admission.request_sha256 != reviewed.request_artifact.sha256
            or admission.appcontainer_sid != reviewed.profile.sid
            or admission.request_root_file_id != reviewed.request_root.file_id):
        raise ValueError("prepared buffers do not belong to reviewed request")
    snapshots = inspect_exact_paths(reviewed, file_pins, inspector)
    return CreationCallPlan(
        reviewed, buffers, file_pins, snapshots,
        ctypes.addressof(buffers.application_name),
        ctypes.addressof(buffers.command_line),
        ctypes.addressof(buffers.environment),
        ctypes.addressof(buffers.current_directory),
        ctypes.addressof(buffers.startup.value),
        buffers.inputs.creation_flags,
    )


def validate_creation_call_plan(plan, inspector):
    """Recheck owners and injected path snapshots before any future handoff."""
    if type(plan) is not CreationCallPlan:
        raise ValueError("exact creation call plan required")
    current = prepare_creation_call_plan(
        plan.reviewed, plan.buffers, plan.file_pins, inspector)
    if current != plan:
        raise ValueError("creation call plan drift")
    return plan
