"""Fake-only creator ordering; no native call or trusted receipt."""

from threading import Lock

from tools.ea4e92s_creator_preflight import (
    CreationCallPlan, validate_creation_call_plan,
)
from tools.ea4e92s_suspended_process import SuspendedCreationResult


class FakeCreatorDenied(RuntimeError):
    """The simulated one-attempt owner cannot advance."""


class FakeCreatorOwner:
    def __init__(self, plan):
        if type(plan) is not CreationCallPlan:
            raise ValueError("exact source-only call plan required")
        self.plan = plan
        self.state = "prepared"
        self.attempts = 0
        self.result = None
        self.inspector = None
        self._lock = Lock()

    def _deny(self, message):
        self.state = "unknown"
        raise FakeCreatorDenied(message)

    def _check_plan(self, plan):
        if plan is not self.plan or self.inspector is None:
            self._deny("fake owner mismatch")
        try:
            validate_creation_call_plan(plan, self.inspector)
        except BaseException as error:
            self.state = "unknown"
            raise FakeCreatorDenied("fake owner preflight changed") from error

    def begin_fake_call(self, plan, inspector):
        """Consume the simulated attempt before any return is recorded."""
        with self._lock:
            if self.state != "prepared" or plan is not self.plan:
                self._deny("fake call replay or owner mismatch")
            try:
                validate_creation_call_plan(plan, inspector)
            except BaseException as error:
                self.state = "unknown"
                raise FakeCreatorDenied("fake call preflight changed") from error
            self.inspector = inspector
            self.attempts = 1
            self.state = "call_in_progress"

    def record_fake_return(self, plan, result):
        """Keep returned numbers untrusted; no positive verdict exists."""
        with self._lock:
            if self.state != "call_in_progress" or plan is not self.plan:
                self._deny("fake return conflicts with attempt")
            self.result = result
            self._check_plan(plan)
            if type(result) is not SuspendedCreationResult:
                self._deny("fake return is noncanonical")
            handles = (result.process_handle, result.thread_handle)
            ids = (result.process_id, result.thread_id)
            if (any(type(value) is not int or value <= 0 for value in handles + ids)
                    or handles[0] == handles[1]
                    or any(value > 0xFFFFFFFF for value in ids)):
                self._deny("fake return identity malformed")
            self.state = "returned_untrusted"

    def begin_fake_cleanup(self, plan, result):
        with self._lock:
            if (self.state != "returned_untrusted" or plan is not self.plan
                    or result is not self.result):
                self._deny("fake cleanup owner mismatch")
            self._check_plan(plan)
            self.state = "cleanup_pending"

    def record_fake_cleanup(self, plan, result, *, confirmed):
        with self._lock:
            if (self.state != "cleanup_pending" or plan is not self.plan
                    or result is not self.result or confirmed is not True):
                self._deny("fake cleanup unconfirmed")
            self._check_plan(plan)
            self.state = "closed_fake"

    def cancel(self):
        with self._lock:
            if self.state == "prepared":
                self.state = "cancelled"
            elif self.state not in ("closed_fake", "cancelled", "unknown"):
                self.state = "unknown"
