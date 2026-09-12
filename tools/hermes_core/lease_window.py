"""Finite, immutable lease windows for governed live-proof attempts."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


LEASE_WINDOW_POLICY_VERSION = "hermes-live-proof-lease-window/v1"
LEASE_WINDOW_MANIFEST = "lease-window.json"
QUALIFIED_TTL_SECONDS = 300
MAX_TTL_SECONDS = 3600
EXPIRY_SEMANTICS = "valid-iff-issued-at-lte-now-lt-expires-at"
CLOCK_SOURCE = "utc-wall-clock"
CLOCK_SKEW_GRACE_SECONDS = 0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LeaseWindowError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _format_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise LeaseWindowError("clock must return an offset-aware datetime")
    value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LeaseWindowError(f"{field} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LeaseWindowError(f"{field} must be canonical UTC") from exc
    if _format_utc(parsed) != value:
        raise LeaseWindowError(f"{field} must use whole-second canonical UTC")
    return parsed


def _clock_value(clock: Callable[[], datetime] | None) -> datetime:
    return datetime.now(timezone.utc) if clock is None else clock()


@dataclass(frozen=True)
class LeaseWindowPolicy:
    ttl_seconds: int = QUALIFIED_TTL_SECONDS

    def __post_init__(self) -> None:
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, int)
            or self.ttl_seconds <= 0
            or self.ttl_seconds > MAX_TTL_SECONDS
        ):
            raise LeaseWindowError("lease TTL must be a finite bounded integer")

    def material(self) -> dict[str, Any]:
        return lease_window_policy_material(ttl_seconds=self.ttl_seconds)

    @property
    def policy_id(self) -> str:
        return lease_window_policy_id(self.material())


def lease_window_policy_material(
    *,
    ttl_seconds: int = QUALIFIED_TTL_SECONDS,
    expiry_semantics: str = EXPIRY_SEMANTICS,
) -> dict[str, Any]:
    return {
        "policy_version": LEASE_WINDOW_POLICY_VERSION,
        "ttl_seconds": ttl_seconds,
        "maximum_ttl_seconds": MAX_TTL_SECONDS,
        "clock_source": CLOCK_SOURCE,
        "canonical_time": "UTC-RFC3339-whole-seconds-Z",
        "expiry_semantics": expiry_semantics,
        "clock_skew_grace_seconds": CLOCK_SKEW_GRACE_SECONDS,
        "auto_renewal": False,
    }


def lease_window_policy_id(material: dict[str, Any] | None = None) -> str:
    return _hash(lease_window_policy_material() if material is None else material)


QUALIFIED_LEASE_WINDOW_POLICY = LeaseWindowPolicy()
QUALIFIED_LEASE_WINDOW_POLICY_ID = QUALIFIED_LEASE_WINDOW_POLICY.policy_id


@dataclass(frozen=True)
class AttemptLeaseWindow:
    policy_id: str
    namespace_owner_hash: str
    issued_at: str
    expires_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not _SHA256.fullmatch(self.policy_id):
            raise LeaseWindowError("lease policy identity is invalid")
        if (
            not isinstance(self.namespace_owner_hash, str)
            or not _SHA256.fullmatch(self.namespace_owner_hash)
        ):
            raise LeaseWindowError("namespace owner hash is invalid")
        issued = _parse_utc(self.issued_at, "issued_at")
        expires = _parse_utc(self.expires_at, "expires_at")
        if expires <= issued:
            raise LeaseWindowError("lease expiration must be after issuance")

    def material(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "namespace_owner_hash": self.namespace_owner_hash,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @property
    def artifact_hash(self) -> str:
        return _hash(self.material())


@dataclass(frozen=True)
class LeaseWindowReservation:
    window: AttemptLeaseWindow
    manifest_path: Path
    replayed: bool


def issue_attempt_lease_window(
    policy: LeaseWindowPolicy,
    namespace_owner_hash: str,
    *,
    clock: Callable[[], datetime] | None = None,
) -> AttemptLeaseWindow:
    if not isinstance(policy, LeaseWindowPolicy):
        raise LeaseWindowError("closed lease-window policy is required")
    issued = _parse_utc(_format_utc(_clock_value(clock)), "issued_at")
    expires = issued + timedelta(seconds=policy.ttl_seconds)
    return AttemptLeaseWindow(
        policy_id=policy.policy_id,
        namespace_owner_hash=namespace_owner_hash,
        issued_at=_format_utc(issued),
        expires_at=_format_utc(expires),
    )


def lease_event_time(window: AttemptLeaseWindow, offset_seconds: int) -> str:
    if isinstance(offset_seconds, bool) or not isinstance(offset_seconds, int):
        raise LeaseWindowError("event offset must be an integer")
    issued = _parse_utc(window.issued_at, "issued_at")
    expires = _parse_utc(window.expires_at, "expires_at")
    event = issued + timedelta(seconds=offset_seconds)
    if event < issued or event >= expires:
        raise LeaseWindowError("event time must remain inside the lease window")
    return _format_utc(event)


def is_lease_valid(
    window: AttemptLeaseWindow,
    *,
    clock: Callable[[], datetime] | None = None,
) -> bool:
    now = _clock_value(clock)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise LeaseWindowError("clock must return an offset-aware datetime")
    now = now.astimezone(timezone.utc)
    issued = _parse_utc(window.issued_at, "issued_at")
    expires = _parse_utc(window.expires_at, "expires_at")
    return issued <= now < expires


def require_lease_valid(
    window: AttemptLeaseWindow,
    *,
    clock: Callable[[], datetime] | None = None,
) -> None:
    if not is_lease_valid(window, clock=clock):
        raise LeaseWindowError("attempt lease window is not currently valid")


def _manifest(window: AttemptLeaseWindow, policy: LeaseWindowPolicy) -> dict[str, Any]:
    return {
        "artifact_type": "hermes.attempt_lease_window",
        "artifact_version": "1",
        "policy": policy.material(),
        **window.material(),
        "artifact_hash": window.artifact_hash,
    }


def _load_manifest(
    manifest_path: Path,
    policy: LeaseWindowPolicy,
    namespace_owner_hash: str,
) -> AttemptLeaseWindow:
    try:
        actual = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LeaseWindowError("lease-window manifest is unreadable") from exc
    try:
        window = AttemptLeaseWindow(
            policy_id=actual["policy_id"],
            namespace_owner_hash=actual["namespace_owner_hash"],
            issued_at=actual["issued_at"],
            expires_at=actual["expires_at"],
        )
    except (KeyError, TypeError, LeaseWindowError) as exc:
        raise LeaseWindowError("lease-window manifest is invalid") from exc
    expected = _manifest(window, policy)
    if actual != expected:
        raise LeaseWindowError("lease-window manifest differs from qualified material")
    if window.policy_id != policy.policy_id:
        raise LeaseWindowError("lease-window policy identity changed")
    if window.namespace_owner_hash != namespace_owner_hash:
        raise LeaseWindowError("lease-window namespace owner changed")
    issued = _parse_utc(window.issued_at, "issued_at")
    expires = _parse_utc(window.expires_at, "expires_at")
    if expires - issued != timedelta(seconds=policy.ttl_seconds):
        raise LeaseWindowError("lease-window TTL differs from qualified policy")
    return window


def load_attempt_lease_window(
    namespace_path: str | Path,
    policy: LeaseWindowPolicy,
    namespace_owner_hash: str,
) -> LeaseWindowReservation:
    manifest_path = Path(namespace_path) / LEASE_WINDOW_MANIFEST
    if not manifest_path.is_file():
        raise LeaseWindowError("attempt lease window has not been issued")
    return LeaseWindowReservation(
        _load_manifest(manifest_path, policy, namespace_owner_hash),
        manifest_path,
        True,
    )


def issue_or_load_attempt_lease_window(
    namespace_path: str | Path,
    policy: LeaseWindowPolicy,
    namespace_owner_hash: str,
    *,
    clock: Callable[[], datetime] | None = None,
) -> LeaseWindowReservation:
    path = Path(namespace_path)
    if not path.is_dir():
        raise LeaseWindowError("owned runtime namespace must exist before lease issuance")
    manifest_path = path / LEASE_WINDOW_MANIFEST
    if manifest_path.exists():
        return load_attempt_lease_window(path, policy, namespace_owner_hash)
    window = issue_attempt_lease_window(policy, namespace_owner_hash, clock=clock)
    try:
        with manifest_path.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(_manifest(window, policy)) + "\n")
    except FileExistsError as exc:
        raise LeaseWindowError("attempt lease-window issuance collided") from exc
    return LeaseWindowReservation(window, manifest_path, False)
