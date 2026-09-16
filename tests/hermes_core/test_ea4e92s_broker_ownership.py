"""Fake-only broker ownership orchestration; no process is resumed."""

import pytest

from tools import ea4e92s_broker_ownership as subject
from tools.ea4e92s_pre_resume import PreResumeDenied, PreResumeEvidence
from tools.ea4e92s_profile_preflight import ProfileSnapshot
from tools.ea4e92s_profile_security_binding import (
    BoundProfileSecurity, UnknownBoundCleanup)
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult,
    UnknownSuspendedProcess)
from tools.ea4e92s_windows_job import UnknownJobCleanup


SID = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"


class SecurityResource:
    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail
        self.state = "owned"
        self.attributes = type("Attributes", (), {"state": "owned"})()

    def close(self):
        self.events.append("security_close")
        self.state = "unknown"
        if self.fail:
            raise OSError("scripted security cleanup failure")
        self.state = "closed"


class ProcessApi:
    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail

    def terminate(self, handle):
        self.events.append("process_terminate")
        if self.fail:
            raise OSError("scripted process cleanup failure")
        return True

    def close_thread(self, handle):
        self.events.append("thread_close")
        return True

    def close_process(self, handle):
        self.events.append("process_close")
        return True


def resources(events, security_fail=False, process_fail=False):
    profile = ProfileSnapshot(
        "reviewed-profile", SID, r"C:\reviewed-profile", 7,
        bytes(range(16)), False)
    security = SecurityResource(events, security_fail)
    bound = BoundProfileSecurity(profile, security)
    created = SuspendedCreationResult(101, 102, 201, 202, True, True, True)
    process = OwnedSuspendedProcess(
        ProcessApi(events, process_fail), created, bound)
    evidence = PreResumeEvidence(
        41, 101, 102, 201, 202, "reviewed-profile", SID)
    return bound, process, evidence


class Backend:
    def __init__(self, stage_failure=None, malformed=None, security_fail=False,
                 process_fail=False, job_close=True):
        self.stage_failure = stage_failure
        self.malformed = malformed
        self.security_fail = security_fail
        self.process_fail = process_fail
        self.job_close_result = job_close
        self.events = []
        self.security, self.process, self.evidence = resources(
            self.events, security_fail, process_fail)

    def step(self, name, value):
        self.events.append(name)
        if self.stage_failure == name:
            error = (PreResumeDenied("scripted verification denial")
                     if name == "verify" else OSError(f"scripted {name} failure"))
            raise error
        return self.malformed if self.malformed == name else value

    def prepare_job(self):
        return self.step("job", 41)

    def prepare_security(self, job_handle):
        assert job_handle == 41
        return self.step("security", self.security)

    def create_suspended(self, security):
        assert security is self.security
        return self.step("create", self.process)

    def verify_pre_resume(self, process, job_handle):
        assert process is self.process and job_handle == 41
        return self.step("verify", self.evidence)

    def close_job(self, job_handle):
        assert job_handle == 41
        self.events.append("job_close")
        if self.stage_failure == "job_close":
            raise OSError("scripted job cleanup failure")
        return self.job_close_result


def test_success_returns_owned_verified_process_and_closes_security_first():
    backend = Backend()
    owned = subject.prepare_verified_suspended_process(backend)
    assert owned.state == "owned"
    assert owned.process is backend.process
    assert owned.evidence is backend.evidence
    assert owned.job_handle == 41
    assert backend.security.state == "closed"
    assert backend.events == [
        "job", "security", "create", "verify", "security_close"]


def test_returned_owner_closes_process_then_job_and_is_idempotent():
    backend = Backend()
    owned = subject.prepare_verified_suspended_process(backend)
    owned.close()
    owned.close()
    assert owned.state == "closed"
    assert owned.job_handle is None
    assert backend.events[-4:] == [
        "process_terminate", "thread_close", "process_close", "job_close"]


def test_job_preparation_failure_is_definitive_denial_without_cleanup():
    backend = Backend(stage_failure="job")
    with pytest.raises(subject.BrokerDenied, match="job preparation"):
        subject.prepare_verified_suspended_process(backend)
    assert backend.events == ["job"]


def test_missing_job_result_is_denied_without_speculative_cleanup():
    backend = Backend()
    backend.prepare_job = lambda: None
    with pytest.raises(subject.BrokerDenied, match="job handle"):
        subject.prepare_verified_suspended_process(backend)


@pytest.mark.parametrize("job", [0, -1, True, "41"])
def test_nonnull_malformed_job_result_is_unknown(job):
    backend = Backend()
    backend.prepare_job = lambda: job
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        subject.prepare_verified_suspended_process(backend)
    assert caught.value.resources.uncertain is job


def test_uncertain_job_preparation_preserves_lower_layer_evidence_without_retry():
    backend = Backend()
    error = UnknownJobCleanup("scripted uncertain job", backend, 41)
    backend.prepare_job = lambda: (_ for _ in ()).throw(error)
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        subject.prepare_verified_suspended_process(backend)
    assert caught.value.resources.uncertain is error
    assert backend.events == []


@pytest.mark.parametrize("stage", ["security", "verify"])
def test_known_preparation_or_verification_failure_cleans_and_denies(stage):
    backend = Backend(stage_failure=stage)
    with pytest.raises(subject.BrokerDenied):
        subject.prepare_verified_suspended_process(backend)
    if stage == "security":
        assert backend.events == ["job", "security", "job_close"]
    else:
        assert backend.events == [
            "job", "security", "create", "verify", "process_terminate",
            "thread_close", "process_close", "security_close", "job_close"]


def test_ambiguous_creation_failure_cleans_known_resources_but_stays_unknown():
    backend = Backend(stage_failure="create")
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        subject.prepare_verified_suspended_process(backend)
    assert caught.value.resources.security is backend.security
    assert caught.value.resources.process is None
    assert backend.events == [
        "job", "security", "create", "security_close", "job_close"]


@pytest.mark.parametrize("stage", ["security", "create", "verify"])
def test_malformed_stage_result_cleans_all_known_resources(stage):
    backend = Backend(malformed=stage)
    error = (subject.BrokerDenied if stage == "verify"
             else subject.UnknownBrokerContainment)
    with pytest.raises(error):
        subject.prepare_verified_suspended_process(backend)
    assert backend.events[-1] == "job_close"


def test_uncertain_security_preparation_preserves_bound_evidence_without_retry():
    backend = Backend()
    backend.security.state = "unknown"
    error = UnknownBoundCleanup("scripted uncertain security", backend.security)
    backend.prepare_security = lambda job: (_ for _ in ()).throw(error)
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        subject.prepare_verified_suspended_process(backend)
    assert caught.value.resources.security is backend.security
    assert caught.value.resources.job_handle is None
    assert backend.events == ["job", "job_close"]


def test_security_close_failure_after_verification_cleans_process_and_job_unknown():
    backend = Backend(security_fail=True)
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        subject.prepare_verified_suspended_process(backend)
    assert caught.value.resources.process is backend.process
    assert backend.events[-4:] == [
        "process_terminate", "thread_close", "process_close", "job_close"]


@pytest.mark.parametrize("failure", ["process", "job_false", "job_exception"])
def test_returned_owner_cleanup_uncertainty_is_sticky_and_blocks_retry(failure):
    backend = Backend(
        process_fail=failure == "process",
        job_close=None if failure == "job_false" else True,
        stage_failure="job_close" if failure == "job_exception" else None)
    owned = subject.prepare_verified_suspended_process(backend)
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        owned.close()
    assert caught.value.resources is owned.resources
    assert owned.state == "unknown"
    assert (owned.job_handle == 41) is (failure != "process")
    assert backend.events[-1] == "job_close"
    before = list(backend.events)
    with pytest.raises(subject.UnknownBrokerContainment, match="reconciliation"):
        owned.close()
    assert backend.events == before


def test_denial_cleanup_uncertainty_promotes_result_to_unknown():
    backend = Backend(stage_failure="verify", process_fail=True)
    with pytest.raises(subject.UnknownBrokerContainment) as caught:
        subject.prepare_verified_suspended_process(backend)
    assert caught.value.resources.process is backend.process
    assert backend.events[-1] == "job_close"


def test_source_has_no_native_launch_resume_or_runtime_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "subprocess", "Popen", "WinDLL", "CreateProcessW", "ResumeThread",
            "resume_process", "socket", "requests", "ComfyUI"):
        assert forbidden not in text
