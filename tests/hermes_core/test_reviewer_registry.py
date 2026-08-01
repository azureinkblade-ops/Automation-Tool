from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.hermes_core import ReviewerRegistry, ReviewerRegistryError, load_schema_catalog


class HermesReviewerRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_schema_catalog(Path(__file__).resolve().parents[2])

    def reviewer(self, agent_id: str = "reviewer-1", status: str = "active") -> dict:
        return {
            "agent_id": agent_id,
            "display_name": "Reviewer One",
            "role": "reviewer",
            "model_id": "local-model",
            "authority": {
                "can_review": True,
                "can_modify_governance_state": False,
                "can_authorize_execution": False,
                "can_execute": False,
            },
            "allowed_tools": [],
            "denied_tools": ["browser", "shell"],
            "status": status,
        }

    def test_loads_active_reviewers_from_documents(self) -> None:
        registry = ReviewerRegistry.from_documents(
            self.catalog,
            [self.reviewer("reviewer-1"), self.reviewer("reviewer-2", status="paused")],
        )

        self.assertEqual(registry.get("reviewer-1").model_id, "local-model")
        self.assertEqual([agent.agent_id for agent in registry.active_reviewers()], ["reviewer-1"])

    def test_loads_registry_file_with_reviewers_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviewers.json"
            path.write_text(
                json.dumps({"reviewers": [self.reviewer("reviewer-1")]}),
                encoding="utf-8",
            )

            registry = ReviewerRegistry.load(self.catalog, path)

            self.assertEqual(registry.require_active_count(1)[0].agent_id, "reviewer-1")

    def test_duplicate_agent_id_fails(self) -> None:
        with self.assertRaisesRegex(ReviewerRegistryError, "Duplicate reviewer agent_id"):
            ReviewerRegistry.from_documents(
                self.catalog,
                [self.reviewer("reviewer-1"), self.reviewer("reviewer-1")],
            )

    def test_non_reviewer_role_fails(self) -> None:
        document = self.reviewer()
        document["role"] = "engineer"

        with self.assertRaisesRegex(ReviewerRegistryError, "must use role reviewer"):
            ReviewerRegistry.from_documents(self.catalog, [document])

    def test_execution_authority_fails(self) -> None:
        document = self.reviewer()
        document["authority"]["can_execute"] = True

        with self.assertRaisesRegex(ReviewerRegistryError, "must not execute"):
            ReviewerRegistry.from_documents(self.catalog, [document])

    def test_governance_authority_fails(self) -> None:
        document = self.reviewer()
        document["authority"]["can_modify_governance_state"] = True

        with self.assertRaisesRegex(ReviewerRegistryError, "must not modify governance state"):
            ReviewerRegistry.from_documents(self.catalog, [document])

    def test_require_active_count_fails_when_too_few(self) -> None:
        registry = ReviewerRegistry.from_documents(
            self.catalog,
            [self.reviewer("reviewer-1", status="paused")],
        )

        with self.assertRaisesRegex(ReviewerRegistryError, "Need at least 1 active reviewers"):
            registry.require_active_count(1)


if __name__ == "__main__":
    unittest.main()
