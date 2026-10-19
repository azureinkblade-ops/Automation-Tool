"""Explicit local-profile app-host context check; never execution authority."""

from dataclasses import dataclass
import re
import uuid
from typing import Callable


PROFILE_ID = "ea4e92ml-local-container-app-host-v1"
_SID = re.compile(r"S-[0-9]+(?:-[0-9]+){2,}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class LocalAppHostPolicy:
    app_instance_id: str
    account_sid: str
    store_instance_id: str
    store_generation: int
    governing_commit: str
    enabled: bool = False
    profile_id: str = PROFILE_ID


@dataclass(frozen=True)
class LocalAppHostRequest:
    app_instance_id: str
    store_instance_id: str
    store_generation: int
    governing_commit: str
    profile_id: str = PROFILE_ID


@dataclass(frozen=True)
class LocalAppHostDecision:
    decision: str
    reason: str


def _uuid(value):
    if type(value) is not str:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def check_local_app_host(
    policy: LocalAppHostPolicy,
    request: LocalAppHostRequest,
    *,
    account_reader: Callable[[], str],
    store_reader: Callable[[], tuple[str, int]],
) -> LocalAppHostDecision:
    """Compare trusted configured context with read-only live observations."""
    deny = lambda reason: LocalAppHostDecision("DENY", reason)
    if type(policy) is not LocalAppHostPolicy or policy.enabled is not True:
        return deny("LOCAL_PROFILE_DISABLED")
    if (policy.profile_id != PROFILE_ID
            or not _uuid(policy.app_instance_id)
            or type(policy.account_sid) is not str
            or not _SID.fullmatch(policy.account_sid)
            or not _uuid(policy.store_instance_id)
            or type(policy.store_generation) is not int
            or policy.store_generation < 1
            or type(policy.governing_commit) is not str
            or not _COMMIT.fullmatch(policy.governing_commit)):
        return deny("LOCAL_PROFILE_POLICY_INVALID")
    if (type(request) is not LocalAppHostRequest
            or type(request.profile_id) is not str
            or type(request.app_instance_id) is not str
            or type(request.store_instance_id) is not str
            or type(request.store_generation) is not int
            or type(request.governing_commit) is not str
            or request.profile_id != policy.profile_id
            or request.app_instance_id != policy.app_instance_id
            or request.store_instance_id != policy.store_instance_id
            or request.store_generation != policy.store_generation
            or request.governing_commit != policy.governing_commit):
        return deny("LOCAL_PROFILE_REQUEST_MISMATCH")
    if not callable(account_reader) or not callable(store_reader):
        return deny("LOCAL_PROFILE_OBSERVER_MISSING")
    try:
        observed_sid = account_reader()
        observed_store = store_reader()
    except Exception:
        return deny("LOCAL_PROFILE_OBSERVATION_UNAVAILABLE")
    if type(observed_sid) is not str or observed_sid != policy.account_sid:
        return deny("LOCAL_PROFILE_ACCOUNT_MISMATCH")
    if (type(observed_store) is not tuple or len(observed_store) != 2
            or type(observed_store[0]) is not str
            or type(observed_store[1]) is not int
            or observed_store != (policy.store_instance_id, policy.store_generation)):
        return deny("LOCAL_PROFILE_STORE_MISMATCH")
    return LocalAppHostDecision("MATCH", "LOCAL_PROFILE_CONTEXT_ONLY")
