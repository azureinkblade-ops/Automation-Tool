"""Fake-only source preflight; no process or native path inspector is invoked."""

import ctypes
from dataclasses import replace
import inspect

import pytest

from tools import ea4e92s_creator_preflight as subject
from tools.ea4e92s_creation_provenance import (
    CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT, EXTENDED_STARTUPINFO_PRESENT,
)
from tests.hermes_core.test_ea4e92aq_native_buffers import prepared
from tests.hermes_core.test_ea4e92s_probe_admission import policy


class FakeInspector:
    def __init__(self, snapshots):
        self.snapshots = {item.path: item for item in snapshots}
        self.calls = []

    def inspect(self, path):
        self.calls.append(path)
        return self.snapshots[path]


def identity_fixture(reviewed):
    artifacts = (reviewed.runtime, reviewed.bootstrap, reviewed.request_artifact)
    pins = tuple(subject.FilePin(
        item.path, 100 + index, bytes([index + 1]) * 16,
        item.size, item.sha256,
    ) for index, item in enumerate(artifacts))
    snapshots = [subject.PathSnapshot(
        item.path, item.volume_serial, item.file_id,
        False, False, item.size, item.sha256,
    ) for item in pins]
    root = reviewed.request_root
    profile = reviewed.profile
    snapshots.extend((
        subject.PathSnapshot(root.path, root.volume_serial, root.file_id,
                             False, True),
        subject.PathSnapshot(profile.storage_path, profile.volume_serial,
                             profile.file_id, False, True),
    ))
    return pins, FakeInspector(snapshots)


def test_exact_fake_preflight_and_noninvoking_call_plan():
    reviewed = policy()
    buffers, attributes = prepared(reviewed)
    pins, inspector = identity_fixture(reviewed)
    try:
        plan = subject.prepare_creation_call_plan(reviewed, buffers, pins, inspector)
        assert len(plan.snapshots) == 5
        assert inspector.calls == [item.path for item in plan.snapshots]
        assert plan.application_name_address == ctypes.addressof(buffers.application_name)
        assert plan.command_line_address == ctypes.addressof(buffers.command_line)
        assert plan.environment_address == ctypes.addressof(buffers.environment)
        assert plan.current_directory_address == ctypes.addressof(buffers.current_directory)
        assert plan.startup_address == ctypes.addressof(buffers.startup.value)
        assert plan.creation_flags == (CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
                                       | EXTENDED_STARTUPINFO_PRESENT)
        assert plan.inherit_handles is False
        assert plan.process_security_attributes is None
        assert plan.thread_security_attributes is None
        assert subject.validate_creation_call_plan(plan, inspector) is plan
    finally:
        attributes.close()


@pytest.mark.parametrize("field", [
    "path", "volume_serial", "file_id", "reparse", "directory", "size", "sha256",
])
def test_file_snapshot_drift_denied(field):
    reviewed = policy()
    pins, inspector = identity_fixture(reviewed)
    old = inspector.snapshots[pins[0].path]
    replacement = {
        "path": old.path + "x", "volume_serial": 1234,
        "file_id": b"z" * 16, "reparse": True, "directory": True,
        "size": old.size + 1, "sha256": "f" * 64,
    }[field]
    inspector.snapshots[pins[0].path] = replace(old, **{field: replacement})
    with pytest.raises(ValueError):
        subject.inspect_exact_paths(reviewed, pins, inspector)


@pytest.mark.parametrize("index", [3, 4])
def test_directory_and_profile_identity_drift_denied(index):
    reviewed = policy()
    pins, inspector = identity_fixture(reviewed)
    path = (reviewed.request_root.path, reviewed.profile.storage_path)[index - 3]
    inspector.snapshots[path] = replace(inspector.snapshots[path], reparse=True)
    with pytest.raises(ValueError):
        subject.inspect_exact_paths(reviewed, pins, inspector)


def test_changed_file_pin_and_cross_request_denied():
    reviewed = policy()
    buffers, attributes = prepared(reviewed)
    pins, inspector = identity_fixture(reviewed)
    try:
        with pytest.raises(ValueError):
            subject.inspect_exact_paths(
                reviewed, (replace(pins[0], file_id=b"x" * 16), *pins[1:]), inspector)
        with pytest.raises(ValueError):
            subject.prepare_creation_call_plan(
                replace(reviewed, request_id="other-request"), buffers,
                pins, inspector)
    finally:
        attributes.close()


@pytest.mark.parametrize("field", ["creation_flags", "environment_block", "runtime_sha256"])
def test_replaced_input_values_denied(field):
    reviewed = policy()
    buffers, attributes = prepared(reviewed)
    pins, inspector = identity_fixture(reviewed)
    try:
        if field == "runtime_sha256":
            admission = replace(buffers.inputs.admission, runtime_sha256="f" * 64)
            inputs = replace(buffers.inputs, admission=admission)
        elif field == "creation_flags":
            inputs = replace(buffers.inputs, creation_flags=0)
        else:
            inputs = replace(buffers.inputs, environment_block=b"X")
            buffers.environment[0] = b"X"
        with pytest.raises(ValueError):
            subject.prepare_creation_call_plan(
                reviewed, replace(buffers, inputs=inputs), pins, inspector)
    finally:
        attributes.close()


def test_late_path_drift_and_closed_buffer_owner_denied():
    reviewed = policy()
    buffers, attributes = prepared(reviewed)
    pins, inspector = identity_fixture(reviewed)
    plan = subject.prepare_creation_call_plan(reviewed, buffers, pins, inspector)
    path = reviewed.profile.storage_path
    inspector.snapshots[path] = replace(inspector.snapshots[path], file_id=b"z" * 16)
    with pytest.raises(ValueError):
        subject.validate_creation_call_plan(plan, inspector)
    attributes.close()
    with pytest.raises(ValueError):
        subject.validate_creation_call_plan(plan, inspector)


def test_source_has_no_native_or_process_invocation():
    source = inspect.getsource(subject)
    for forbidden in ("WinDLL", "CreateProcessW", "ResumeThread", "subprocess",
                      "Popen", "socket", "requests", "os.system"):
        assert forbidden not in source
