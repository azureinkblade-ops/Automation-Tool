"""Isolated, non-live persistence for externally issued capture artifacts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from tools.hermes_core.capture_qualification_authority import (
    CaptureQualificationArtifact, _parse_time,
)
from tools.hermes_core.hashing import sha256_payload


STORE_SCHEMA = "hermes.capture-qualification-store/v1"
ANCHOR_SCHEMA = "hermes.capture-qualification-anchor/v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class CaptureStoreError(RuntimeError):
    pass


class CaptureStoreIntegrityError(CaptureStoreError):
    pass


class CaptureStoreConflict(CaptureStoreError):
    pass


@dataclass(frozen=True)
class CaptureState:
    artifact: CaptureQualificationArtifact
    consumed: bool
    consumed_at: str | None
    cancelled_at: str | None
    revoked_at: str | None


class CaptureQualificationStore:
    """No issuer or process capability; caller supplies an externally pinned epoch."""

    def __init__(
        self, path: Path, *, anchor_path: Path,
        expected_instance_id: str, expected_generation: int,
    ) -> None:
        self.path = Path(path).resolve()
        self.anchor_path = Path(anchor_path).resolve()
        self.expected_instance_id = expected_instance_id
        self.generation = expected_generation
        if (
            self.path == self.anchor_path or not self.path.is_file()
            or not self.anchor_path.is_file() or not expected_instance_id
            or type(expected_generation) is not int or expected_generation < 1
        ):
            raise CaptureStoreIntegrityError("missing or invalid pinned capture store")
        with self._connection() as connection:
            self._verify(connection)

    @classmethod
    def initialize(
        cls, path: Path, *, anchor_path: Path, instance_id: str,
    ) -> "CaptureQualificationStore":
        """Explicit one-time provisioning; never repairs a partial store."""
        path = Path(path).resolve()
        anchor_path = Path(anchor_path).resolve()
        if path == anchor_path or not instance_id or path.exists() or anchor_path.exists():
            raise CaptureStoreConflict("capture store already exists or identity invalid")
        path.parent.mkdir(parents=True, exist_ok=True)
        anchor_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE capture_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                "schema_id TEXT NOT NULL, instance_id TEXT NOT NULL, generation INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO capture_meta VALUES (1, ?, ?, 1)", (STORE_SCHEMA, instance_id)
            )
            connection.execute(
                "CREATE TABLE capture_authorizations ("
                "authorization_id TEXT PRIMARY KEY, issue_request_id TEXT UNIQUE NOT NULL, "
                "issue_request_hash TEXT NOT NULL, artifact BLOB NOT NULL, "
                "artifact_hash TEXT NOT NULL, state TEXT NOT NULL, consumed_at TEXT, "
                "cancelled_at TEXT, revoked_at TEXT, record_hash TEXT NOT NULL)"
            )
            connection.execute("COMMIT")
        finally:
            connection.close()
        cls._write_anchor(anchor_path, instance_id, 1)
        return cls(
            path, anchor_path=anchor_path,
            expected_instance_id=instance_id, expected_generation=1,
        )

    @contextmanager
    def _connection(self):
        connection = None
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw", uri=True,
                isolation_level=None, timeout=1.0,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 1000")
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        except sqlite3.Error as exc:
            raise CaptureStoreError(str(exc)) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _anchor_payload(instance_id: str, generation: int) -> dict[str, object]:
        material = {
            "schema_id": ANCHOR_SCHEMA, "instance_id": instance_id,
            "generation": generation,
        }
        return {**material, "anchor_hash": sha256_payload(material)}

    @classmethod
    def _write_anchor(cls, path: Path, instance_id: str, generation: int) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = cls._anchor_payload(instance_id, generation)
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise CaptureStoreError("capture anchor publication failed") from exc

    def _verify(self, connection: sqlite3.Connection) -> int:
        try:
            row = connection.execute(
                "SELECT schema_id, instance_id, generation FROM capture_meta WHERE singleton=1"
            ).fetchone()
            anchor = json.loads(self.anchor_path.read_text(encoding="utf-8"))
        except (sqlite3.Error, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CaptureStoreIntegrityError("capture store or anchor unreadable") from exc
        if row is None or not isinstance(anchor, dict) or set(anchor) != {
            "schema_id", "instance_id", "generation", "anchor_hash",
        }:
            raise CaptureStoreIntegrityError("capture store or anchor malformed")
        generation = row["generation"]
        if (
            row["schema_id"] != STORE_SCHEMA or anchor["schema_id"] != ANCHOR_SCHEMA
            or type(generation) is not int or generation < 1
            or type(anchor["generation"]) is not int
            or anchor != self._anchor_payload(anchor["instance_id"], anchor["generation"])
            or row["instance_id"] != self.expected_instance_id
            or anchor["instance_id"] != self.expected_instance_id
            or generation != anchor["generation"]
            or generation != self.generation
        ):
            raise CaptureStoreIntegrityError("capture store identity or generation mismatch")
        return generation

    @staticmethod
    def _record_material(
        issue_request_id: str, issue_request_hash: str, artifact_hash: str,
        state: str, consumed_at: str | None, cancelled_at: str | None,
        revoked_at: str | None,
    ) -> dict[str, object]:
        return dict(
            issue_request_id=issue_request_id, issue_request_hash=issue_request_hash,
            artifact_hash=artifact_hash, state=state, consumed_at=consumed_at,
            cancelled_at=cancelled_at, revoked_at=revoked_at,
        )

    def _state(self, row: sqlite3.Row) -> CaptureState:
        try:
            artifact = CaptureQualificationArtifact.from_canonical_bytes(row["artifact"])
            material = self._record_material(
                row["issue_request_id"], row["issue_request_hash"],
                row["artifact_hash"], row["state"], row["consumed_at"],
                row["cancelled_at"], row["revoked_at"],
            )
            if (
                artifact.authorization_id != row["authorization_id"]
                or artifact.issue_request_id != row["issue_request_id"]
                or artifact.sha256() != row["artifact_hash"]
                or _HASH.fullmatch(row["issue_request_hash"]) is None
                or row["record_hash"] != sha256_payload(material)
                or row["state"] not in ("ISSUED", "CONSUMED")
                or (row["state"] == "CONSUMED") != (row["consumed_at"] is not None)
            ):
                raise CaptureStoreIntegrityError("capture record integrity mismatch")
            for key in ("consumed_at", "cancelled_at", "revoked_at"):
                if row[key] is not None:
                    _parse_time(row[key])
        except (ValueError, TypeError, KeyError) as exc:
            raise CaptureStoreIntegrityError("capture record malformed") from exc
        return CaptureState(
            artifact, row["state"] == "CONSUMED", row["consumed_at"],
            row["cancelled_at"], row["revoked_at"],
        )

    def _advance(self, connection: sqlite3.Connection, generation: int) -> int:
        cursor = connection.execute(
            "UPDATE capture_meta SET generation=? WHERE singleton=1 AND generation=?",
            (generation + 1, generation),
        )
        if cursor.rowcount != 1:
            raise CaptureStoreIntegrityError("capture generation changed during update")
        return generation + 1

    def _publish(self, generation: int) -> None:
        self._write_anchor(self.anchor_path, self.expected_instance_id, generation)
        self.generation = generation

    def _after_commit_before_anchor(self) -> None:
        """Fault-injection seam; an interrupted publication must fail closed."""

    def persist_issued(
        self, artifact: CaptureQualificationArtifact, *, issue_request_hash: str,
    ) -> bool:
        """Persist supplied external material; does not approve or issue authority."""
        if type(issue_request_hash) is not str or _HASH.fullmatch(issue_request_hash) is None:
            raise CaptureStoreIntegrityError("invalid external issue request hash")
        raw = artifact.canonical_bytes()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            generation = self._verify(connection)
            rows = connection.execute(
                "SELECT * FROM capture_authorizations WHERE authorization_id=? OR issue_request_id=?",
                (artifact.authorization_id, artifact.issue_request_id),
            ).fetchall()
            if rows:
                if len(rows) != 1:
                    raise CaptureStoreConflict("capture authorization identities collide")
                state = self._state(rows[0])
                if state.artifact != artifact or rows[0]["issue_request_hash"] != issue_request_hash:
                    raise CaptureStoreConflict("capture issue replay changed material")
                connection.execute("COMMIT")
                return True
            material = self._record_material(
                artifact.issue_request_id, issue_request_hash, artifact.sha256(),
                "ISSUED", None, None, None,
            )
            connection.execute(
                "INSERT INTO capture_authorizations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact.authorization_id, artifact.issue_request_id,
                 issue_request_hash, raw, artifact.sha256(), "ISSUED", None,
                 None, None, sha256_payload(material)),
            )
            next_generation = self._advance(connection, generation)
            connection.execute("COMMIT")
            self._after_commit_before_anchor()
            self._publish(next_generation)
            return False

    def inspect(self, authorization_id: str) -> CaptureState:
        with self._connection() as connection:
            self._verify(connection)
            row = connection.execute(
                "SELECT * FROM capture_authorizations WHERE authorization_id=?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                raise CaptureStoreIntegrityError("capture authorization absent")
            return self._state(row)

    def claim(
        self, artifact: CaptureQualificationArtifact, *, task: bytes, now: str,
        receiver_id: str, source_commit: str, executable_sha256: str,
        config_sha256: str, transport_id: str, model_binding_id: str,
        provider_budget_id: str,
    ) -> bool:
        """Consume one start credit; True only after durable anchor publication."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            generation = self._verify(connection)
            row = connection.execute(
                "SELECT * FROM capture_authorizations WHERE authorization_id=?",
                (artifact.authorization_id,),
            ).fetchone()
            if row is None:
                return False
            state = self._state(row)
            if state.artifact != artifact or state.consumed or state.cancelled_at or state.revoked_at:
                return False
            artifact.check_current_material(
                task=task, now=now, receiver_id=receiver_id,
                source_commit=source_commit, executable_sha256=executable_sha256,
                config_sha256=config_sha256, transport_id=transport_id,
                model_binding_id=model_binding_id, provider_budget_id=provider_budget_id,
            )
            material = self._record_material(
                artifact.issue_request_id, row["issue_request_hash"],
                artifact.sha256(), "CONSUMED", now, None, None,
            )
            cursor = connection.execute(
                "UPDATE capture_authorizations SET state='CONSUMED', consumed_at=?, "
                "record_hash=? WHERE authorization_id=? AND state='ISSUED'",
                (now, sha256_payload(material), artifact.authorization_id),
            )
            if cursor.rowcount != 1:
                return False
            next_generation = self._advance(connection, generation)
            connection.execute("COMMIT")
            self._after_commit_before_anchor()
            self._publish(next_generation)
            return True

    def cancel(self, authorization_id: str, *, at: str) -> None:
        self._mark(authorization_id, at=at, column="cancelled_at")

    def revoke(self, authorization_id: str, *, at: str) -> None:
        self._mark(authorization_id, at=at, column="revoked_at")

    def _mark(self, authorization_id: str, *, at: str, column: str) -> None:
        _parse_time(at)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            generation = self._verify(connection)
            row = connection.execute(
                "SELECT * FROM capture_authorizations WHERE authorization_id=?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                raise CaptureStoreIntegrityError("capture authorization absent")
            state = self._state(row)
            if getattr(state, column) is not None:
                connection.execute("COMMIT")
                return
            cancelled = at if column == "cancelled_at" else state.cancelled_at
            revoked = at if column == "revoked_at" else state.revoked_at
            material = self._record_material(
                state.artifact.issue_request_id, row["issue_request_hash"],
                state.artifact.sha256(), row["state"], state.consumed_at,
                cancelled, revoked,
            )
            connection.execute(
                f"UPDATE capture_authorizations SET {column}=?, record_hash=? "
                "WHERE authorization_id=?",
                (at, sha256_payload(material), authorization_id),
            )
            next_generation = self._advance(connection, generation)
            connection.execute("COMMIT")
            self._after_commit_before_anchor()
            self._publish(next_generation)
