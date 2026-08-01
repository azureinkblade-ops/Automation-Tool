"""Local reviewer registry for Hermes governance agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import SchemaCatalog, SchemaValidationError


class ReviewerRegistryError(ValueError):
    """Raised when reviewer registry configuration is invalid."""


@dataclass(frozen=True)
class ReviewerAgent:
    agent_id: str
    display_name: str
    model_id: str
    status: str
    allowed_tools: tuple[str, ...]
    denied_tools: tuple[str, ...]
    document: dict[str, Any]


class ReviewerRegistry:
    """Validate and query local reviewer agent records."""

    def __init__(self, catalog: SchemaCatalog, reviewers: list[ReviewerAgent]) -> None:
        self.catalog = catalog
        self.reviewers = tuple(reviewers)
        self._by_id = {reviewer.agent_id: reviewer for reviewer in reviewers}

    @classmethod
    def from_documents(
        cls,
        catalog: SchemaCatalog,
        documents: list[dict[str, Any]],
    ) -> "ReviewerRegistry":
        reviewers: list[ReviewerAgent] = []
        seen: set[str] = set()

        for document in documents:
            try:
                catalog.validate("hermes.agent", document)
            except SchemaValidationError as exc:
                raise ReviewerRegistryError(str(exc)) from exc

            agent_id = str(document["agent_id"])
            if agent_id in seen:
                raise ReviewerRegistryError(f"Duplicate reviewer agent_id: {agent_id}")
            seen.add(agent_id)

            cls._validate_reviewer_authority(document)
            reviewers.append(_reviewer_from_document(document))

        return cls(catalog, reviewers)

    @classmethod
    def load(
        cls,
        catalog: SchemaCatalog,
        path: Path | str,
    ) -> "ReviewerRegistry":
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReviewerRegistryError(f"Reviewer registry is not valid JSON: {source}") from exc

        if isinstance(data, dict):
            documents = data.get("reviewers")
        else:
            documents = data
        if not isinstance(documents, list):
            raise ReviewerRegistryError("Reviewer registry must be a list or contain reviewers list")
        if not all(isinstance(item, dict) for item in documents):
            raise ReviewerRegistryError("Every reviewer registry item must be an object")
        return cls.from_documents(catalog, documents)

    def get(self, agent_id: str) -> ReviewerAgent:
        try:
            return self._by_id[agent_id]
        except KeyError as exc:
            raise ReviewerRegistryError(f"Unknown reviewer agent_id: {agent_id}") from exc

    def active_reviewers(self) -> list[ReviewerAgent]:
        return [reviewer for reviewer in self.reviewers if reviewer.status == "active"]

    def require_active_count(self, minimum: int) -> list[ReviewerAgent]:
        active = self.active_reviewers()
        if len(active) < minimum:
            raise ReviewerRegistryError(
                f"Need at least {minimum} active reviewers; found {len(active)}"
            )
        return active

    @staticmethod
    def _validate_reviewer_authority(document: dict[str, Any]) -> None:
        agent_id = str(document.get("agent_id", "<unknown>"))
        if document.get("role") != "reviewer":
            raise ReviewerRegistryError(f"Reviewer {agent_id} must use role reviewer")

        authority = document.get("authority")
        if not isinstance(authority, dict):
            raise ReviewerRegistryError(f"Reviewer {agent_id} authority must be an object")

        if authority.get("can_review") is not True:
            raise ReviewerRegistryError(f"Reviewer {agent_id} must have can_review true")
        if authority.get("can_modify_governance_state") is not False:
            raise ReviewerRegistryError(
                f"Reviewer {agent_id} must not modify governance state"
            )
        if authority.get("can_authorize_execution") is not False:
            raise ReviewerRegistryError(
                f"Reviewer {agent_id} must not authorize execution"
            )
        if authority.get("can_execute") is not False:
            raise ReviewerRegistryError(f"Reviewer {agent_id} must not execute")


def _reviewer_from_document(document: dict[str, Any]) -> ReviewerAgent:
    return ReviewerAgent(
        agent_id=str(document["agent_id"]),
        display_name=str(document["display_name"]),
        model_id=str(document["model_id"]),
        status=str(document["status"]),
        allowed_tools=tuple(document.get("allowed_tools") or []),
        denied_tools=tuple(document.get("denied_tools") or []),
        document=document,
    )
