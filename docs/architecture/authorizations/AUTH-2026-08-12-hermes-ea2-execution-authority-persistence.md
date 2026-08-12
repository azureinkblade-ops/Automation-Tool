---
title: "AUTH-2026-08-12 Hermes EA-2 Execution Authority Persistence"
document_id: "AUTH-2026-08-12-HERMES-EA2-EXECUTION-AUTHORITY-PERSISTENCE"
version: "0.1.0"
status: "proposed"
owner: "Hermes Agent"
date: "2026-08-12"
source_milestone: "Hermes EA-2 Execution Authority Persistence + Integrity Ledger Milestone"
reference_commits:
  - "df5134b Clarify execution authorization time semantics"
  - "4ccff94 Add Hermes execution authorization domain model (EA-1)"
  - "EA-2 commit: Add Hermes execution authority persistence (post-hoc)"
authorization_scope:
  - "Persistence of EA-1 immutable artifacts (Request / Decision / Authorization) in a separate execution_authority.db"
  - "SQLite schema version 1 with fail-closed version guard"
  - "Hash verification before write and on load (canonical hashing reused from hashing.py)"
  - "Append-only, hash-linked execution-authority ledger (one global chain)"
  - "Transactional artifact + ledger event persistence (BEGIN IMMEDIATE / rollback)"
  - "Runtime store provider seam (get_execution_authorization_store) and DB-path resolver (HERMES_EXECUTION_AUTHORITY_DB -> %LOCALAPPDATA%\\Hermes\\execution_authority.db)"
  - "Tamper / reload / schema-version / journal-mode / idempotency / conflict tests"
  - "ExecutionAuthorizationIntegrityError + ExecutionAuthorizationStoreError hierarchy"
forbidden_scope:
  - "Authorization issuance / grant_execution_authorization / authorize / policy evaluation that grants authority"
  - "ExecutionClaim / ExecutionAttempt / authorization or attempt consumption"
  - "Worker routing / launch / enqueue / dispatch"
  - "AWAITING_EXECUTION_AUTHORIZATION / AUTHORIZED_FOR_EXECUTION / EXECUTION_CLAIMED / EXECUTING transitions"
invariants:
  - "ACCEPTED != EXECUTION AUTHORIZATION (preserved; store grants no authority)"
  - "Separate database from governance.db and automation_state.db"
  - "Resolver has no filesystem side effect; DB created only at store open"
  - "Corruption raises ExecutionAuthorizationIntegrityError; missing record returns None"
verification:
  focused_ea2_tests: "17/17 PASS"
  ea1_regression: "39/39 PASS"
  full_hermes_core: "340/340 PASS"
  git_diff_check: "clean"
  production_db_created_in_tests: "NO"
  db_tracked: "NO"
---

# AUTH-2026-08-12 — Hermes EA-2 Execution Authority Persistence

This record authorizes EA-2 (Execution Authority Persistence + Integrity Ledger)
as a **persistence/integrity-only** milestone. It makes EA-1 domain artifacts
durably storable, reloadable, version-guarded, and tamper-detectable.

EA-2 does **not** authorize creation of real execution authority. The store
persists *representations* and answers: what immutable artifact was persisted,
whether it still verifies, what audit events exist, whether the chain is intact.
It never decides whether authorization should be granted.

Disposition: **PASS** (verified, not yet pushed per stop condition).
