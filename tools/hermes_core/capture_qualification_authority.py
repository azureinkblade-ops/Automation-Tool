"""Non-live EA-4E.92BN capture artifact validation; not execution admission."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Mapping


SCHEMA_ID = "hermes.capture-qualification-authorization/v1"
RECEIVER_ID = "opencode-cli-agent"
_ID = re.compile(r"[A-Za-z0-9_:-]{1,128}\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z", re.ASCII)


class CaptureArtifactInvalid(ValueError):
    """Canonical capture artifact or current context does not match."""


@dataclass(frozen=True)
class CaptureQualificationArtifact:
    schema_id: str
    authorization_id: str
    issue_request_id: str
    approval_id: str
    operator_id: str
    run_id: str
    receiver_id: str
    task_sha256: str
    source_commit: str
    executable_sha256: str
    config_sha256: str
    transport_id: str
    model_binding_id: str
    provider_budget_id: str
    issued_at: str
    expires_at: str
    process_start_limit: int
    nonce: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CaptureQualificationArtifact":
        if not isinstance(value, Mapping) or set(value) != {field.name for field in fields(cls)}:
            raise CaptureArtifactInvalid("capture artifact keys do not match v1")
        return cls(**value)

    @classmethod
    def from_canonical_bytes(cls, raw: bytes) -> "CaptureQualificationArtifact":
        if type(raw) is not bytes:
            raise CaptureArtifactInvalid("capture artifact must be bytes")

        def distinct_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result = dict(pairs)
            if len(result) != len(pairs):
                raise CaptureArtifactInvalid("duplicate capture artifact key")
            return result

        try:
            decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=distinct_pairs)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaptureArtifactInvalid("invalid capture artifact JSON") from exc
        artifact = cls.from_mapping(decoded)
        if raw != artifact.canonical_bytes():
            raise CaptureArtifactInvalid("capture artifact is not canonical")
        return artifact

    def __post_init__(self) -> None:
        value = {field.name: getattr(self, field.name) for field in fields(self)}
        if any(type(item) is not str for key, item in value.items() if key != "process_start_limit"):
            raise CaptureArtifactInvalid("capture artifact requires string fields")
        if value["schema_id"] != SCHEMA_ID or value["receiver_id"] != RECEIVER_ID:
            raise CaptureArtifactInvalid("unsupported capture schema or receiver")
        if type(value["process_start_limit"]) is not int or value["process_start_limit"] != 1:
            raise CaptureArtifactInvalid("capture start limit must be integer one")

        identity_fields = (
            "authorization_id", "issue_request_id", "approval_id", "operator_id",
            "run_id", "receiver_id", "provider_budget_id", "nonce",
        )
        if any(_ID.fullmatch(value[key]) is None for key in identity_fields):
            raise CaptureArtifactInvalid("invalid capture identity")
        if len({value[key] for key in identity_fields}) != len(identity_fields):
            raise CaptureArtifactInvalid("capture identities must be distinct")
        if _COMMIT.fullmatch(value["source_commit"]) is None:
            raise CaptureArtifactInvalid("invalid source commit")
        hash_fields = (
            "task_sha256", "executable_sha256", "config_sha256",
            "transport_id", "model_binding_id",
        )
        if any(_HASH.fullmatch(value[key]) is None for key in hash_fields):
            raise CaptureArtifactInvalid("invalid capture hash")
        issued = _parse_time(value["issued_at"])
        expires = _parse_time(value["expires_at"])
        if not issued < expires <= issued + timedelta(minutes=5):
            raise CaptureArtifactInvalid("invalid capture validity window")

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            {field.name: getattr(self, field.name) for field in fields(self)},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def check_current_material(
        self, *, task: bytes, now: str, receiver_id: str,
        source_commit: str, executable_sha256: str, config_sha256: str,
        transport_id: str, model_binding_id: str, provider_budget_id: str,
    ) -> None:
        """Compare observed bytes/identity only; does not issue or consume authority."""
        if type(task) is not bytes or not task or len(task) > 65536:
            raise CaptureArtifactInvalid("invalid capture task bytes")
        if hashlib.sha256(task).hexdigest() != self.task_sha256:
            raise CaptureArtifactInvalid("capture task changed")
        if not _parse_time(self.issued_at) <= _parse_time(now) < _parse_time(self.expires_at):
            raise CaptureArtifactInvalid("capture artifact outside validity window")
        observed = (
            receiver_id, source_commit, executable_sha256, config_sha256,
            transport_id, model_binding_id, provider_budget_id,
        )
        expected = (
            self.receiver_id, self.source_commit, self.executable_sha256,
            self.config_sha256, self.transport_id, self.model_binding_id,
            self.provider_budget_id,
        )
        if observed != expected:
            raise CaptureArtifactInvalid("current capture identity changed")


def _parse_time(value: str) -> datetime:
    if _TIME.fullmatch(value) is None:
        raise CaptureArtifactInvalid("capture timestamp must be UTC seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CaptureArtifactInvalid("invalid capture timestamp") from exc
