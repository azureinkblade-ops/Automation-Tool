"""Deterministic ownership for isolated governed-proof runtime directories."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_NAMESPACE_CONTRACT_VERSION = "hermes-runtime-namespace/v1"
RUNTIME_NAMESPACE_MANIFEST = "runtime-owner.json"
HISTORICAL_ORIGINAL_R12E_ID = "ea4d4f-r12e-original"
HISTORICAL_R4_ID = "ea4d4f-r12e-r4"
_HISTORICAL_NAMES = {
    HISTORICAL_ORIGINAL_R12E_ID: "r12e",
    HISTORICAL_R4_ID: "r12e-r4",
}
_IDENTITY = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,126}[a-z0-9])?$")
_GIT_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class RuntimeNamespaceError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeNamespaceOwner:
    proof_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.proof_identity, str) or not _IDENTITY.fullmatch(
            self.proof_identity
        ) or ".." in self.proof_identity:
            raise RuntimeNamespaceError("proof identity is not canonical")
        if self.proof_identity in _HISTORICAL_NAMES:
            raise RuntimeNamespaceError("historical proof identity is read-only")

    def material(self) -> dict[str, str]:
        return {
            "contract_version": RUNTIME_NAMESPACE_CONTRACT_VERSION,
            "owner_type": "governed-qualification-proof",
            "proof_identity": self.proof_identity,
        }

    @property
    def owner_hash(self) -> str:
        return _hash(self.material())


@dataclass(frozen=True)
class RuntimeNamespaceReservation:
    path: Path
    manifest_path: Path
    owner_hash: str
    source_binding: str
    replayed: bool


def historical_runtime_namespace(runtime_root: str | Path, proof_identity: str) -> Path:
    try:
        name = _HISTORICAL_NAMES[proof_identity]
    except (KeyError, TypeError) as exc:
        raise RuntimeNamespaceError("unknown historical proof identity") from exc
    return _within_root(runtime_root, Path(runtime_root) / name)


def runtime_namespace_path(
    runtime_root: str | Path, owner: RuntimeNamespaceOwner,
) -> Path:
    if not isinstance(owner, RuntimeNamespaceOwner):
        raise RuntimeNamespaceError("closed RuntimeNamespaceOwner is required")
    name = f"proof-{owner.owner_hash[:24]}"
    return _within_root(runtime_root, Path(runtime_root) / name)


def _within_root(runtime_root: str | Path, path: Path) -> Path:
    root = Path(runtime_root).resolve()
    candidate = path.resolve()
    if candidate == root or root not in candidate.parents:
        raise RuntimeNamespaceError("runtime namespace escapes trusted root")
    return candidate


def _manifest(owner: RuntimeNamespaceOwner, source_binding: str, name: str) -> dict[str, str]:
    if not isinstance(source_binding, str) or not _GIT_OBJECT_ID.fullmatch(source_binding):
        raise RuntimeNamespaceError("source binding must be a canonical Git object ID")
    return {
        "artifact_type": "hermes.runtime_namespace_owner",
        "artifact_version": "1",
        "contract_version": RUNTIME_NAMESPACE_CONTRACT_VERSION,
        "namespace_name": name,
        "owner_hash": owner.owner_hash,
        "owner_type": "governed-qualification-proof",
        "proof_identity": owner.proof_identity,
        "source_binding": source_binding,
    }


def reserve_runtime_namespace(
    runtime_root: str | Path,
    owner: RuntimeNamespaceOwner,
    *,
    source_binding: str,
) -> RuntimeNamespaceReservation:
    path = runtime_namespace_path(runtime_root, owner)
    expected = _manifest(owner, source_binding, path.name)
    manifest_path = path / RUNTIME_NAMESPACE_MANIFEST
    if path.exists():
        if not path.is_dir() or not manifest_path.is_file():
            raise RuntimeNamespaceError("runtime namespace ownership is unknown")
        try:
            actual = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeNamespaceError("runtime namespace manifest is unreadable") from exc
        if actual != expected:
            raise RuntimeNamespaceError("runtime namespace is owned by different material")
        return RuntimeNamespaceReservation(
            path, manifest_path, owner.owner_hash, source_binding, True,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
        with manifest_path.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(expected) + "\n")
    except FileExistsError as exc:
        raise RuntimeNamespaceError("runtime namespace creation collided") from exc
    return RuntimeNamespaceReservation(
        path, manifest_path, owner.owner_hash, source_binding, False,
    )
