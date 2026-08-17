"""EA-4D.3E-C deterministic local probe worker (real process boundary).

This is the single authorized LOCAL_WORKER_ADAPTER workload. It is spawned by
the real adapter via subprocess.Popen(shell=False) and implements the frozen
Option-A acceptance contract:

    receive request
    validate
    BEGIN transaction
    check idempotency key
    insert/reuse logical identity
    persist runtime_run_id + STARTED
    COMMIT
    emit STARTED ack
    exit

It performs NO user work, NO network, NO model invocation, NO production-data
mutation. It writes ONLY to the worker-owned SQLite idempotency registry passed
as argv[1].

Runtime freeze (authoritative values used by the adapter):
    protocol_version : hermes-local-worker-v1
    registry schema  : local-worker-idempotency-v1
    runtime_run_id   : probe-run-<sha256(idempotency_key)[:16]>

Fault-injection flags (test-only, never from task input):
    --reject               write FAILED row, exit 1 (definitive non-start)
    --exit-before-ack     accept+commit then exit without emitting ack
    --delay N             sleep N seconds before emitting ack
    --malformed-ack       emit an invalid JSON line instead of a valid ack
"""

import argparse
import hashlib
import json
import sqlite3
import sys
import time


REGISTRY_TABLE = "local_worker_idempotency"
REGISTRY_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} (
    idempotency_key TEXT PRIMARY KEY,
    launch_attempt_id TEXT NOT NULL,
    runtime_run_id TEXT NOT NULL,
    state TEXT NOT NULL,
    recorded_at REAL NOT NULL
);
"""
SCHEMA_VERSION_MARKER = "local-worker-idempotency-v1"


def _runtime_run_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return "probe-run-" + digest[:16]


def _connect(registry_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(registry_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(REGISTRY_SCHEMA)
    conn.execute("COMMIT")


def _accept(conn: sqlite3.Connection, idempotency_key: str,
            launch_attempt_id: str, state: str) -> str:
    run_id = _runtime_run_id(idempotency_key)
    conn.execute("BEGIN IMMEDIATE")
    existing = conn.execute(
        f"SELECT runtime_run_id, state FROM {REGISTRY_TABLE} "
        f"WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
    if existing is not None:
        conn.execute("ROLLBACK")
        return existing[0]
    conn.execute(
        f"INSERT INTO {REGISTRY_TABLE} "
        f"(idempotency_key, launch_attempt_id, runtime_run_id, state, recorded_at) "
        f"VALUES (?, ?, ?, ?, ?)",
        (idempotency_key, launch_attempt_id, run_id, state, time.time()))
    conn.execute("COMMIT")
    return run_id


def _emit_ack(idempotency_key: str, launch_attempt_id: str,
              runtime_run_id: str) -> None:
    ack = {
        "protocol_version": "hermes-local-worker-v1",
        "idempotency_key": idempotency_key,
        "launch_attempt_id": launch_attempt_id,
        "runtime_run_id": runtime_run_id,
        "state": "STARTED",
    }
    sys.stdout.write(json.dumps(ack) + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry_path")
    parser.add_argument("--reject", action="store_true")
    parser.add_argument("--exit-before-ack", action="store_true")
    parser.add_argument("--exit-before-commit", action="store_true")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="sleep this many seconds before emitting ack "
                             "(used to exceed ack_timeout in tests)")
    parser.add_argument("--sleep-before-commit", type=float, default=0.0,
                        help="sleep this many seconds BEFORE durable "
                             "acceptance (no registry row at ack timeout -> "
                             "UNKNOWN)")
    parser.add_argument("--malformed-ack", action="store_true")
    args = parser.parse_args(argv)

    # Read exactly one canonical request line from stdin.
    raw = sys.stdin.readline()
    try:
        request = json.loads(raw)
    except (ValueError, TypeError):
        return 2  # unusable request
    if request.get("protocol_version") != "hermes-local-worker-v1":
        return 2
    idempotency_key = request.get("idempotency_key")
    launch_attempt_id = request.get("launch_attempt_id")
    if not idempotency_key or not launch_attempt_id:
        return 2

    conn = _connect(args.registry_path)
    try:
        _ensure_schema(conn)
        if args.exit_before_commit:
            # Validate then exit WITHOUT committing: simulates a worker that
            # dies before durable acceptance. No registry row -> adapter
            # normalizes to UNKNOWN (ambiguous, not authoritative).
            conn.close()
            return 0
        if args.sleep_before_commit > 0:
            # Sleep BEFORE durable acceptance: if the adapter's ack timeout
            # fires first, no registry row exists and the launch normalizes
            # to UNKNOWN.
            time.sleep(args.sleep_before_commit)
        if args.reject:
            _accept(conn, idempotency_key, launch_attempt_id, "FAILED")
            return 1
        run_id = _accept(conn, idempotency_key, launch_attempt_id, "STARTED")
    finally:
        conn.close()

    if args.delay > 0:
        time.sleep(args.delay)
    if args.sleep > 0:
        time.sleep(args.sleep)
    if args.exit_before_ack:
        return 0
    if args.malformed_ack:
        sys.stdout.write("this is not valid json\n")
        sys.stdout.flush()
        return 0
    _emit_ack(idempotency_key, launch_attempt_id, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
