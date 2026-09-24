"""Fake-only lifecycle ordering; never grants or performs a native resume."""

from threading import Lock

from tools.ea4e92s_creation_provenance import (
    CreationProvenanceDenied,
    SuspendedCreationReceipt,
    validate_creation_receipt,
)
from tools.ea4e92s_provenance_observation import UntrustedCreationObservation


class FakeLifecycleDenied(RuntimeError):
    """The fake lifecycle cannot advance."""


class FakeSuspendedLifecycle:
    def __init__(self, receipt):
        if type(receipt) is not SuspendedCreationReceipt:
            raise FakeLifecycleDenied("canonical fake receipt required")
        self.receipt = receipt
        self.owner = receipt.owned
        self.state = "created"
        self._lock = Lock()

    def _receipt_still_owned(self):
        try:
            validate_creation_receipt(
                self.receipt, self.owner, request_id=self.receipt.request_id,
                adapter_sha256=self.receipt.adapter_sha256,
                job_handle=self.receipt.job_handle)
        except CreationProvenanceDenied:
            return False
        return True

    def observe(self, observation):
        with self._lock:
            if (self.state != "created"
                    or type(observation) is not UntrustedCreationObservation
                    or observation.receipt is not self.receipt
                    or not self._receipt_still_owned()):
                self.state = "unknown"
                raise FakeLifecycleDenied("fake observation conflicts")
            self.state = "observed"

    def consume_test_transition(self, owner, receipt):
        """Mark one fake transition; no callback, OS operation or permit."""
        with self._lock:
            if (self.state != "observed" or owner is not self.owner
                    or receipt is not self.receipt
                    or not self._receipt_still_owned()):
                self.state = "unknown"
                raise FakeLifecycleDenied("fake transition denied")
            self.state = "consumed"

    def cancel(self):
        with self._lock:
            if self.state != "unknown":
                self.state = "cancelled"
