"""Static receiver registry. Bind receiver IDs to trusted adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.receiver_adapter import (
    ReceiverAdapter,
    ReceiverError,
)


class UnknownReceiverError(ReceiverError):
    pass


class DisabledReceiverError(ReceiverError):
    pass


@dataclass(frozen=True)
class ReceiverDescriptor:
    receiver_id: str
    receiver_class: str
    receiver_version: str
    adapter_version: str
    executable_path: str
    expected_sha256: str
    expected_version: str
    transport_contract_id: str
    approval_policy: str
    sandbox_policy: str
    allowed_operations: Sequence[str]
    capabilities: Sequence[str]
    enabled: bool
    registration_source: str
    registration_version: str
    descriptor_hash: str

    def to_canonical_dict(self):
        return {
            "receiver_class": self.receiver_class,
            "receiver_id": self.receiver_id,
            "receiver_version": self.receiver_version,
            "adapter_version": self.adapter_version,
            "executable_path": self.executable_path,
            "expected_sha256": self.expected_sha256,
            "expected_version": self.expected_version,
            "transport_contract_id": self.transport_contract_id,
            "approval_policy": self.approval_policy,
            "sandbox_policy": self.sandbox_policy,
            "allowed_operations": list(self.allowed_operations),
            "capabilities": list(self.capabilities),
            "enabled": self.enabled,
            "registration_source": self.registration_source,
            "registration_version": self.registration_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.descriptor_hash


@dataclass(frozen=True)
class ReceiverRegistry:
    registry_version: str
    registry_hash: str
    receivers: Sequence[ReceiverDescriptor]

    def to_canonical_dict(self):
        return {
            "registry_version": self.registry_version,
            "receivers": [r.to_canonical_dict() for r in self.receivers],
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.registry_hash

    def get_receiver(self, receiver_id: str) -> Optional[ReceiverDescriptor]:
        for r in self.receivers:
            if r.receiver_id == receiver_id:
                return r
        return None

    def get_adapter(self, receiver_id: str) -> ReceiverAdapter:
        desc = self.get_receiver(receiver_id)
        if desc is None:
            raise UnknownReceiverError(f"Unknown: {receiver_id}")
        if not desc.enabled:
            raise DisabledReceiverError(f"Disabled: {receiver_id}")
        return _ADAPTER_FACTORY[receiver_id]()


_ADAPTER_FACTORY: dict[str, type[ReceiverAdapter]] = {}


def register_adapter(receiver_id: str, adapter_cls: type[ReceiverAdapter]) -> None:
    _ADAPTER_FACTORY[receiver_id] = adapter_cls


def build_receiver_descriptor(
    *,
    receiver_id: str,
    receiver_class: str,
    receiver_version: str,
    adapter_version: str,
    executable_path: str,
    expected_sha256: str,
    expected_version: str,
    transport_contract_id: str,
    approval_policy: str,
    sandbox_policy: str,
    allowed_operations: Sequence[str],
    capabilities: Sequence[str],
    enabled: bool,
    registration_source: str,
    registration_version: str,
) -> ReceiverDescriptor:
    d = ReceiverDescriptor(
        receiver_id=receiver_id, receiver_class=receiver_class,
        receiver_version=receiver_version, adapter_version=adapter_version,
        executable_path=executable_path, expected_sha256=expected_sha256,
        expected_version=expected_version, transport_contract_id=transport_contract_id,
        approval_policy=approval_policy, sandbox_policy=sandbox_policy,
        allowed_operations=list(allowed_operations), capabilities=list(capabilities),
        enabled=enabled, registration_source=registration_source,
        registration_version=registration_version, descriptor_hash="",
    )
    h = sha256_payload(d.to_canonical_dict())
    return ReceiverDescriptor(
        receiver_id=d.receiver_id, receiver_class=d.receiver_class,
        receiver_version=d.receiver_version, adapter_version=d.adapter_version,
        executable_path=d.executable_path, expected_sha256=d.expected_sha256,
        expected_version=d.expected_version, transport_contract_id=d.transport_contract_id,
        approval_policy=d.approval_policy, sandbox_policy=d.sandbox_policy,
        allowed_operations=d.allowed_operations, capabilities=d.capabilities,
        enabled=d.enabled, registration_source=d.registration_source,
        registration_version=d.registration_version, descriptor_hash=h,
    )


def build_receiver_registry(
    *, registry_version: str, receivers: Sequence[ReceiverDescriptor],
) -> ReceiverRegistry:
    r = ReceiverRegistry(registry_version=registry_version, registry_hash="", receivers=list(receivers))
    h = sha256_payload(r.to_canonical_dict())
    return ReceiverRegistry(registry_version=r.registry_version, registry_hash=h, receivers=r.receivers)
