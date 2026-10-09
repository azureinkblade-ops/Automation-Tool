"""Isolated durable, one-send claim store for non-live EA-4E qualification."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import uuid

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.kilo_send_claim import (
    KiloSendClaimDenied,
    candidate_send_claim_hash,
    canonical_send_claim_material,
)


SCHEMA = "hermes.ea4e-kilo-send-store/v1"
ANCHOR_SCHEMA = "hermes.ea4e-kilo-send-anchor/v1"
CHAIN_SCHEMA = "hermes.ea4e-kilo-send-chain/v1"
GENESIS = "0" * 64


class KiloSendStoreError(RuntimeError):
    pass


class KiloSendStoreUnavailable(KiloSendStoreError):
    pass


class KiloSendStoreIntegrityError(KiloSendStoreError):
    pass


class KiloSendStoreConflict(KiloSendStoreError):
    pass


class DurableKiloSendClaimStore:
    """Host-owned claim persistence; a receipt is returned only after anchor sync."""

    def __init__(self, path, *, anchor_path):
        self.path = Path(path).resolve()
        self.anchor_path = Path(anchor_path).resolve()
        self.lock_path = self.path.with_name(self.path.name + ".coordination.sqlite3")
        if len({self.path, self.anchor_path, self.lock_path}) != 3:
            raise KiloSendStoreUnavailable("claim store paths collide")
        if not self.path.is_file() or not self.anchor_path.is_file():
            raise KiloSendStoreUnavailable("claim store or anchor is absent")
        with self._connection() as db:
            self._verify(db)

    @classmethod
    def initialize(cls, path, *, anchor_path):
        """Explicit bootstrap only; never reconstruct a missing side."""
        path = Path(path).resolve()
        anchor_path = Path(anchor_path).resolve()
        if path.exists() or anchor_path.exists():
            return cls(path, anchor_path=anchor_path)
        if path == anchor_path or anchor_path == path.with_name(path.name + ".coordination.sqlite3"):
            raise KiloSendStoreUnavailable("claim store paths collide")
        path.parent.mkdir(parents=True, exist_ok=True)
        instance_id = uuid.uuid4().hex
        db = sqlite3.connect(str(path), isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                       "schema_id TEXT NOT NULL, instance_id TEXT NOT NULL, "
                       "generation INTEGER NOT NULL, head_hash TEXT NOT NULL)")
            db.execute("INSERT INTO metadata VALUES(1, ?, ?, 0, ?)", (SCHEMA, instance_id, GENESIS))
            db.execute("CREATE TABLE claims (sequence INTEGER PRIMARY KEY, "
                       "authorization_id TEXT NOT NULL UNIQUE, attempt_id TEXT NOT NULL UNIQUE, "
                       "run_id TEXT NOT NULL UNIQUE, request_nonce TEXT NOT NULL UNIQUE, "
                       "material_json TEXT NOT NULL, material_hash TEXT NOT NULL, "
                       "previous_hash TEXT NOT NULL, receipt_hash TEXT NOT NULL UNIQUE)")
            db.execute("COMMIT")
            cls._write_anchor(anchor_path, instance_id, 0, GENESIS)
        except (OSError, sqlite3.Error) as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise KiloSendStoreUnavailable("claim store bootstrap incomplete") from exc
        finally:
            db.close()
        return cls(path, anchor_path=anchor_path)

    @staticmethod
    def _anchor_payload(instance_id, generation, head_hash):
        material = {"schema_id": ANCHOR_SCHEMA, "instance_id": instance_id,
                    "generation": generation, "head_hash": head_hash}
        return {**material, "anchor_hash": sha256_payload(material)}

    @classmethod
    def _write_anchor(cls, path, instance_id, generation, head_hash):
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(cls._anchor_payload(instance_id, generation, head_hash)) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise KiloSendStoreUnavailable("claim anchor publication failed") from exc

    @contextmanager
    def _connection(self):
        lock = None
        db = None
        try:
            lock = sqlite3.connect(str(self.lock_path), isolation_level=None, timeout=1)
            lock.execute("BEGIN IMMEDIATE")
            db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                                 isolation_level=None, timeout=1)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            yield db
        except sqlite3.Error as exc:
            raise KiloSendStoreUnavailable("claim store unavailable") from exc
        finally:
            if db is not None:
                db.close()
            if lock is not None:
                lock.close()

    def _verify(self, db):
        try:
            metadata = db.execute("SELECT * FROM metadata WHERE singleton=1").fetchone()
            rows = db.execute("SELECT * FROM claims ORDER BY sequence").fetchall()
            with self.anchor_path.open("r", encoding="utf-8") as stream:
                anchor = json.load(stream)
        except (sqlite3.Error, OSError, ValueError, UnicodeError) as exc:
            raise KiloSendStoreIntegrityError("claim store cannot be verified") from exc
        if metadata is None or metadata["schema_id"] != SCHEMA:
            raise KiloSendStoreIntegrityError("claim store schema mismatch")
        generation, head_hash, instance_id = (metadata["generation"],
                                               metadata["head_hash"], metadata["instance_id"])
        if type(generation) is not int or generation < 0 or type(instance_id) is not str:
            raise KiloSendStoreIntegrityError("claim lineage malformed")
        expected = self._anchor_payload(instance_id, generation, head_hash)
        if anchor != expected:
            raise KiloSendStoreIntegrityError("claim anchor mismatch")
        previous = GENESIS
        for index, row in enumerate(rows, 1):
            try:
                material = json.loads(row["material_json"])
                if type(material) is not dict:
                    raise KiloSendStoreIntegrityError("claim material malformed")
                material_hash = candidate_send_claim_hash({k: v for k, v in material.items() if k != "schema"})
            except (KiloSendClaimDenied, ValueError, TypeError, KeyError) as exc:
                raise KiloSendStoreIntegrityError("claim material malformed") from exc
            if (material != canonical_send_claim_material({k: v for k, v in material.items() if k != "schema"})
                    or row["material_json"] != canonical_json(material)
                    or row["sequence"] != index
                    or row["authorization_id"] != material["invocation_authorization_id"]
                    or row["attempt_id"] != material["execution_attempt_id"]
                    or row["run_id"] != material["run_id"]
                    or row["request_nonce"] != material["request_nonce"]
                    or row["material_hash"] != material_hash
                    or row["previous_hash"] != previous):
                raise KiloSendStoreIntegrityError("claim row mismatch")
            receipt = sha256_payload({"schema": CHAIN_SCHEMA, "sequence": index,
                                      "previous_hash": previous, "material_hash": material_hash})
            if row["receipt_hash"] != receipt:
                raise KiloSendStoreIntegrityError("claim chain mismatch")
            previous = receipt
        if generation != len(rows) or head_hash != previous:
            raise KiloSendStoreIntegrityError("claim generation mismatch")
        return instance_id, generation, previous

    def _after_database_commit_before_anchor(self):
        """Crash-injection seam; any interruption leaves the store fail-closed."""

    def claim(self, values):
        material = canonical_send_claim_material(values)
        material_hash = candidate_send_claim_hash(values)
        with self._connection() as db:
            instance_id, generation, previous = self._verify(db)
            for column, value in (("authorization_id", values["invocation_authorization_id"]),
                                  ("attempt_id", values["execution_attempt_id"]),
                                  ("run_id", values["run_id"]),
                                  ("request_nonce", values["request_nonce"])):
                if db.execute(f"SELECT 1 FROM claims WHERE {column}=?", (value,)).fetchone():
                    raise KiloSendStoreConflict("send identity already claimed")
            sequence = generation + 1
            receipt = sha256_payload({"schema": CHAIN_SCHEMA, "sequence": sequence,
                                      "previous_hash": previous, "material_hash": material_hash})
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO claims VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (sequence, values["invocation_authorization_id"],
                            values["execution_attempt_id"], values["run_id"],
                            values["request_nonce"], canonical_json(material),
                            material_hash, previous, receipt))
                db.execute("UPDATE metadata SET generation=?, head_hash=? WHERE singleton=1",
                           (sequence, receipt))
                db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise KiloSendStoreConflict("send identity already claimed") from exc
            self._after_database_commit_before_anchor()
            self._write_anchor(self.anchor_path, instance_id, sequence, receipt)
            self._verify(db)
            return receipt
