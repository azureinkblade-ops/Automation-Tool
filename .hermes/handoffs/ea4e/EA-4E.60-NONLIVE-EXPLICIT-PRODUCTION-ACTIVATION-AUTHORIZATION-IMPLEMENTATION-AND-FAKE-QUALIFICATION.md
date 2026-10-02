# EA-4E.60 Non-Live Explicit Production-Activation Authorization Implementation and Fake Qualification

## Governing State

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=d61945f96e11b19ef0dcbd008c4d301647c8acad
GOVERNING_REMOTE_HEAD=d61945f96e11b19ef0dcbd008c4d301647c8acad
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
EA4E59_RECONCILIATION_CHECKPOINT=PASS
EA4E59_RECONCILIATION_CHECKPOINT_COMMIT=d61945f96e11b19ef0dcbd008c4d301647c8acad
EA4E60_IMPLEMENTATION_DERIVED_FROM_CHECKPOINTED_EA4E59_CONTRACT=YES
```

The worktree started with 246 pre-existing WIP entries. The three pre-existing
tracked changes were the EA-4E.6 receiver-router evidence, `tools/hermes_core/__init__.py`,
and `tools/hermes_core/receiver_registry.py`. They were not modified by EA-4E.60.

## Implementation

```text
EA4E60_IMPLEMENTATION_MODULES=tools/hermes_core/production_activation_authorization.py; tools/hermes_core/production_activation_authorization_store.py
EA4E60_NEW_PRODUCTION_FILES=tools/hermes_core/production_activation_authorization.py; tools/hermes_core/production_activation_authorization_store.py
EA4E60_MODIFIED_PRODUCTION_FILES=app.py; tools/hermes_core/production_app_config.py; tools/hermes_core/production_app_lifecycle.py
ACTIVATION_AUTHORIZATION_SCHEMA_ID=hermes.production-activation-authorization/v1
ACTIVATION_AUTHORIZATION_VERSION=ea4e.59
ACTIVATION_AUTHORIZATION_ARTIFACT_VERSION=1
ACTIVATION_AUTHORIZATION_CANONICAL_HASH_DEFINED=YES
IRRELEVANT_TASK_TEXT_INCLUDED_IN_ACTIVATION_AUTH_HASH=NO
SECRET_INCLUDED_IN_ACTIVATION_AUTH_HASH=NO
MAPPING_ORDER_ALTERS_ARTIFACT_HASH=NO
```

The immutable artifact binds one request and receiver to the governing commit,
router contract, execution-authority contract, transport contract, model binding,
feature-gate state, activation mode, issuer, issuance/expiry times, and nonce.
Its ID is derived from the canonical artifact hash. The default and maximum TTL
are both 300 seconds, and all time comes from the injected clock.

## Issue Path

`app.issue_production_activation_authorization` is the separate explicit action.
It parses an operator request and delegates to
`ProductionActivationAuthorizationIssuer.issue`. The policy uses configured
readiness and current durable recovery state; neither can be asserted by task
text or untrusted request fields. Issuance persists `ISSUED` and stops.

```text
ISSUE_ACTION_STOPS_AT_ISSUED=YES
ISSUE_ACTION_CLAIMS_AUTHORIZATION=NO
ISSUE_ACTION_PERFORMS_ACTIVATION_TRANSITION=NO
ISSUE_ACTION_CONSUMES_AUTHORIZATION=NO
ISSUE_ACTION_BINDS_EXECUTOR=NO
ISSUE_ACTION_ISSUES_INVOCATION_AUTHORIZATION=NO
ISSUE_ACTION_STARTS_RECEIVER_PROCESS=NO
ISSUE_ACTION_INVOKES_MODEL=NO
READINESS_PASS_ALONE_ISSUES_ACTIVATION_AUTHORIZATION=NO
ORDINARY_PRODUCTION_ACTION_AUTO_REQUESTS_ACTIVATION_AUTH=NO
GROK_ACTIVATION_AUTHORIZATION=DENY
```

The app requires an explicitly bootstrapped activation-authorization store when
the governed app action is configured. App startup, factory build, and runtime do
not create or bootstrap this store.

## Store and State Machine

`ProductionActivationAuthorizationStore` uses a separate SQLite database with
schema version 1. `ProductionActivationAuthStoreBootstrapper` is the only
initializer. Construction only reopens and validates an existing store.

```text
ACTIVATION_AUTH_STORE_TYPE=ProductionActivationAuthorizationStore
ACTIVATION_AUTH_STORE_BOOTSTRAP_OWNER=ProductionActivationAuthStoreBootstrapper
APP_STARTUP_AUTO_BOOTSTRAPS_ACTIVATION_AUTH_STORE=NO
FACTORY_BUILD_AUTO_BOOTSTRAPS_ACTIVATION_AUTH_STORE=NO
RUNTIME_AUTO_BOOTSTRAPS_ACTIVATION_AUTH_STORE=NO
STORE_OWNS_DURABLE_STATE_TRANSITIONS=YES
CLAIM_STATE_MUTATION_OWNER=ProductionActivationAuthorizationStore.claim
CLAIM_POLICY_CALLER=ProductionActivationAuthorizationPolicy.claim
ACTIVATION_AUTHORIZATION_SINGLE_USE=YES
ACTIVATION_AUTHORIZATION_REPLAY_DENIED=YES
DURABLE_REOPEN_PRESERVES_CONSUMED_STATE=YES
DURABLE_REOPEN_PRESERVES_ABORTED_STATE=YES
REPLAY_AFTER_RESTART_DENIED=YES
MULTIPLE_SIMULTANEOUS_ACTIVATION_AUTH_REQUESTS_POLICY=FAIL_CLOSED_SINGLE_OUTSTANDING_ISSUED_OR_CLAIMED
```

Durable states are `ISSUED`, `CLAIMED`, `CONSUMED`, `ABORTED`, `EXPIRED`, and
`DENIED`. Atomic claim accepts only `ISSUED`. Successful transition durably
consumes; failed transition durably aborts. Expired rows cannot be claimed and
are retired during a later, fresh explicit issue action. No path retries,
reissues, falls back, or fails over automatically.

## Lifecycle Integration

The request lifecycle retains the EA-4E.11 `ProductionActivation` and validator.
After admission, lifecycle credential preflight, and existing binding lookup, it
validates execution authority, validates activation authorization without state
mutation, atomically claims it, accepts the existing ENABLED activation for the
request, and durably consumes the authorization. Only then may the existing host
path reach invocation authorization and the runtime.

```text
VALIDATION_PRECEDES_CLAIM=YES
CLAIM_PRECEDES_TRANSITION=YES
TRANSITION_PRECEDES_CONSUME=YES
SUCCESSFUL_TRANSITION_FINAL_AUTH_STATE=CONSUMED
FAILED_TRANSITION_AFTER_CLAIM_FINAL_AUTH_STATE=ABORTED
ACTIVATION_AUTH_CLAIM_OCCURS_AFTER_LIFECYCLE_ADMISSION=YES
ACTIVATION_AUTH_CLAIM_OCCURS_AFTER_LIFECYCLE_PREFLIGHT=YES
MISSING_BINDING_CAN_CLAIM_ACTIVATION_AUTH=NO
INVALID_EXECUTION_AUTHORITY_CAN_CLAIM_ACTIVATION_AUTH=NO
EA4E11_PRODUCTION_ACTIVATION_VALIDATOR_RETAINED=YES
```

`ProductionAppActivationTransitionOwner` owns only the request-scoped activation
transition, durable consume, and in-memory teardown. A consume persistence failure
removes active request state, blocks the host/runtime path, and marks the durable
request lifecycle as recovery-required. It does not guess whether a failed write
committed and does not retry or issue a replacement authorization.

```text
REQUEST_CAN_EXECUTE_IF_CONSUME_NOT_DURABLY_CONFIRMED=NO
CONSUME_WRITE_FAILURE_FINAL_STATE=RECOVERY_REQUIRED_TO_CONFIRM_ABORTED
CONSUME_WRITE_FAILURE_AUTO_RETRIES=NO
CONSUME_WRITE_FAILURE_AUTO_REISSUES_AUTH=NO
ACTIVATION_TEARDOWN_OWNER=ProductionAppRequestLifecycleOwner.finally
ACTIVATION_TEARDOWN_FINALLY_EQUIVALENT=YES
BINDING_TEARDOWN_FINALLY_EQUIVALENT=YES
TEARDOWN_EXACTLY_ONCE_GUARANTEE=YES
CONCURRENCY_POLICY=FAIL_CLOSED_SINGLE_SLOT
```

The lifecycle `finally` clears request activation before performing the existing
exact-binding teardown. Durable `CONSUMED` and `ABORTED` rows survive teardown.
Activation accounting-event writes are observational and cannot issue, claim,
activate, bind, or execute.

## Separation Invariants

```text
ACTIVATION_AUTHORIZATION != ACTIVATION
ACTIVATION_AUTHORIZATION_REQUEST != ACTIVATION_AUTHORIZATION
ACTIVATION_AUTHORIZATION_ISSUANCE != ACTIVATION
ACTIVATION_AUTHORIZATION_VALIDATION != ACTIVATION
ACTIVATION_AUTHORIZATION_CONSUMPTION != EXECUTION
SEPARATE_EXECUTION_AUTHORITY_STILL_REQUIRED=YES
SEPARATE_BINDING_STILL_REQUIRED=YES
SEPARATE_INVOCATION_AUTH_STILL_REQUIRED=YES
SEPARATE_EXECUTION_BOUNDARY_STILL_REQUIRED=YES
PERSISTENT_PRODUCTION_ACTIVATION=NO
NEXT_REQUEST_REQUIRES_NEW_ACTIVATION_AUTHORIZATION=YES
```

## Fake Qualification

The dedicated suite exercises issuance-only behavior, canonical hashing and ID,
policy denial, TTL, nonce, trusted readiness/recovery, Kilo and OpenCode fake app
paths, Grok denial, cross-receiver denial, non-mutating validation, atomic claim,
replay, restart durability, expiry retirement, transition consume/abort,
consume-write failure, missing-binding and invalid-authority ordering, lifecycle
teardown, and durable accounting order.

```text
TEST_ISSUE_ONLY_DOES_NOT_CLAIM=PASS
TEST_ISSUE_ONLY_DOES_NOT_ACTIVATE=PASS
TEST_ISSUE_ONLY_DOES_NOT_BIND=PASS
TEST_ISSUE_ONLY_DOES_NOT_EXECUTE=PASS
TEST_VALID_ACTIVATION_AUTHORIZATION=PASS
TEST_TAMPERED_ACTIVATION_AUTHORIZATION=DENY
TEST_WRONG_REQUEST_ID=DENY
TEST_WRONG_RECEIVER=DENY
TEST_WRONG_GOVERNING_COMMIT=DENY
TEST_WRONG_ROUTER_CONTRACT=DENY
TEST_WRONG_AUTHORITY_CONTRACT=DENY
TEST_WRONG_TRANSPORT_BINDING=DENY
TEST_WRONG_MODEL_BINDING=DENY
TEST_FEATURE_GATE_DISABLED=DENY
TEST_READINESS_NOT_PASS=DENY
TEST_EXPIRED_ACTIVATION_AUTHORIZATION=DENY
TEST_MISSING_NONCE=DENY
TEST_ATOMIC_CLAIM_SUCCESS=PASS
TEST_SECOND_CLAIM_REPLAY=DENY
TEST_SUCCESSFUL_TRANSITION=PASS
TEST_TRANSITION_FAILURE_ABORTS=PASS
TEST_CONSUME_PERSISTENCE_FAILURE_FAILS_CLOSED=PASS
TEST_ABORTED_AUTHORIZATION_REPLAY=DENY
TEST_CONSUMED_AUTHORIZATION_REPLAY=DENY
TEST_REOPEN_PRESERVES_CONSUMED_STATE=PASS
TEST_REOPEN_PRESERVES_ABORTED_STATE=PASS
TEST_NEXT_REQUEST_REQUIRES_FRESH_AUTHORIZATION=PASS
TEST_MISSING_BINDING_CANNOT_CLAIM=PASS
TEST_INVALID_EXECUTION_AUTHORITY_CANNOT_CLAIM=PASS
TEST_RECOVERY_BLOCKED_ACTIVATION_AUTH=DENY
TEST_SECOND_OUTSTANDING_ISSUED_OR_CLAIMED=DENY
TEST_GROK_ACTIVATION_AUTHORIZATION=DENY
FAKE_KILO_ACTIVATION_AUTHORIZATION_PATH=PASS
FAKE_OPENCODE_ACTIVATION_AUTHORIZATION_PATH=PASS
TEST_CONSUME_FAILURE_BLOCKS_RUNTIME=PASS
TEST_INVOCATION_AUTH_NOT_CLAIMED_BEFORE_ACTIVATION_AUTH_CONSUMED=PASS
TEST_PROCESS_INTENT_NOT_WRITTEN_BEFORE_ACTIVATION_AUTH_CONSUMED=PASS
TEST_MODEL_INTENT_NOT_WRITTEN_BEFORE_ACTIVATION_AUTH_CONSUMED=PASS
TEST_ACTIVATION_ACCOUNTING_ORDER=PASS
IMPORT_ACTIVATION_AUTH_MODULE_STARTS_RECEIVER=NO
IMPORT_ACTIVATION_AUTH_MODULE_INVOKES_MODEL=NO
IMPORT_ACTIVATION_AUTH_MODULE_CALLS_NETWORK=NO
```

## Test Results

```text
EA4E60_TEST_FILE=tests/hermes_core/test_ea4e60_nonlive_activation_authorization.py
EA4E60_DEDICATED_TESTS_PASSED=40
EA4E60_DEDICATED_TESTS_FAILED=0
EA4E58_RETRY_DEDICATED_TESTS_PASSED=4
EA4E58_RETRY_DEDICATED_TESTS_FAILED=0
EA4E58R3_DEDICATED_TESTS_PASSED=9
EA4E58R3_DEDICATED_TESTS_FAILED=0
EA4E58R_REGRESSION_TESTS_PASSED=11
EA4E58R_REGRESSION_TESTS_FAILED=0
EA4E57_REGRESSION_TESTS_PASSED=45
EA4E57_REGRESSION_TESTS_FAILED=0
EA4E56_REGRESSION_TESTS_PASSED=32
EA4E56_REGRESSION_TESTS_FAILED=0
EA4E55_52_REGRESSION_TESTS_PASSED=90
EA4E55_52_REGRESSION_TESTS_FAILED=0
SEALED_ALIGNED_PASSED=171
SEALED_ALIGNED_FAILED=0
BROADER_COMPATIBILITY_PASSED=527
BROADER_COMPATIBILITY_FAILED=15
BROADER_COMPATIBILITY_FAILURES_INHERITED=15
BROADER_COMPATIBILITY_NEW_FAILURES=0
```

The 15 broader failures are unchanged: 14 obsolete dual-binding fixtures in
EA-4E.36/37/38/39/41 conflict with the qualified one-binding limit, and the
EA-4E.43 enabled-path fixture omits execution authority. The exact same failures
were documented before EA-4E.60. No old security assertion was removed or
weakened. Two EA-4E.53 fake-executor cases were updated only to supply the newly
required fake activation authorization before testing their original executor
failure and teardown behavior.

## WIP and Live Activity

```text
EA4E60_PRODUCTION_CHANGE_FILES=app.py; tools/hermes_core/production_app_config.py; tools/hermes_core/production_app_lifecycle.py; tools/hermes_core/production_activation_authorization.py; tools/hermes_core/production_activation_authorization_store.py
EA4E60_TEST_CHANGE_FILES=tests/hermes_core/test_ea4e60_nonlive_activation_authorization.py; tests/hermes_core/test_ea4e52_nonlive_app_host_integration.py; tests/hermes_core/test_ea4e53_nonlive_request_lifecycle.py
EA4E60_EVIDENCE_FILES=.hermes/handoffs/ea4e/EA-4E.60-NONLIVE-EXPLICIT-PRODUCTION-ACTIVATION-AUTHORIZATION-IMPLEMENTATION-AND-FAKE-QUALIFICATION.md
EA4E60_TEMPORARY_ENTRIES=.pytest-ea4e60-* (22 untracked qualification directories)
PREEXISTING_EA4E_WIP_ENTRIES=246 entries at start; preserved and unstaged
UNRELATED_WIP_ENTRIES=present; preserved and unstaged
AMBIGUOUS_FILES=NONE

NEW_KILO_TASKS=0
NEW_KILO_RECEIVER_PROCESSES=0
NEW_KILO_MODEL_INVOCATIONS=0
NEW_OPENCODE_TASKS=0
NEW_OPENCODE_RECEIVER_PROCESSES=0
NEW_OPENCODE_MODEL_INVOCATIONS=0
NEW_LIVE_ACTIVATION_AUTH_REQUESTS=0
NEW_LIVE_ACTIVATION_AUTHS_ISSUED=0
NEW_LIVE_ACTIVATION_AUTHS_CLAIMED=0
NEW_LIVE_ACTIVATION_AUTHS_CONSUMED=0
NEW_PRODUCTION_ACTIVATIONS=0
NEW_REAL_EXECUTOR_REGISTRATIONS=0
NEW_REAL_EXECUTOR_BINDINGS=0
REAL_RECEIVER_PROCESS_INSPECTIONS=0
REAL_PROCESS_TERMINATION_ATTEMPTS=0
NETWORK_CALLS=0
PROVIDER_API_CALLS=0
DEVICE_CODE_FLOWS_STARTED=0
OAUTH_FLOWS_STARTED=0
BROWSERS_OPENED=0
CREDENTIALS_CREATED=0
CREDENTIALS_UPDATED=0
CREDENTIALS_REFRESHED=0
CREDENTIALS_DELETED=0
GROK_TASKS=0
GROK_RECEIVER_PROCESSES=0
GROK_MODEL_INVOCATIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Final Disposition

```text
EA4E60_EVIDENCE_CREATED=YES
EA4E60_RESULT=PASS
EA4E60_CHECKPOINT_ALLOWED=YES
PRODUCTION_ACTIVATED=NO
PRODUCTION_ACTIVATION_AUTHORIZED=NO
LIVE_EXECUTION_AUTHORIZED=NO
EA4E61_ALLOWED=NO
STAGED=0
COMMIT=NO
PUSH=NO
NEXT_PHASE=EA-4E.60 IMPLEMENTATION + EVIDENCE CHECKPOINT REVIEW
```

EA-4E.60 stops here. No production activation, live receiver, model, network,
provider, browser, GPU, or ComfyUI action was performed.

## EA-4E.61B Prospective Test-Evidence Reconciliation

The original EA-4E.60 qualification observed 191 passing predecessor tests, but
four of those tests came from
`tests/hermes_core/test_ea4e58_retry_nonlive_consolidation.py`, which was not
included in the EA-4E.60 committed checkpoint. Therefore commit `c29d379...`
could reproduce only 187 of the reported predecessor tests from tracked files.

EA-4E.61B Strategy A preserves that historical fact and adds the reviewed
four-test file prospectively. Its exact historical bytes remain unproven because
no prior hash or commit exists. Against the EA-4E.61B worktree candidate, pytest
collected the checkpointed nine-file predecessor set as 191 tests and all 191
passed. Committed reproducibility remains pending the separate EA-4E.61B
checkpoint.

```text
EA4E60_EVIDENCE_RECONCILIATION_REQUIRED=YES
EA4E60_EVIDENCE_HISTORICAL_FACTS_PRESERVED=YES
EA4E60_ORIGINAL_PREDECESSOR_TEST_OBSERVATION=191
EA4E60_COMMITTED_PREDECESSOR_TESTS_REPRODUCIBLE_AT_C29D379=187
EA4E61B_RETRY_TEST_ADDITION=PROSPECTIVE
EA4E58_RETRY_TEST_BYTE_FOR_BYTE_HISTORICAL_PROVENANCE_PROVEN=NO
EA4E61B_CANDIDATE_PREDECESSOR_TESTS_COLLECTED=191
EA4E61B_CANDIDATE_PREDECESSOR_TESTS_PASSED=191
EA4E61B_CANDIDATE_PREDECESSOR_TESTS_FAILED=0
EA4E61B_COMMITTED_REPRODUCIBILITY=NO_PENDING_CHECKPOINT
```
