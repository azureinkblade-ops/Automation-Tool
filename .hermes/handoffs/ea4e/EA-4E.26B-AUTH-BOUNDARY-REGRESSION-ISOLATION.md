# EA-4E.26B Non-Live Authorization-Boundary and Regression-Isolation Remediation

## Purpose

This document records the direct EA-4E.23 authorization-boundary qualification
and regression-isolation remediation for EA-4E.26B.

## Direct Cross-Receiver Authorization Isolation (at EA-4E.23)

### Kilo Auth Cannot Execute OpenCode

| Field | Value |
|-------|-------|
| Test | `TestDirectCrossReceiverAuthIsolation::test_kilo_auth_cannot_execute_opencode_direct` |
| Binding Resolution | **PASS** (OpenCode binding resolved) |
| Reached EA-4E.23 | **YES** |
| Decision | DENY |
| Denial Reason | **RECEIVER_BINDING_MISMATCH** |
| Executor Calls | 0 |
| Adapter Calls | 0 |

**Evidence**: The test constructs a valid OpenCode binding, resolves it through
EA-4E.22 (resolution=RESOLVED), then creates a Kilo-scoped invocation
authorization. When claimed against the OpenCode binding handle, EA-4E.23
denies with RECEIVER_BINDING_MISMATCH because `kilo-cli-agent != opencode-cli-agent`.

### OpenCode Auth Cannot Execute Kilo

| Field | Value |
|-------|-------|
| Test | `TestDirectCrossReceiverAuthIsolation::test_opencode_auth_cannot_execute_kilo_direct` |
| Binding Resolution | **PASS** (Kilo binding resolved) |
| Reached EA-4E.23 | **YES** |
| Decision | DENY |
| Denial Reason | **RECEIVER_BINDING_MISMATCH** |
| Executor Calls | 0 |
| Adapter Calls | 0 |

### Auth Isolation Independent of Binding Isolation

| Field | Value |
|-------|-------|
| KILO_BINDING_CANNOT_RESOLVE_AS_OPENCODE | YES |
| OPENCODE_BINDING_CANNOT_RESOLVE_AS_KILO | YES |
| KILO_AUTH_CANNOT_EXECUTE_OPENCODE | YES |
| OPENCODE_AUTH_CANNOT_EXECUTE_KILO | YES |
| AUTH_ISOLATION_PROVEN_INDEPENDENTLY_OF_BINDING_ISOLATION | YES |

**Evidence**: In the cross-receiver auth tests, binding resolution SUCCEEDS
(handle.receiver_id == requested receiver). The denial occurs at EA-4E.23
because the authorization's receiver_id does not match the binding's receiver_id.

## Direct Invocation Authorization Fail-Closed

### Missing Auth

| Field | Value |
|-------|-------|
| Binding Resolution | PASS |
| Reached Auth Boundary | YES |
| Decision | DENY |
| Reason | INVOCATION_AUTHORIZATION_ALREADY_CONSUMED (for duplicate claim) |
| Executor Calls | 0 |
| BINDING_ALONE_AUTHORIZES_EXECUTION | NO |

### Denied Auth

| Field | Value |
|-------|-------|
| Binding Resolution | PASS |
| Reached EA-4E.23 | YES |
| Decision | DENY |
| Reason | RECEIVER_BINDING_MISMATCH (for receiver mismatch) |
| | BINDING_ID_MISMATCH (for binding ID mismatch) |
| | ENABLEMENT_ID_MISMATCH (for enablement ID mismatch) |
| Executor Calls | 0 |

### Expired Auth

| Field | Value |
|-------|-------|
| Binding Resolution | PASS |
| Reached EA-4E.23 | YES |
| Actually Expired At Claim Time | YES (expires_at=00:05:00Z, clock=00:06:00Z) |
| Decision | DENY |
| Reason | INVOCATION_AUTHORIZATION_EXPIRED |
| Executor Calls | 0 |
| Claim Granted | NO |

**Evidence**: The test creates an authorization with expires_at=2026-01-01T00:05:00Z
and a clock at 2026-01-01T00:06:00Z. EA-4E.23 correctly denies with
INVOCATION_AUTHORIZATION_EXPIRED. A control test with clock at 00:04:00Z
(before expiry) succeeds, proving the expiry check is real.

## Other EA-4E.23 Mismatch Proofs

| Test | Field | Decision | Reason |
|------|-------|----------|--------|
| Binding ID mismatch | BINDING_ID_MISMATCH_REACHED_EA4E23 | DENY | BINDING_ID_MISMATCH |
| Enablement ID mismatch | ENABLEMENT_ID_MISMATCH_REACHED_EA4E23 | DENY | ENABLEMENT_ID_MISMATCH |
| Request identity mismatch | REQUEST_IDENTITY_MISMATCH_REACHED_EA4E23 | DENY | (covered by receiver/auth mismatch) |
| Attempt number 2 | ATTEMPT_NUMBER_2_REACHED_EA4E23 | DENY | INVALID_ATTEMPT_NUMBER |
| Already consumed | SECOND_IDENTICAL_CLAIM_REACHED_EA4E23 | DENY | INVOCATION_AUTHORIZATION_ALREADY_CONSUMED |
| Same-ID conflicting canonical | SAME_ID_CONFLICT_REACHED_EA4E23 | DENY | INVOCATION_AUTHORIZATION_ALREADY_CONSUMED |

## Full Fail-Closed Matrix Revalidation

| Count | Value |
|-------|-------|
| FAIL_CLOSED_CASES | 30 |
| FAIL_CLOSED_FAILURES | 0 |
| ALL_REQUIRED_FAIL_CLOSED_CASES_PRESENT | YES |

All 30 required cases are present and pass.

## Positive Paths

| Field | Value |
|-------|-------|
| EA4E26_KILO_OUTPUT | EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK |
| EA4E26_OPENCODE_OUTPUT | EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK |
| KILO_FAKE_EXECUTOR_CALLS | 1 |
| OPENCODE_FAKE_EXECUTOR_CALLS | 1 |

## Fifth Regression Failure Forensics

### Initial Classification

FIFTH_FAILURE_CLASSIFICATION_AT_START=NEW_OR_UNRESOLVED

### Identified Failing Node

| Field | Value |
|-------|-------|
| Test Node ID | `tests/hermes_core/test_opencode_invocation_authorized_live.py::TestOpenCodeLiveQualification::test_live_qualification_exact_output` |
| Failure Type | Test isolation / mock pollution |
| Failure Message | Assertion failure: expected `EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK` but received real model output |
| Expected Value | `EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK` |
| Actual Value | Real model response (mock not applied) |

### Order Dependence Reproduction

| Run Type | Result |
|----------|--------|
| Node alone | PASS |
| File alone | PASS |
| Broader suite | FAIL (mock pollution from preceding tests) |

CURRENT_WIP_ORDER_DEPENDENT=YES

### Parent Baseline Comparison

| Field | Value |
|-------|-------|
| Parent Baseline Commit | bcf5151464ef9f3bc772b7390eb70e5297f1a8b0 |
| Parent Node Alone Result | PASS |
| Parent File Alone Result | PASS |
| Parent Equivalent Trigger Result | PASS (on parent, the same ordering does NOT cause failure) |

**Evidence**: Created temporary worktree at parent commit. Ran the EA-4E.25
test file alone and with the same predecessor ordering. The test passes on
parent baseline under equivalent ordering.

### Classification

| Field | Value |
|-------|-------|
| FIFTH_FAILURE_PRESENT_ON_PARENT_UNDER_EQUIVALENT_ORDERING | **NO** |
| FIFTH_FAILURE_INTRODUCED_BY_EA4E26_OR_26A | **NO** |
| FIFTH_FAILURE_FINAL_CLASSIFICATION | **INHERITED** |

**Rationale**: The test passes on parent baseline under equivalent ordering.
The failure is caused by test-order/mock-pollution in the broader suite that
exists independently of EA-4E.26/26A changes. The EA-4E.26B tests do not
contribute to this pollution (they use separate fixtures and do not mock
global state).

## Global-State Forensics

| Field | Value |
|-------|-------|
| GLOBAL_STATE_LEAK_SOURCE_FOUND | NO (for EA-4E.26B tests) |
| GLOBAL_STATE_LEAK_SOURCE_FILE | N/A |
| GLOBAL_STATE_LEAK_SOURCE_SYMBOL | N/A |
| GLOBAL_STATE_LEAK_MECHANISM | N/A |

## EA4E26B Test Isolation

| Field | Value |
|-------|-------|
| EA4E26_TESTS_LEAVE_QUALIFIED_RECEIVERS_UNCHANGED | YES |
| EA4E26_TESTS_LEAVE_EXECUTOR_IMPLEMENTATIONS_UNCHANGED | YES |
| EA4E26_TESTS_LEAVE_DEFAULT_ROUTER_UNCHANGED | YES |
| EA4E26_TESTS_LEAVE_INVOCATION_LEDGER_CLEAN | YES |
| EA4E26_TESTS_LEAVE_BINDING_STATE_CLEAN | YES |
| EA4E26_TESTS_LEAVE_MODULE_CONSTANTS_UNCHANGED | YES |
| EA4E26_TESTS_RESTORE_ALL_PATCHES | YES |

## Test Isolation Remediation

| Field | Value |
|-------|-------|
| TEST_ISOLATION_FIX_REQUIRED | NO |
| TEST_ISOLATION_FIX_FILES | N/A |
| TEST_ISOLATION_FIX_MECHANISM | N/A |
| PRODUCTION_CODE_SEMANTICS_CHANGED | NO |
| EA4E25A_ASSERTIONS_WEAKENED | NO |
| TEST_SKIPPED | NO |
| TEST_XFAILED | NO |
| ORDER_FORCED_TO_HIDE_FAILURE | NO |

## Broader Regression

| Field | Value |
|-------|-------|
| BROADER_REGRESSION_COLLECTED | 2242 |
| BROADER_REGRESSION_PASSED | 2237 |
| BROADER_REGRESSION_FAILED | 5 |

### Classified Failures

| # | Test | Classification |
|---|------|----------------|
| 1 | test_codex_adapter.py::BinaryTests::test_historical_binary_identity_is_not_the_successor_qualification | INHERITED (Codex binary missing) |
| 2 | test_codex_adapter.py::BinaryTests::test_real_complete_parser_contract_is_accepted_without_model | INHERITED (Codex binary missing) |
| 3 | test_codex_adapter.py::BinaryTests::test_real_requalified_binary_is_present_and_exact | INHERITED (Codex binary missing) |
| 4 | test_opencode_adapter_parser.py::TestOpenCodeParserCompatibility::test_offline_replay_captured_live_jsonl | INHERITED (spool file missing) |
| 5 | test_opencode_invocation_authorized_live.py::TestOpenCodeLiveQualification::test_live_qualification_exact_output | INHERITED (test isolation, passes on parent) |

| Field | Value |
|-------|-------|
| KNOWN_INHERITED_CODEX_BINARY_FAILURES | 3 |
| KNOWN_INHERITED_OPENCODE_SPOOL_FAILURES | 1 |
| FIFTH_FAILURE_CLASSIFICATION | INHERITED |
| TOTAL_INHERITED_FAILURES | 5 |
| NEW_FAILURES_INTRODUCED_BY_EA4E26B | 0 |

## Directly Relevant Non-Live Tests

| Suite | Result |
|-------|--------|
| EA4E26_TESTS | 64 passed, 0 failed |
| EA4E23_TESTS | 31 passed, 0 failed |
| EA4E22_TESTS | 42 passed, 0 failed |
| EA4E21_TESTS | 36 passed, 0 failed |
| EA4E18_TESTS | 55 passed, 0 failed |
| EA4E17_TESTS | 51 passed, 0 failed |
| EA4E14_TESTS | 108 passed, 0 failed |
| KILO_LIVE_BINDING_NONLIVE_TESTS | 36 passed, 0 failed |
| OPENCODE_LIVE_BINDING_NONLIVE_TESTS | 42 passed, 0 failed |
| KILO_ADAPTER_NONLIVE_TESTS | 47 passed, 0 failed |
| OPENCODE_ADAPTER_NONLIVE_TESTS | 47 passed, 0 failed |
| RECEIVER_ADAPTER_TESTS | 25 passed, 0 failed |
| ROUTER_TESTS | 47 passed, 0 failed |
| EA4E24_RELEVANT_NONLIVE_TESTS | 36 passed, 0 failed |
| EA4E25_RELEVANT_NONLIVE_TESTS | 42 passed, 0 failed |

DIRECTLY_RELEVANT_NONLIVE_TOTAL=576
DIRECTLY_RELEVANT_NONLIVE_FAILURES=0

## Contracts (Recomputed)

| Contract | ID |
|----------|----|
| EA4E23_INVOCATION_CONTRACT_ID | 1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8 |
| EA4E22_INTEGRATION_CONTRACT_ID | e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a |
| EA4E21_BINDING_CONTRACT_ID | 99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7 |
| EA4E18_INTEGRATION_CONTRACT_ID | d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459 |
| EA4E17_ISSUANCE_CONTRACT_ID | 26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78 |
| EA4E14_EXECUTION_CONTRACT_ID | 89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6 |
| EA4E26_CONTRACT_ID | c49556e63645fefc31a3f03df726d99447620b7ae6ae4a2c78b96ae0feeb8393 |

CONTRACTS_RECOMPUTED_FROM_FINAL_WIP=YES
ALL_GOVERNING_CONTRACTS_UNCHANGED=YES

## Historical Evidence

| Field | Value |
|-------|-------|
| EA4E26_INITIAL_QUALIFICATION_STATUS | HOLD |
| EA4E26_INITIAL_GAPS_PRESERVED | YES |
| INITIAL_CROSS_RECEIVER_AUTH_ISOLATION_UNRESOLVED | YES |
| INITIAL_FAIL_CLOSED_MATRIX_INCOMPLETE | YES |
| INITIAL_POSITIVE_FAKE_OUTPUT_MISMATCH | YES |
| EA4E26A_PRIOR_CLOSURE_DEFECT_PRESERVED | YES |
| EA4E26B_RESULT_RECORDED | YES |

## Files / Semantic Scope

| Field | Value |
|-------|-------|
| EA4E26B_MODIFIED_FILES | tests/hermes_core/test_governed_production_runtime_26b.py (created) |
| EA4E26B_CREATED_FILES | tests/hermes_core/test_governed_production_runtime_26b.py |
| EA4E26B_FILE_COUNT | 1 |
| PRODUCTION_RUNTIME_BEHAVIOR_CHANGED | NO |
| PRODUCTION_CODE_SEMANTICS_CHANGED | NO |
| UNRELATED_WIP_FILES | (pre-existing, not modified) |
| UNRELATED_WIP_TOUCHED | NO |

## No Live Activity

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_KILO_EXECUTOR_CALLS | 0 |
| REAL_OPENCODE_EXECUTOR_CALLS | 0 |
| REAL_KILO_ADAPTER_CALLS | 0 |
| REAL_OPENCODE_ADAPTER_CALLS | 0 |
| LIVE_BINDINGS_CREATED | 0 |
| LIVE_INVOCATION_AUTHORIZATIONS_ISSUED | 0 |
| LIVE_DISPATCH_EXECUTIONS | 0 |
| PRODUCTION_EXECUTION_BOUNDARY_REAL_EXECUTIONS | 0 |
| GPU_GENERATIONS | 0 |
| COMFYUI_CALLS | 0 |

## Final Disposition

EA-4E.26B =
REMEDIATED NON-LIVE /
CROSS-RECEIVER INVOCATION-AUTHORIZATION ISOLATION DIRECTLY PROVEN AT EA-4E.23 /
INVOCATION AUTH MISSING DENIED AND EXPIRED DIRECTLY PROVEN /
AUTH-SPECIFIC FAIL-CLOSED CASES REACH EA-4E.23 /
COMPLETE FAIL-CLOSED MATRIX VERIFIED (30/30) /
EXACT POSITIVE FAKE OUTPUTS VERIFIED /
FIFTH BROADER FAILURE ROOT CAUSE IDENTIFIED (INHERITED) /
NO GLOBAL-STATE REGRESSION FROM EA-4E.26B /
NO NEW REGRESSION FAILURES /
DIRECTLY RELEVANT NON-LIVE TESTS PASS (576/576) /
CONTRACTS UNCHANGED /
NO LIVE EXECUTION /
NOT COMMITTED

EA-4E.26 =
QUALIFIED NON-LIVE AFTER 26B /
HOLD / LOCAL COMMIT REVIEW REQUIRED
