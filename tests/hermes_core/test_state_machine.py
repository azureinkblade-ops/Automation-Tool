from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.hermes_core import (
    ArtifactBundle,
    SchemaValidationError,
    StateTransitionError,
    load_schema_catalog,
    validate_transition,
)


TASK_ID = "11111111-1111-1111-1111-111111111111"


def task_doc() -> dict:
    return {
        "task_id": TASK_ID,
        "title": "Hermes validator test",
        "created_at": "2026-08-01T10:00:00Z",
        "requested_by": "David",
        "current_state": "DRAFT",
        "scope": {
            "project_id": "hermes",
            "permitted_read_paths": ["docs/architecture/**"],
            "permitted_write_paths": ["tools/hermes_core/**"],
            "network_policy": "none",
        },
        "authority": {
            "governance_owner": "hermes",
            "execution_requires_authorization": True,
        },
    }


def evidence_doc() -> dict:
    return {
        "evidence_package_id": "evidence-1",
        "task_id": TASK_ID,
        "created_at": "2026-08-01T10:01:00Z",
        "inventory": [
            {
                "artifact_id": "artifact-1",
                "path_or_uri": "docs/architecture/state-machine.md",
                "sha256": "abc123",
            }
        ],
        "package_sha256": "package123",
        "frozen": True,
    }


def review_doc(**authority_overrides: bool) -> dict:
    authority = {
        "can_modify_state": False,
        "can_authorize_execution": False,
        "can_execute": False,
    }
    authority.update(authority_overrides)
    return {
        "review_id": "22222222-2222-2222-2222-222222222222",
        "task_id": TASK_ID,
        "reviewer": {
            "agent_id": "reviewer-1",
            "model_id": "review-model",
            "role": "reviewer",
        },
        "evidence_package_id": "evidence-1",
        "started_at": "2026-08-01T10:02:00Z",
        "completed_at": "2026-08-01T10:03:00Z",
        "findings": [],
        "recommendation": "accept",
        "authority": authority,
    }


def consensus_doc(result: str = "ACCEPTED") -> dict:
    return {
        "consensus_id": "consensus-1",
        "task_id": TASK_ID,
        "policy_id": "policy-1",
        "input_review_ids": ["22222222-2222-2222-2222-222222222222"],
        "calculated_at": "2026-08-01T10:04:00Z",
        "result": result,
        "authority": {
            "can_generate_acceptance": True,
            "can_authorize_execution": False,
            "can_execute": False,
        },
    }


def acceptance_doc(**authority_overrides: bool) -> dict:
    authority = {
        "can_authorize_execution": False,
        "requires_separate_authorization": True,
    }
    authority.update(authority_overrides)
    return {
        "acceptance_id": "33333333-3333-3333-3333-333333333333",
        "task_id": TASK_ID,
        "consensus_id": "consensus-1",
        "evidence_package_id": "evidence-1",
        "accepted_at": "2026-08-01T10:05:00Z",
        "acceptance_sha256": "acceptance-hash",
        "authority": authority,
    }


def authorization_doc(parent_hash: str = "acceptance-hash", expires_at: str = "2026-08-08T00:00:00Z") -> dict:
    return {
        "authorization_id": "44444444-4444-4444-4444-444444444444",
        "task_id": TASK_ID,
        "authorized_phase": "Hermes Core validator",
        "parent_acceptance_sha256": parent_hash,
        "allowed_operations": ["validate transitions"],
        "prohibited_operations": ["execute app workflows"],
        "permitted_read_paths": ["docs/architecture/**"],
        "permitted_write_paths": ["tools/hermes_core/**"],
        "network_policy": "none",
        "fixture_policy": "write_temp_fixtures",
        "expires_at": expires_at,
        "issuing_authority": "human_owner",
        "authorization_sha256": "authorization-hash",
    }


class HermesStateMachineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def test_schema_catalog_loads_all_foundation_contracts(self) -> None:
        self.assertEqual(len(self.catalog.schemas), 9)
        self.assertIn("hermes.task", self.catalog.schemas)
        self.assertIn("hermes.authorization", self.catalog.schemas)

    def test_task_schema_validates_required_scope_and_authority(self) -> None:
        self.catalog.validate("hermes.task", task_doc())
        invalid = task_doc()
        invalid["authority"]["governance_owner"] = "reviewer"
        with self.assertRaises(SchemaValidationError):
            self.catalog.validate("hermes.task", invalid)

    def test_allows_documented_acceptance_path_with_required_artifacts(self) -> None:
        result = validate_transition(
            "CONSENSUS_CALCULATED",
            "ACCEPTED",
            ArtifactBundle(consensus=consensus_doc(), event_parent_ref="consensus-1"),
            self.catalog,
        )
        self.assertTrue(result.accepted)

    def test_rejects_acceptance_to_authorized_shortcut(self) -> None:
        with self.assertRaises(StateTransitionError):
            validate_transition(
                "ACCEPTED",
                "AUTHORIZED",
                ArtifactBundle(
                    acceptance=acceptance_doc(),
                    authorization=authorization_doc(),
                    event_parent_ref="acceptance-hash",
                ),
                self.catalog,
            )

    def test_reviewer_records_cannot_directly_alter_state(self) -> None:
        with self.assertRaises(StateTransitionError):
            validate_transition(
                "UNDER_REVIEW",
                "CONSENSUS_CALCULATED",
                ArtifactBundle(
                    reviews=[review_doc(can_modify_state=True)],
                    event_parent_ref="review-1",
                ),
                self.catalog,
            )

    def test_acceptance_cannot_authorize_execution(self) -> None:
        with self.assertRaises(StateTransitionError):
            validate_transition(
                "ACCEPTED",
                "AWAITING_EXECUTION_AUTHORIZATION",
                ArtifactBundle(
                    acceptance=acceptance_doc(can_authorize_execution=True),
                    event_parent_ref="acceptance-hash",
                ),
                self.catalog,
            )

    def test_authorization_requires_parent_acceptance_hash(self) -> None:
        with self.assertRaises(StateTransitionError):
            validate_transition(
                "AWAITING_EXECUTION_AUTHORIZATION",
                "AUTHORIZED",
                ArtifactBundle(
                    acceptance=acceptance_doc(),
                    authorization=authorization_doc(parent_hash="wrong-hash"),
                    event_parent_ref="authorization-hash",
                    now=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                self.catalog,
            )

    def test_authorization_expires_before_execution(self) -> None:
        with self.assertRaises(StateTransitionError):
            validate_transition(
                "AUTHORIZED",
                "EXECUTING",
                ArtifactBundle(
                    acceptance=acceptance_doc(),
                    authorization=authorization_doc(expires_at="2026-07-01T00:00:00Z"),
                    event_parent_ref="authorization-hash",
                    now=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                self.catalog,
            )

    def test_allows_authorized_execution_with_valid_authorization(self) -> None:
        result = validate_transition(
            "AUTHORIZED",
            "EXECUTING",
            ArtifactBundle(
                acceptance=acceptance_doc(),
                authorization=authorization_doc(),
                event_parent_ref="authorization-hash",
                now=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
            self.catalog,
        )
        self.assertTrue(result.accepted)


if __name__ == "__main__":
    unittest.main()
