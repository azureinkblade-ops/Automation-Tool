"""Fake-only coverage for Codex's durable terminal observation time."""

import sqlite3

import pytest

from tools.hermes_core.codex_adapter import (
    CodexAdapterError, CodexInvocationRegistry, REGISTRY_SCHEMA_VERSION,
)


def reserve(registry):
    registry.initialize()
    return registry.reserve(
        key="invocation", material_hash="a" * 64, run_id="run",
        launch_id="launch", delegation_id="delegation", argv_hash="b" * 64,
    )


def test_terminal_observation_survives_restart_and_cannot_be_overwritten(tmp_path):
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    reserve(registry)
    assert registry.get("invocation").terminal_observed_at is None
    terminal = registry.transition(
        "invocation", start_state="DEFINITELY_STARTED",
        terminal_state="VERIFIED", pid=123, result_json='{"result":true}',
    )
    assert isinstance(terminal.terminal_observed_at, float)
    assert terminal.terminal_observed_at > 0
    reopened = CodexInvocationRegistry(registry.path)
    reopened.initialize()
    assert reopened.get("invocation") == terminal
    with pytest.raises(CodexAdapterError, match="immutable"):
        reopened.transition(
            "invocation", start_state="DEFINITELY_STARTED",
            terminal_state="VERIFIED", pid=456, result_json='{"result":false}',
        )
    assert reopened.get("invocation") == terminal


def test_migration_does_not_invent_time_for_legacy_terminal_row(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE codex_transport_metadata (schema_version INTEGER NOT NULL)")
        conn.execute("INSERT INTO codex_transport_metadata VALUES (1)")
        conn.execute("""CREATE TABLE codex_transport_invocations (
            idempotency_key TEXT PRIMARY KEY, material_hash TEXT NOT NULL,
            runtime_run_id TEXT NOT NULL, launch_attempt_id TEXT NOT NULL,
            delegation_id TEXT NOT NULL, argv_hash TEXT NOT NULL,
            start_state TEXT NOT NULL, terminal_state TEXT, pid INTEGER,
            result_json TEXT, cancellation_reason TEXT,
            created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
        conn.execute("""INSERT INTO codex_transport_invocations VALUES
            ('legacy', ?, 'run', 'launch', 'delegation', ?,
             'DEFINITELY_STARTED', 'VERIFIED', 123, '{}', NULL, 1, 2)""",
                     ("a" * 64, "b" * 64))
    registry = CodexInvocationRegistry(str(path))
    registry.initialize()
    registry.initialize()
    assert registry.get("legacy").terminal_observed_at is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT schema_version FROM codex_transport_metadata").fetchone() == (REGISTRY_SCHEMA_VERSION,)
    with pytest.raises(CodexAdapterError, match="immutable"):
        registry.transition("legacy", start_state="DEFINITELY_STARTED", terminal_state="VERIFIED")


def test_missing_transition_does_not_create_terminal_time(tmp_path):
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    with pytest.raises(CodexAdapterError, match="missing"):
        registry.transition("absent", start_state="DEFINITELY_STARTED", terminal_state="VERIFIED")
    assert registry.get("absent") is None
