"""Synthetic probe-admission contract tests; no artifact is executed."""

import hashlib
import json
from dataclasses import replace

import pytest

from tools import ea4e92s_probe_admission as subject
from tools.ea4e92s_profile_preflight import ProfileSnapshot


RUNTIME = b"synthetic-node-runtime"
BOOTSTRAP = b"synthetic-probe-bootstrap"
SID = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"


def artifact(path, content):
    return subject.ArtifactIdentity(
        path, len(content), hashlib.sha256(content).hexdigest())


def probe_config(probe_id):
    if probe_id == "NQ-04":
        return (("host", "127.0.0.1"), ("port", 43192))
    if probe_id == "NQ-05":
        return (("host", "192.0.2.1"), ("port", 43193))
    if probe_id in {"NQ-06", "NQ-07"}:
        return (("path", rf"C:\EA4E92S\fixtures\{probe_id}.bin"),
                ("sha256", "a" * 64))
    return ()


def request_content(request_id="ea4e92s-request-0001", probe_id="NQ-02",
                    config=None):
    budgets = subject.ProbeBudgets()
    config = probe_config(probe_id) if config is None else config
    return json.dumps({
        "schemaVersion": 1,
        "requestId": request_id,
        "probeId": probe_id,
        "budgets": {
            "wallClockMs": budgets.wall_clock_ms,
            "processMemoryBytes": budgets.process_memory_bytes,
            "inputBytes": budgets.input_bytes,
            "stdoutBytes": budgets.stdout_bytes,
            "stderrBytes": budgets.stderr_bytes,
            "activeProcesses": budgets.active_processes,
            "descendants": budgets.descendants,
        },
        "probeConfig": dict(config),
    }, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


REQUEST = request_content()


def policy(**changes):
    request_id = changes.pop("request_id", "ea4e92s-request-0001")
    probe_id = changes.pop("probe_id", "NQ-02")
    root = subject.DirectoryIdentity(
        r"C:\EA4E92S\ea4e92s-request-0001", 7, bytes(range(16)), False)
    profile = ProfileSnapshot(
        "ea4e92s-profile", SID, r"C:\Profiles\ea4e92s", 8,
        bytes(range(16, 32)), False)
    runtime = artifact(r"C:\Runtime\node.exe", RUNTIME)
    bootstrap = artifact(
        r"C:\EA4E92S\ea4e92s-request-0001\probe-bootstrap.js", BOOTSTRAP)
    config = changes.pop("probe_config", probe_config(probe_id))
    request_bytes = request_content(request_id, probe_id, config)
    request = artifact(
        r"C:\EA4E92S\ea4e92s-request-0001\probe-request.json", request_bytes)
    base = subject.ProbeAdmissionContract(
        request_id=request_id,
        probe_id=probe_id,
        runtime=runtime,
        bootstrap=bootstrap,
        request_artifact=request,
        request_root=root,
        profile=profile,
        probe_config=config,
        argv=(
            runtime.path, bootstrap.path,
            "--probe-id", probe_id,
            "--request-id", request_id,
            "--request", request.path,
        ),
        environment=(
            ("SystemRoot", r"C:\Windows"),
            ("TEMP", r"C:\EA4E92S\ea4e92s-request-0001\tmp"),
            ("TMP", r"C:\EA4E92S\ea4e92s-request-0001\tmp"),
            ("WINDIR", r"C:\Windows"),
        ),
        budgets=subject.ProbeBudgets(),
    )
    return replace(base, **changes)


def admit(reviewed=None, candidate=None, **contents):
    reviewed = reviewed or policy()
    candidate = candidate or reviewed
    return subject.validate_probe_admission(
        reviewed,
        candidate,
        runtime_bytes=contents.get("runtime_bytes", RUNTIME),
        bootstrap_bytes=contents.get("bootstrap_bytes", BOOTSTRAP),
        request_bytes=contents.get(
            "request_bytes",
            request_content(reviewed.request_id, reviewed.probe_id)),
    )


def test_exact_candidate_returns_value_only_evidence():
    evidence = admit()
    assert evidence.request_id == "ea4e92s-request-0001"
    assert evidence.probe_id == "NQ-02"
    assert evidence.runtime_sha256 == hashlib.sha256(RUNTIME).hexdigest()
    assert evidence.bootstrap_sha256 == hashlib.sha256(BOOTSTRAP).hexdigest()
    assert evidence.request_sha256 == hashlib.sha256(REQUEST).hexdigest()
    assert evidence.probe_config_sha256 == hashlib.sha256(b"{}").hexdigest()
    assert evidence.profile_name == "ea4e92s-profile"
    assert evidence.appcontainer_sid == SID
    assert evidence.active_process_limit == 1
    assert evidence.descendant_limit == 0


@pytest.mark.parametrize("probe_id", subject.PROBE_IDS)
def test_all_frozen_probe_ids_are_admissible_as_exact_contracts(probe_id):
    reviewed = policy(probe_id=probe_id)
    reviewed = replace(
        reviewed,
        argv=(
            reviewed.runtime.path, reviewed.bootstrap.path,
            "--probe-id", probe_id,
            "--request-id", reviewed.request_id,
            "--request", reviewed.request_artifact.path,
        ))
    assert admit(reviewed).probe_id == probe_id


@pytest.mark.parametrize("probe_id", ["NQ-04", "NQ-05", "NQ-06", "NQ-07"])
def test_probe_target_config_is_bound_to_evidence(probe_id):
    reviewed = policy(probe_id=probe_id)
    expected = json.dumps(
        dict(reviewed.probe_config), separators=(",", ":"), sort_keys=True).encode()
    assert admit(reviewed).probe_config_sha256 == hashlib.sha256(expected).hexdigest()


@pytest.mark.parametrize("probe_id,config", [
    ("NQ-02", (("host", "127.0.0.1"),)),
    ("NQ-04", (("host", "192.0.2.1"), ("port", 43192))),
    ("NQ-05", (("host", "127.0.0.1"), ("port", 43193))),
    ("NQ-05", (("host", "example.com"), ("port", 43193))),
    ("NQ-06", (("path", "relative.bin"), ("sha256", "a" * 64))),
    ("NQ-07", (("path", r"C:\fixture.bin"), ("sha256", "bad"))),
])
def test_invalid_or_misclassified_probe_target_denied(probe_id, config):
    reviewed = policy(probe_id=probe_id, probe_config=config)
    with pytest.raises(subject.ProbeAdmissionDenied, match="probe|loopback|network|filesystem"):
        admit(reviewed)


@pytest.mark.parametrize("probe_id", [None, "", "NQ-00", "NQ-13", 2])
def test_unknown_or_malformed_probe_id_denied(probe_id):
    with pytest.raises(subject.ProbeAdmissionDenied):
        admit(policy(probe_id=probe_id))


@pytest.mark.parametrize("request_id", [None, "", "short", "UPPER-REQUEST", "bad/id"])
def test_malformed_request_id_denied(request_id):
    reviewed = policy(request_id=request_id)
    with pytest.raises(subject.ProbeAdmissionDenied):
        admit(reviewed)


@pytest.mark.parametrize("field,value", [
    ("runtime", artifact(r"C:\Other\node.exe", RUNTIME)),
    ("bootstrap", artifact(r"C:\EA4E92S\request-0001\other.js", BOOTSTRAP)),
    ("request_artifact", artifact(
        r"C:\EA4E92S\ea4e92s-request-0001\other.json", REQUEST)),
    ("environment", (("SystemRoot", r"C:\Different"),)),
    ("budgets", replace(subject.ProbeBudgets(), stdout_bytes=8 * 1024 * 1024)),
])
def test_candidate_drift_denied(field, value):
    reviewed = policy()
    candidate = replace(reviewed, **{field: value})
    with pytest.raises(subject.ProbeAdmissionDenied, match="candidate"):
        admit(reviewed, candidate)


@pytest.mark.parametrize("name", [
    "PATH", "Path", "NODE_OPTIONS", "NODE_PATH", "OPENAI_API_KEY",
    "HTTPS_PROXY", "USERPROFILE",
])
def test_unreviewed_or_sensitive_environment_name_denied(name):
    reviewed = policy(environment=((name, "value"),))
    with pytest.raises(subject.ProbeAdmissionDenied, match="environment"):
        admit(reviewed)


def test_case_insensitive_duplicate_environment_name_denied():
    reviewed = policy(environment=(
        ("TEMP", r"C:\temp"), ("temp", r"C:\other")))
    with pytest.raises(subject.ProbeAdmissionDenied, match="environment"):
        admit(reviewed)


@pytest.mark.parametrize("field,value", [
    ("TEMP", r"C:\Outside\tmp"),
    ("TMP", r"C:\Outside\tmp"),
    ("SystemRoot", r"C:\OtherWindows"),
    ("WINDIR", r"C:\OtherWindows"),
])
def test_mismatched_or_escaped_environment_paths_denied(field, value):
    reviewed = policy()
    environment = tuple(
        (name, value if name == field else content)
        for name, content in reviewed.environment)
    with pytest.raises(subject.ProbeAdmissionDenied, match="environment"):
        admit(replace(reviewed, environment=environment))


@pytest.mark.parametrize("environment", [
    {"TEMP": r"C:\temp"},
    (("TEMP", ""),),
    (("TEMP", "bad\0value"),),
    (("TEMP", r"C:\temp"), ("SystemRoot", r"C:\Windows")),
])
def test_noncanonical_environment_denied(environment):
    with pytest.raises(subject.ProbeAdmissionDenied, match="environment"):
        admit(policy(environment=environment))


@pytest.mark.parametrize("argv", [
    (),
    (r"C:\Runtime\node.exe",),
    policy().argv + ("--extra",),
    tuple(reversed(policy().argv)),
    policy().argv[:-1] + ("bad\0path",),
])
def test_noncanonical_argv_denied(argv):
    with pytest.raises(subject.ProbeAdmissionDenied, match="argv"):
        admit(policy(argv=argv))


@pytest.mark.parametrize("field,content", [
    ("runtime_bytes", RUNTIME + b"x"),
    ("bootstrap_bytes", BOOTSTRAP + b"x"),
    ("request_bytes", REQUEST + b"x"),
])
def test_artifact_content_drift_denied(field, content):
    with pytest.raises(subject.ProbeAdmissionDenied, match="identity"):
        admit(**{field: content})


@pytest.mark.parametrize("payload", [
    {**json.loads(REQUEST), "extra": True},
    {**json.loads(REQUEST), "probeId": "NQ-03"},
])
def test_hash_matched_but_semantically_changed_request_denied(payload):
    content = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    reviewed = policy()
    reviewed = replace(
        reviewed,
        request_artifact=artifact(reviewed.request_artifact.path, content))
    with pytest.raises(subject.ProbeAdmissionDenied, match="schema"):
        admit(reviewed, request_bytes=content)


def test_hash_matched_but_noncanonical_request_encoding_denied():
    content = json.dumps(json.loads(REQUEST), indent=2).encode()
    reviewed = policy()
    reviewed = replace(
        reviewed,
        request_artifact=artifact(reviewed.request_artifact.path, content))
    with pytest.raises(subject.ProbeAdmissionDenied, match="canonical"):
        admit(reviewed, request_bytes=content)


@pytest.mark.parametrize("field", [
    "runtime_bytes", "bootstrap_bytes", "request_bytes"])
def test_mutable_or_nonbyte_artifact_content_denied(field):
    with pytest.raises(subject.ProbeAdmissionDenied, match="bytes"):
        admit(**{field: bytearray(b"mutable")})


@pytest.mark.parametrize("field", ["bootstrap", "request_artifact"])
def test_staged_artifact_outside_request_root_denied(field):
    reviewed = policy()
    moved = replace(getattr(reviewed, field), path=r"C:\Other\escaped.bin")
    with pytest.raises(subject.ProbeAdmissionDenied, match="request root"):
        admit(replace(reviewed, **{field: moved}))


def test_reparse_request_root_denied():
    reviewed = policy()
    with pytest.raises(subject.ProbeAdmissionDenied, match="reparse"):
        admit(replace(
            reviewed,
            request_root=replace(reviewed.request_root, reparse=True)))


def test_reparse_profile_denied():
    reviewed = policy()
    with pytest.raises(subject.ProbeAdmissionDenied, match="profile"):
        admit(replace(
            reviewed,
            profile=replace(reviewed.profile, is_reparse_point=True)))


@pytest.mark.parametrize("field,value", [
    ("wall_clock_ms", 10001),
    ("process_memory_bytes", 256 * 1024 * 1024 + 1),
    ("input_bytes", 65537),
    ("stdout_bytes", 4 * 1024 * 1024 + 1),
    ("stderr_bytes", 65537),
    ("active_processes", 2),
    ("descendants", 1),
])
def test_any_budget_widening_denied(field, value):
    reviewed = policy(budgets=replace(
        subject.ProbeBudgets(), **{field: value}))
    with pytest.raises(subject.ProbeAdmissionDenied, match="budget"):
        admit(reviewed)


class ForgedContract(subject.ProbeAdmissionContract):
    pass


def test_subclassed_contract_denied():
    reviewed = policy()
    forged = ForgedContract(**reviewed.__dict__)
    with pytest.raises(subject.ProbeAdmissionDenied, match="exact"):
        admit(reviewed, forged)


def test_source_has_no_runtime_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "subprocess", "Popen", "WinDLL", "CreateProcessW", "ResumeThread",
            "socket", "requests", "urllib", "ComfyUI", "open("):
        assert forbidden not in text
