"""EA-1 schema / domain parity tests.

Confirms the YAML schemas under docs/architecture/schemas validate the same
critical structural constraints as the Python domain model, using the existing
SchemaCatalog validator.
"""

from __future__ import annotations

import copy
import unittest

from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.schemas import SchemaValidationError, load_schema_catalog
from tests.hermes_core.test_execution_authorization_domain import (
    make_authorization,
    make_decision,
    make_request,
)
from tools.hermes_core.execution_authorization import (
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecisionOutcome,
)


def _to_builtin(obj):
    """Recursively convert dataclasses/(str,Enum) to plain JSON-able dicts.

    Note: the canonical preimage (to_canonical_dict) deliberately excludes
    artifact_hash; for SCHEMA validation we include artifact_hash because the
    serialized artifact carries it (the schema requires it).
    """
    import dataclasses

    if hasattr(obj, "to_canonical_dict"):
        d = obj.to_canonical_dict()
        d["artifact_hash"] = obj.artifact_hash
        return d
    if isinstance(obj, dict):
        return {k: _to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_builtin(v) for v in obj]
    if isinstance(obj, ExecutionAuthorizationActorType):
        return obj.value
    if isinstance(obj, ExecutionAuthorizationDecisionOutcome):
        return obj.value
    return obj


class TestSchemaDomainParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_schema_catalog()

    def test_authorization_schema_valid_for_domain(self):
        doc = _to_builtin(make_authorization())
        self.catalog.validate("hermes.execution_authorization", doc)

    def test_request_schema_valid_for_domain(self):
        doc = _to_builtin(make_request())
        self.catalog.validate("hermes.execution_authorization_request", doc)

    def test_decision_schema_valid_for_domain(self):
        doc = _to_builtin(make_decision())
        self.catalog.validate("hermes.execution_authorization_decision", doc)

    def test_schema_accepts_attempt_limit_zero_limitation(self):
        # SCHEMA-LIMITATION: the shared SchemaCatalog validator does not enforce
        # `minimum` on integer-typed fields (only `number` type checks bounds).
        # Therefore the YAML schema cannot reject attempt_limit=0. The Python
        # domain model DOES reject it (see test_attempt_limit_zero_rejected in
        # the domain suite). This test documents the gap; it must not be "fixed"
        # by weakening Python validation.
        doc = _to_builtin(make_authorization())
        doc["authorized_scope"]["attempt_limit"] = 0  # valid Python build, naive schema
        self.catalog.validate("hermes.execution_authorization", doc)

    def test_schema_accepts_non_utc_timestamp_limitation(self):
        # SCHEMA-LIMITATION: SchemaCatalog's date-time format accepts a naive ISO
        # timestamp (no 'Z'); it does not require absolute UTC. The Python domain
        # model DOES require a trailing 'Z' (see test_non_utc_issued_at_rejected
        # in the domain suite). This test documents the gap.
        doc = _to_builtin(make_authorization())
        doc["issued_at"] = "2026-08-12T21:30:00"  # no Z
        self.catalog.validate("hermes.execution_authorization", doc)

    def test_schema_rejects_unknown_decision_outcome(self):
        doc = _to_builtin(make_decision())
        doc["outcome"] = "MAYBE"
        with self.assertRaises(SchemaValidationError):
            self.catalog.validate("hermes.execution_authorization_decision", doc)

    def test_schema_rejects_missing_required_field(self):
        doc = _to_builtin(make_authorization())
        doc.pop("accepted_governance_hash")
        with self.assertRaises(SchemaValidationError):
            self.catalog.validate("hermes.execution_authorization", doc)

    def test_schema_allows_null_expires_at(self):
        doc = _to_builtin(make_authorization(expires_at=None))
        self.catalog.validate("hermes.execution_authorization", doc)

    def test_decision_schema_granted_requires_authorization_id_present(self):
        # Schema cannot express the GRANTED-requires-id cross-field rule cleanly;
        # documented limitation. The Python validation enforces it. Here we only
        # confirm the schema accepts the well-formed GRANTED shape (id present).
        doc = _to_builtin(make_decision())
        self.catalog.validate("hermes.execution_authorization_decision", doc)


if __name__ == "__main__":
    unittest.main()
