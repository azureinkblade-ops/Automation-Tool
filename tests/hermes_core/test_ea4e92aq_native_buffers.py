"""Synthetic buffer preparation tests; no process is created."""

import ctypes
from dataclasses import replace
import inspect
import subprocess

import pytest

from tools import ea4e92s_native_buffers as subject
from tools.ea4e92s_creation_attributes import prepare_creation_attributes
from tools.ea4e92s_probe_admission import ProbeAdmissionDenied
from tests.hermes_core.test_ea4e92s_probe_admission import (
    BOOTSTRAP, RUNTIME, policy, request_content,
)
from tests.hermes_core.test_ea4e92s_windows_attributes import FakeKernel, adapter


@pytest.mark.parametrize("argv", [
    (r"C:\Program Files\node.exe", r"C:\request root\probe.js"),
    ("runtime", "", "plain"),
    ("runtime", 'a"b', r"a\"b", r"a\\\"b"),
    ("runtime", "a b\\", "two tabs\there", "a\\\\"),
    ("runtime", "\u96ea", "\U0001f642"),
])
def test_pure_encoder_matches_standard_windows_quoting(argv):
    assert subject.encode_windows_argv(argv) == subprocess.list2cmdline(argv)


@pytest.mark.parametrize("argv", [
    (), [], ("runtime", "bad\0argument"), ("runtime", "\ud800"),
    ("runtime", 3),
])
def test_malformed_argv_denied(argv):
    with pytest.raises(ValueError):
        subject.encode_windows_argv(argv)


def test_utf16_limit_includes_terminating_null():
    assert len(subject.encode_windows_argv(("a" * 32766,))) == 32766
    with pytest.raises(ValueError, match="limit"):
        subject.encode_windows_argv(("a" * 32767,))
    assert subject.encode_windows_argv(("a" * 32763, "\U0001f642"))
    with pytest.raises(ValueError, match="limit"):
        subject.encode_windows_argv(("a" * 32764, "\U0001f642"))


def prepared(reviewed=None, candidate=None, *, attributes=None, **content):
    reviewed = reviewed if reviewed is not None else policy()
    candidate = candidate if candidate is not None else reviewed
    if attributes is None:
        attributes = prepare_creation_attributes(
            adapter(FakeKernel()), 71, 91, object())
    value = subject.prepare_probe_buffers(
        reviewed, candidate, attributes,
        runtime_bytes=content.get("runtime_bytes", RUNTIME),
        bootstrap_bytes=content.get("bootstrap_bytes", BOOTSTRAP),
        request_bytes=content.get(
            "request_bytes", request_content(
                reviewed.request_id, reviewed.probe_id, reviewed.probe_config)),
    )
    return value, attributes


def test_prepared_buffers_retain_exact_inputs_and_attribute_owner():
    reviewed = policy()
    value, attributes = prepared(reviewed)
    assert value.inputs.application_name == reviewed.runtime.path
    assert value.startup.attributes is attributes
    assert value.command_line.value == subprocess.list2cmdline(reviewed.argv)
    assert value.application_name.value == reviewed.runtime.path
    assert value.current_directory.value == reviewed.request_root.path
    assert bytes(value.environment) == value.inputs.environment_block
    assert value.startup.value.lpAttributeList == ctypes.addressof(attributes.handle.buffer)
    assert subject.validate_prepared_probe_buffers(value) is value
    attributes.close()


@pytest.mark.parametrize("field", [
    "application_name", "command_line", "environment", "current_directory",
    "startup", "attributes", "closed",
])
def test_buffer_or_owner_drift_denied(field):
    value, attributes = prepared()
    if field == "environment":
        value.environment[0] = b"X"
    elif field == "startup":
        value.startup.value.StartupInfo.cb = 0
    elif field == "attributes":
        attributes.handle.buffer[0] = b"X"
    elif field == "closed":
        attributes.close()
    else:
        getattr(value, field)[0] = "X"
    with pytest.raises(ValueError):
        subject.validate_prepared_probe_buffers(value)
    if field != "closed":
        attributes.close()


def test_candidate_and_content_drift_denied_before_buffer_preparation():
    reviewed = policy()
    attributes = prepare_creation_attributes(adapter(FakeKernel()), 71, 91, object())
    with pytest.raises(ProbeAdmissionDenied):
        prepared(reviewed, replace(reviewed, argv=("other",)), attributes=attributes)
    with pytest.raises(ProbeAdmissionDenied):
        prepared(reviewed, attributes=attributes, runtime_bytes=b"other")
    attributes.close()


def test_source_has_no_process_or_resume_binding():
    source = inspect.getsource(subject)
    for forbidden in (
            "WinDLL", "CreateProcessW", "ResumeThread", "subprocess",
            "Popen", "socket", "requests"):
        assert forbidden not in source
