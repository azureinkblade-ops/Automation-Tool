"""Test-owned containment broker ownership; no native adapter or resume path."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_pre_resume import PreResumeEvidence
from tools.ea4e92s_profile_security_binding import (
    BoundProfileSecurity,
    UnknownBoundCleanup,
)
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess,
    UnknownSuspendedProcess,
)
from tools.ea4e92s_windows_job import UnknownJobCleanup


class BrokerDenied(RuntimeError):
    """Preparation was denied and every known resource was cleaned."""


class UnknownBrokerContainment(RuntimeError):
    """Preparation or cleanup is ambiguous; automatic retry is barred."""

    def __init__(self, message, resources):
        super().__init__(message)
        self.resources = resources


@dataclass
class BrokerResources:
    job_handle: int | None = None
    security: BoundProfileSecurity | None = None
    process: OwnedSuspendedProcess | None = None
    evidence: PreResumeEvidence | None = None
    uncertain: object | None = None


@dataclass
class PreparedVerifiedSuspendedProcess:
    backend: object
    resources: BrokerResources
    state: str = "owned"

    @property
    def job_handle(self):
        return self.resources.job_handle

    @property
    def process(self):
        return self.resources.process

    @property
    def evidence(self):
        return self.resources.evidence

    def close(self):
        if self.state == "closed":
            return
        if self.state != "owned":
            raise UnknownBrokerContainment(
                "broker cleanup requires reconciliation", self.resources)
        self.state = "unknown"
        if _cleanup_known(self.backend, self.resources) is not True:
            raise UnknownBrokerContainment(
                "broker cleanup requires reconciliation", self.resources)
        self.state = "closed"


def _valid_pointer(value):
    maximum = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    return type(value) is int and 0 < value <= maximum


def _cleanup_known(backend, resources):
    confirmed = True
    process = resources.process
    if process is not None:
        if type(process) is not OwnedSuspendedProcess:
            confirmed = False
        elif process.state == "owned":
            try:
                process.close()
            except BaseException:
                confirmed = False
        elif process.state != "closed":
            confirmed = False

    security = resources.security
    if security is not None:
        if type(security) is not BoundProfileSecurity:
            confirmed = False
        elif security.state == "owned":
            try:
                security.close()
            except BaseException:
                confirmed = False
        elif security.state != "closed":
            confirmed = False

    if resources.job_handle is not None:
        try:
            if backend.close_job(resources.job_handle) is True:
                resources.job_handle = None
            else:
                confirmed = False
        except BaseException:
            confirmed = False
    return confirmed


def _finish_failure(backend, resources, message, unknown=False, cause=None):
    cleaned = _cleanup_known(backend, resources)
    if unknown or cleaned is not True:
        error = UnknownBrokerContainment(message, resources)
    else:
        error = BrokerDenied(message)
    if cause is not None:
        raise error from cause
    raise error


def prepare_verified_suspended_process(backend):
    """Prepare and verify a suspended process through an injected backend.

    The backend is responsible for delegating each stage to reviewed components.
    This ownership layer contains no OS binding, command/environment construction,
    resume operation, parser execution or fallback launch path.
    """
    resources = BrokerResources()
    try:
        job_handle = backend.prepare_job()
    except UnknownJobCleanup as error:
        resources.uncertain = error
        raise UnknownBrokerContainment(
            "job preparation cleanup unknown", resources) from error
    except BaseException as error:
        raise BrokerDenied("job preparation failed") from error
    if job_handle is None:
        raise BrokerDenied("valid job handle not returned")
    if not _valid_pointer(job_handle):
        resources.uncertain = job_handle
        raise UnknownBrokerContainment(
            "job handle ownership unknown", resources)
    resources.job_handle = job_handle

    try:
        security = backend.prepare_security(job_handle)
    except UnknownBoundCleanup as error:
        resources.security = error.bound
        _finish_failure(
            backend, resources, "security preparation cleanup unknown",
            unknown=True, cause=error)
    except BaseException as error:
        _finish_failure(
            backend, resources, "security preparation failed", cause=error)
    if type(security) is not BoundProfileSecurity or security.state != "owned":
        resources.uncertain = security
        _finish_failure(
            backend, resources, "security preparation malformed", unknown=True)
    resources.security = security

    try:
        process = backend.create_suspended(security)
    except UnknownSuspendedProcess as error:
        resources.process = error.owned
        resources.uncertain = error
        _finish_failure(
            backend, resources, "suspended creation outcome unknown",
            unknown=True, cause=error)
    except BaseException as error:
        _finish_failure(
            backend, resources, "suspended creation outcome unknown",
            unknown=True, cause=error)
    if type(process) is not OwnedSuspendedProcess or process.state != "owned":
        resources.uncertain = process
        _finish_failure(
            backend, resources, "suspended creation evidence malformed",
            unknown=True)
    resources.process = process

    try:
        evidence = backend.verify_pre_resume(process, job_handle)
    except BaseException as error:
        _finish_failure(
            backend, resources, "pre-resume verification denied", cause=error)
    if type(evidence) is not PreResumeEvidence:
        _finish_failure(
            backend, resources, "pre-resume verification evidence malformed")
    resources.evidence = evidence

    try:
        security.close()
    except BaseException as error:
        _finish_failure(
            backend, resources, "creation-security cleanup unknown",
            unknown=True, cause=error)
    resources.security = None
    return PreparedVerifiedSuspendedProcess(backend, resources)
