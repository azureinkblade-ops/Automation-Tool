"""Synthetic value-only launch-input tests; no process is created."""

from dataclasses import replace
import inspect

import pytest

from tools import ea4e92s_launch_inputs as subject
from tools.ea4e92s_creation_provenance import (
    CREATE_SUSPENDED,
    CREATE_UNICODE_ENVIRONMENT,
    EXTENDED_STARTUPINFO_PRESENT,
)
from tools.ea4e92s_probe_admission import ProbeAdmissionDenied
from tests.hermes_core.test_ea4e92s_probe_admission import (
    BOOTSTRAP, RUNTIME, policy, request_content,
)


def build(reviewed=None, candidate=None, **content):
    reviewed = reviewed if reviewed is not None else policy()
    candidate = candidate if candidate is not None else reviewed
    return subject.build_probe_launch_inputs(
        reviewed, candidate,
        runtime_bytes=content.get("runtime_bytes", RUNTIME),
        bootstrap_bytes=content.get("bootstrap_bytes", BOOTSTRAP),
        request_bytes=content.get(
            "request_bytes", request_content(
                reviewed.request_id, reviewed.probe_id, reviewed.probe_config)),
    )


def test_exact_inputs_retain_order_and_unicode_block_without_launch_authority():
    reviewed = policy()
    prepared = build(reviewed)
    assert type(prepared) is subject.ProbeLaunchInputs
    assert prepared.application_name == reviewed.runtime.path
    assert prepared.argv is reviewed.argv
    assert prepared.creation_flags == (
        CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        | EXTENDED_STARTUPINFO_PRESENT)
    assert prepared.environment_block == (
        "\0".join(f"{name}={value}" for name, value in reviewed.environment)
        + "\0\0").encode("utf-16-le")
    assert prepared.environment_block.endswith(b"\0\0\0\0")
    assert prepared.admission.request_id == reviewed.request_id
    assert not hasattr(prepared, "command_line")
    assert not hasattr(prepared, "resume_authorized")


def test_non_ascii_paths_are_preserved_in_unicode_environment():
    reviewed = policy()
    root = replace(reviewed.request_root,
                   path=reviewed.request_root.path.replace("EA4E92S", "EA4E92S-\u96ea"))
    temp = root.path + r"\tmp"
    reviewed = replace(
        reviewed,
        request_root=root,
        bootstrap=replace(reviewed.bootstrap, path=root.path + r"\probe-bootstrap.js"),
        request_artifact=replace(reviewed.request_artifact,
                                 path=root.path + r"\probe-request.json"),
        environment=(("SystemRoot", r"C:\Windows"), ("TEMP", temp),
                     ("TMP", temp), ("WINDIR", r"C:\Windows")),
    )
    reviewed = replace(reviewed, argv=(
        reviewed.runtime.path, reviewed.bootstrap.path,
        "--probe-id", reviewed.probe_id,
        "--request-id", reviewed.request_id,
        "--request", reviewed.request_artifact.path,
    ))
    prepared = build(reviewed)
    assert "\u96ea" in prepared.environment_block.decode("utf-16-le")


@pytest.mark.parametrize("change", [
    {"argv": ("other.exe",)},
    {"environment": (("PATH", r"C:\Windows"),)},
    {"request_id": "other-request"},
])
def test_candidate_drift_denied_before_build(change):
    reviewed = policy()
    with pytest.raises(ProbeAdmissionDenied):
        build(reviewed, replace(reviewed, **change))


@pytest.mark.parametrize("content", [
    {"runtime_bytes": b"other-runtime"},
    {"bootstrap_bytes": b"other-bootstrap"},
    {"request_bytes": b"{}"},
])
def test_content_drift_denied_before_build(content):
    with pytest.raises(ProbeAdmissionDenied):
        build(**content)


def test_builder_has_no_launch_or_resume_capability():
    source = inspect.getsource(subject)
    for forbidden in (
            "WinDLL", "CreateProcessW", "ResumeThread", "subprocess",
            "Popen", "socket", "requests", "CommandLineToArgvW"):
        assert forbidden not in source
