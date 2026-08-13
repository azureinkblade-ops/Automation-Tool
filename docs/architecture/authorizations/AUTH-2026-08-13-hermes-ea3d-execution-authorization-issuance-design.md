---
title: "AUTH-2026-08-13 Hermes EA-3D Execution Authorization Issuance Design"
document_id: "AUTH-2026-08-13-HERMES-EA3D-EXECUTION-AUTHORIZATION-ISSUANCE-DESIGN"
version: "0.1.0"
status: "proposed"
owner: "Hermes Agent"
date: "2026-08-13"
source_milestone: "Hermes EA-3D Execution Authorization Issuance Design"
reference_commits:
  - "df5134b Clarify execution authorization time semantics"
  - "4ccff94 Add Hermes execution authorization domain model (EA-1)"
  - "a09981e Add Hermes execution authority persistence (EA-2)"
authorization_scope:
  - "Documentation/design only for execution-authorization issuance trust boundary"
  - "Authority principal matrix (HUMAN / POLICY_SERVICE / SYSTEM)"
  - "Request prerequisite, GRANTED-decision prerequisite, atomic grant persistence"
  - "Domain amendment assessment (Authorization to Decision/Request binding required)"
  - "Store amendment assessment (atomic issuance method + request-keyed reads required)"
  - "Threat model, security invariants, human/policy-service flows, EA-3I phase slices"
forbidden_scope:
  - "Production Python implementation"
  - "ExecutionAuthorizationService / AuthorizationIssuanceService"
  - "grant_execution_authorization / issue_execution_authorization / authorize"
  - "policy engine with grant capability"
  - "ExecutionClaim / ExecutionAttempt"
  - "WorkerRouter / worker launch / enqueue / dispatch"
  - "AWAITING_EXECUTION_AUTHORIZATION / AUTHORIZED_FOR_EXECUTION / EXECUTING transitions"
disposition:
  - "DESIGN ONLY"
  - "NO PRODUCTION PYTHON"
  - "NO ISSUANCE"
  - "NO CLAIM"
  - "NO WORKER"
key_findings:
  - "EA-1 ExecutionAuthorization lacks request_id/request_hash/decision_id/decision_hash -> DOMAIN AMENDMENT REQUIRED before EA-3I"
  - "EA-2 record_decision + record_authorization separate calls cannot guarantee atomic grant -> STORE AMENDMENT REQUIRED"
  - "AUTHORIZED_FOR_EXECUTION is a derived condition, not first-class state"
  - "Null expiry prohibited in initial EA-3; worker_class=None means deferred-not-unrestricted"
invariants_preserved:
  - "ACCEPTED != EXECUTION AUTHORIZATION"
verification:
  production_python_changed: "NO"
  full_hermes_core_baseline: "340/340 known green (docs only; not rerun for documentation)"
  git_diff_check: "clean"
  unrelated_edits_untouched: "YES"
---

# AUTH-2026-08-13 — Hermes EA-3D Execution Authorization Issuance Design

This record authorizes EA-3D as a **documentation/design-only** milestone. It
freezes the execution-authorization issuance trust boundary and contract before
any callable component can create a real `ExecutionAuthorization`.

No production Python is changed. No issuance, claim, worker, or execution
transition is introduced. The next step (EA-3I implementation) requires separate
explicit authorization and completion of the domain + store amendments identified
here.

Disposition: **PASS (design only, not pushed per stop condition).**
