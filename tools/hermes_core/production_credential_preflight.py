"""Local-only credential readiness checks for qualified production receivers.

Readiness is structural only. This module never authenticates, launches a
receiver, issues authority, binds an executor, mutates credentials, or returns
credential material.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


LOCAL_AUTH_STATE_REFERENCE = "LOCAL_AUTH_STATE_REFERENCE"
ALLOWED_CREDENTIAL_SOURCE_TYPES = frozenset({LOCAL_AUTH_STATE_REFERENCE})
QUALIFIED_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})

KILO_TRANSPORT_ID = "d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd"
KILO_MODEL_BINDING_ID = "b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544"
OPENCODE_TRANSPORT_ID = "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f"
OPENCODE_MODEL_BINDING_ID = "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371"

FAILURE_CODES = frozenset(
    {
        "CREDENTIAL_REFERENCE_MISSING",
        "CREDENTIAL_SOURCE_UNSUPPORTED",
        "CREDENTIAL_SOURCE_UNREADABLE",
        "CREDENTIAL_REFERENCE_MALFORMED",
        "CREDENTIAL_VALUE_ABSENT",
        "RECEIVER_CONFIG_MISMATCH",
        "PROVIDER_CONFIG_MISMATCH",
        "MODEL_BINDING_MISMATCH",
        "TRANSPORT_BINDING_MISMATCH",
        "UNQUALIFIED_RECEIVER",
        "SECRET_LITERAL_FORBIDDEN",
        "PREFLIGHT_INTERNAL_ERROR",
    }
)

_FORBIDDEN_LITERAL_FIELDS = frozenset(
    {
        "api_key",
        "credential",
        "credential_value",
        "password",
        "secret",
        "token",
    }
)
_ALLOWED_CONFIG_FIELDS = frozenset(
    {
        "receiver_id",
        "credential_receiver_id",
        "provider_id",
        "config_identity",
        "credential_source_type",
        "credential_reference",
        "transport_contract_id",
        "model_binding_id",
        "task_text",
    }
)
_SECRET_FIELD_MARKERS = ("api_key", "authorization", "credential", "password", "secret", "token")


@dataclass(frozen=True)
class ReceiverCredentialPolicy:
    receiver_id: str
    provider_id: str
    config_identity: str
    credential_source_type: str
    credential_reference: str
    credential_reference_id: str
    allowed_root: str
    transport_contract_id: str
    model_binding_id: str


@dataclass(frozen=True)
class CredentialReadinessResult:
    receiver_id: str
    config_identity_reference: str
    credential_source_type: str
    credential_reference_id: str
    credential_presence: str
    structural_readiness: str
    binding_consistency: str
    failure_code: str | None
    ready: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "receiver_id": self.receiver_id,
            "config_identity_reference": self.config_identity_reference,
            "credential_source_type": self.credential_source_type,
            "credential_reference_id": self.credential_reference_id,
            "credential_presence": self.credential_presence,
            "structural_readiness": self.structural_readiness,
            "binding_consistency": self.binding_consistency,
            "failure_code": self.failure_code,
            "ready": self.ready,
        }


def default_credential_policies() -> dict[str, ReceiverCredentialPolicy]:
    """Return declarative references without reading either auth-state file."""
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", r"C:\Users\David\AppData\Local")
    )
    runtime_root = local_app_data / "Hermes" / "runtime" / "ea4e"
    kilo_root = runtime_root / "kilo" / "home"
    opencode_root = runtime_root / "opencode" / "home"
    return {
        "kilo-cli-agent": ReceiverCredentialPolicy(
            receiver_id="kilo-cli-agent",
            provider_id="kilo",
            config_identity="hermes-ea4e-kilo-local-auth-state",
            credential_source_type=LOCAL_AUTH_STATE_REFERENCE,
            credential_reference=str(kilo_root / ".local" / "share" / "kilo" / "kilo.db"),
            credential_reference_id="kilo-local-auth-state",
            allowed_root=str(kilo_root),
            transport_contract_id=KILO_TRANSPORT_ID,
            model_binding_id=KILO_MODEL_BINDING_ID,
        ),
        "opencode-cli-agent": ReceiverCredentialPolicy(
            receiver_id="opencode-cli-agent",
            provider_id="opencode",
            config_identity="hermes-ea4e-opencode-local-auth-state",
            credential_source_type=LOCAL_AUTH_STATE_REFERENCE,
            credential_reference=str(
                opencode_root / ".local" / "share" / "opencode" / "opencode.db"
            ),
            credential_reference_id="opencode-local-auth-state",
            allowed_root=str(opencode_root),
            transport_contract_id=OPENCODE_TRANSPORT_ID,
            model_binding_id=OPENCODE_MODEL_BINDING_ID,
        ),
    }


class ProductionCredentialReadinessPreflight:
    """Evaluate an explicit receiver configuration without live validation."""

    def __init__(
        self, policies: Mapping[str, ReceiverCredentialPolicy] | None = None
    ) -> None:
        self._policies = dict(
            default_credential_policies() if policies is None else policies
        )

    def check(self, config: Mapping[str, object] | None) -> CredentialReadinessResult:
        if not isinstance(config, Mapping):
            return self._deny("", "PREFLIGHT_INTERNAL_ERROR")
        receiver_id = self._text(config.get("receiver_id"))
        config_fields = {
            str(field).strip().lower() for field in config if isinstance(field, str)
        }
        if config_fields & _FORBIDDEN_LITERAL_FIELDS:
            return self._deny(receiver_id, "SECRET_LITERAL_FORBIDDEN")
        unknown_fields = config_fields - _ALLOWED_CONFIG_FIELDS
        if any(
            marker in field
            for field in unknown_fields
            for marker in _SECRET_FIELD_MARKERS
        ):
            return self._deny(receiver_id, "SECRET_LITERAL_FORBIDDEN")
        if unknown_fields:
            return self._deny(receiver_id, "PREFLIGHT_INTERNAL_ERROR")
        if receiver_id not in QUALIFIED_RECEIVERS or receiver_id not in self._policies:
            return self._deny(receiver_id, "UNQUALIFIED_RECEIVER")

        policy = self._policies[receiver_id]
        credential_receiver_id = self._text(config.get("credential_receiver_id"))
        if credential_receiver_id != receiver_id:
            return self._deny(receiver_id, "RECEIVER_CONFIG_MISMATCH", policy)
        if self._text(config.get("provider_id")) != policy.provider_id:
            return self._deny(receiver_id, "PROVIDER_CONFIG_MISMATCH", policy)
        if self._text(config.get("config_identity")) != policy.config_identity:
            return self._deny(receiver_id, "RECEIVER_CONFIG_MISMATCH", policy)
        if self._text(config.get("transport_contract_id")) != policy.transport_contract_id:
            return self._deny(receiver_id, "TRANSPORT_BINDING_MISMATCH", policy)
        if self._text(config.get("model_binding_id")) != policy.model_binding_id:
            return self._deny(receiver_id, "MODEL_BINDING_MISMATCH", policy)

        source_type = self._text(config.get("credential_source_type"))
        if not source_type:
            return self._deny(receiver_id, "CREDENTIAL_REFERENCE_MISSING", policy)
        if source_type not in ALLOWED_CREDENTIAL_SOURCE_TYPES:
            return self._deny(receiver_id, "CREDENTIAL_SOURCE_UNSUPPORTED", policy)

        reference = self._text(config.get("credential_reference"))
        if not reference:
            return self._deny(receiver_id, "CREDENTIAL_REFERENCE_MISSING", policy)
        if reference != policy.credential_reference:
            return self._deny(receiver_id, "CREDENTIAL_REFERENCE_MALFORMED", policy)

        path = Path(reference)
        if not self._safe_file_reference(path, Path(policy.allowed_root)):
            return self._deny(receiver_id, "CREDENTIAL_REFERENCE_MALFORMED", policy)
        try:
            if not path.exists() or not path.is_file():
                return self._deny(
                    receiver_id,
                    "CREDENTIAL_VALUE_ABSENT",
                    policy,
                    presence="MISSING",
                )
            with path.open("rb") as source:
                present = bool(source.read(1))
        except (OSError, ValueError):
            return self._deny(
                receiver_id,
                "CREDENTIAL_SOURCE_UNREADABLE",
                policy,
                presence="PRESENT",
            )
        if not present:
            return self._deny(
                receiver_id,
                "CREDENTIAL_VALUE_ABSENT",
                policy,
                presence="MISSING",
            )
        return CredentialReadinessResult(
            receiver_id=receiver_id,
            config_identity_reference=policy.config_identity,
            credential_source_type=policy.credential_source_type,
            credential_reference_id=policy.credential_reference_id,
            credential_presence="PRESENT",
            structural_readiness="READY",
            binding_consistency="MATCH",
            failure_code=None,
            ready=True,
        )

    @staticmethod
    def _text(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _safe_file_reference(path: Path, allowed_root: Path) -> bool:
        if not path.is_absolute():
            return False
        try:
            path.resolve(strict=False).relative_to(allowed_root.resolve(strict=False))
        except (OSError, ValueError):
            return False
        return True

    @staticmethod
    def _deny(
        receiver_id: str,
        failure_code: str,
        policy: ReceiverCredentialPolicy | None = None,
        *,
        presence: str = "UNKNOWN",
    ) -> CredentialReadinessResult:
        return CredentialReadinessResult(
            receiver_id=receiver_id,
            config_identity_reference=policy.config_identity if policy else "",
            credential_source_type=policy.credential_source_type if policy else "",
            credential_reference_id=policy.credential_reference_id if policy else "",
            credential_presence=presence,
            structural_readiness="NOT_READY",
            binding_consistency=(
                "MISMATCH"
                if failure_code
                in {
                    "RECEIVER_CONFIG_MISMATCH",
                    "PROVIDER_CONFIG_MISMATCH",
                    "MODEL_BINDING_MISMATCH",
                    "TRANSPORT_BINDING_MISMATCH",
                }
                else "UNKNOWN"
            ),
            failure_code=failure_code,
            ready=False,
        )
