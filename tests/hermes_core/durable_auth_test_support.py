"""Test-only migration helpers for pre-EA-4E.32 fake authorization fixtures."""

import threading

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableAuthorizationStoreError,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
    ProductionInvocationAuthorizationPolicy,
)


class QualificationDurablePolicy(ProductionInvocationAuthorizationPolicy):
    """Persist legacy fabricated artifacts before exercising durable policy."""

    def __init__(self, *, clock, store):
        super().__init__(clock=clock, store=store)
        self.qualification_store = store
        self._qualification_seed_lock = threading.Lock()

    def _seed_if_absent(self, authorization: ProductionInvocationAuthorization) -> None:
        with self._qualification_seed_lock:
            try:
                self.qualification_store.inspect_by_id(
                    authorization.invocation_authorization_id
                )
                return
            except DurableAuthorizationStoreError as exc:
                if "absent from durable state" not in str(exc):
                    return
            payload = authorization.to_canonical_dict()
            self.qualification_store.persist_issued(
                issue_request_id=f"legacy-test-{authorization.invocation_authorization_id}",
                issue_request_hash=sha256_payload(payload),
                authorization_payload=payload,
            )

    def evaluate(self, authorization, handle, bound_meta, **kwargs):
        self._seed_if_absent(authorization)
        return super().evaluate(authorization, handle, bound_meta, **kwargs)

    def claim_for_execution(self, authorization, handle, bound_meta, **kwargs):
        self._seed_if_absent(authorization)
        return super().claim_for_execution(authorization, handle, bound_meta, **kwargs)


def qualification_store(tmp_path, name="invocation-authorizations.sqlite3"):
    store_path = tmp_path / name
    anchor_path = tmp_path / f"{name}.anchor.json"
    return DurableInvocationAuthorizationStore.initialize(
        store_path, anchor_path=anchor_path
    )
