---
title: "AUTH-2026-08-13 Hermes EA-3A Domain Binding Amendment"
document_id: "AUTH-2026-08-13-HERMES-EA3A-DOMAIN-BINDING-AMENDMENT"
version: "0.1.0"
status: "proposed"
owner: "Hermes Agent"
date: "2026-08-13"
source_milestone: "Hermes EA-3A Domain Binding Amendment Authorization"
reference_commits:
  - "df5134b Clarify execution authorization time semantics"
  - "4ccff94 Add Hermes execution authorization domain model (EA-1)"
  - "a09981e Add Hermes execution authority persistence (EA-2)"
  - "1ba7a19 Design Hermes execution authorization issuance (EA-3D)"
authorized_scope:
  - "Domain-model strengthening: cryptographic lineage bindings"
  - "ExecutionAuthorizationDecision.request_hash"
  - "ExecutionAuthorization.request_id / request_hash / decision_id / decision_hash"
  - "Schemas require new binding fields"
  - "Builders + validation + reconstruction updated"
  - "EA-2 store reconstruction compatibility (authorization_id column)"
  - "Acyclic identity graph (Model A); artifact_version bumped to 2"
forbidden_scope:
  - "Atomic store grant API (record_granted_decision_and_authorization)"
  - "Request-keyed store reads (get_decision_for_request / get_authorization_for_request)"
  - "Authorization issuance service"
  - "grant_execution_authorization / issue_execution_authorization / authorize"
  - "policy engine with grant capability"
  - "ExecutionClaim / ExecutionAttempt"
  - "WorkerRouter / worker launch / enqueue / dispatch"
  - "AUTHORIZED_FOR_EXECUTION / EXECUTING transitions"
key_findings:
  - "Authorization -> Decision -> Request -> AcceptanceArtifact lineage is now cryptographically complete"
  - "Acyclic Model A chosen: decision_id/decision_hash exclude authorization_id (non-hash-bound forward linkage)"
  - "authorization_id persisted in a dedicated decisions-table column for round-trip reconstruction"
  - "Amended Decision/Authorization artifacts use artifact_version = 2; Request stays 1"
disposition:
  - "PASS (domain amendment complete, persistence-integrity correction applied)"
  - "NO issuance capability"
  - "NO atomic grant store API (deferred to EA-3B)"
  - "NO request-keyed store extension (deferred to EA-3B)"
  - "authority DB schema bumped to v2; v1 fails closed (no silent migration)"
  - "authorization_id persistence envelope tamper-evident (decision_linkage_sha256)"
invariants_preserved:
  - "ACCEPTED != EXECUTION AUTHORIZATION"
verification:
  production_python_changed: "YES (domain + store reconstruction-compat + integrity envelope; no issuance/worker/claim)"
  tests_ea1_focused: "46/46 PASS (39 baseline + 7 EA-3A binding)"
  tests_ea2_focused: "22/22 PASS (17 baseline + 5 correction)"
  tests_schema: "9/9 PASS"
  full_hermes_core: "361/361 PASS"
  mutation_tooth: "PASS (decision_hash preimage removal kills targeted test; byte-exact restore)"
  git_diff_check: "clean"
  db_tracked: "NONE"
  production_db_created: "NO"
  unrelated_edits_untouched: "YES"
---

# AUTH-2026-08-13 — Hermes EA-3A Domain Binding Amendment

This record authorizes EA-3A as a **domain-model strengthening** milestone only.
It closes the cryptographic lineage gap identified by EA-3D (Decision and
Authorization did not cryptographically bind to the exact Request/Decision that
produced them). No real issuance capability is introduced; EA-3B (atomic store
amendment) and EA-3I (issuance implementation) remain separately authorized.

Disposition: **PASS (domain amendment complete).**
