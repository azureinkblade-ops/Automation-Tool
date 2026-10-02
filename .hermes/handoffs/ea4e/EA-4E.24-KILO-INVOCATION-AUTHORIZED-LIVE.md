# EA-4E.24A Kilo Real-Executor Identity / Live Accounting Forensic Remediation

## Purpose

Investigate and remediate the defects exposed by EA-4E.24 without performing another live Kilo execution.

## Governing Checkpoint

| Field | Value |
|-------|-------|
| Local HEAD | `74dffa9045264ab499a6774abc9d02b2415a8078` |
| Remote HEAD | `74dffa9045264ab499a6774abc9d02b2415a8078` |
| Branch | `feature/ea4f-regional-hand-repair-pilot` |
| Local ahead | 0 |
| Local behind | 0 |
| Staged before | 0 |

## Fresh Repository Verification

```
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=74dffa9045264ab499a6774abc9d02b2415a8078
GOVERNING_REMOTE_HEAD=74dffa9045264ab499a6774abc9d02b2415a8078
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

## Baseline (Pre-Remediation)

| Field | Value |
|-------|-------|
| PRE_REMEDIATION_EA4E23_TESTS | 38 passed / 0 failed |
| PRE_REMEDIATION_EA4E24_NONLIVE_TESTS | 26 passed / 0 failed |

---

## IDENTITY DEFECT INVESTIGATION

### Defect Found

| Field | Value |
|-------|-------|
| QUALIFIED_KILO_EXECUTOR_IDENTITY | `RealKiloProductionExecutor` |
| REAL_KILO_EXECUTOR_REPORTED_IDENTITY | `real-kilo-production-executor` (BEFORE remediation) |
| IDENTITY_MATCH_BEFORE_REMEDIATION | NO |
| IDENTITY_MASKING_WRAPPER_ACCEPTABLE | NO |
| IDENTITY_MASKING_WRAPPER_RETAINED_AS_FIX | NO |

### Authoritative Identity Investigation

| Field | Value |
|-------|-------|
| EA4E21_CANONICAL_EXECUTOR_IDENTITY_SOURCE | `QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]["executor_identity"]` in `production_executor_binding.py` |
| REAL_EXECUTOR_IDENTITY_SOURCE | `RealKiloProductionExecutor.executor_id` property in `kilo_live_binding.py` |
| PRIOR_LIVE_QUALIFICATION_IDENTITY_SOURCE | EA-4E.19 evidence document references `RealKiloProductionExecutor` as the qualified identity |
| IDENTITY_DEFECT_CLASSIFICATION | `REAL_EXECUTOR_PROPERTY_WRONG` |

### Classification Explanation

The EA-4E.21 qualified binding material correctly specifies `executor_identity: "RealKiloProductionExecutor"`. This is the canonical identity established by the frozen EA-4E.21 contract. The real executor implementation in `kilo_live_binding.py` incorrectly reported `executor_id: "real-kilo-production-executor"` (lowercase, hyphenated), which did not match the canonical identity.

The EA-4E.22 resolver's identity validation (`executor.executor_id != handle.executor_identity`) correctly rejected this mismatch. The EA-4E.24 harness circumvented this by wrapping the real executor and overriding `executor_id` to return the canonical string — masking the defect rather than fixing it.

### Remediation Applied

**File modified:** `tools/hermes_core/kilo_live_binding.py`

**Change:** Narrow correction to `RealKiloProductionExecutor.executor_id` property:

```python
# BEFORE (wrong):
@property
def executor_id(self) -> str:
    return "real-kilo-production-executor"

# AFTER (correct):
@property
def executor_id(self) -> str:
    return "RealKiloProductionExecutor"
```

This aligns the real executor's reported identity with the already-frozen EA-4E.21 canonical identity. No contract roll is required.

### Post-Remediation Identity Verification

| Field | Value |
|-------|-------|
| CANONICAL_KILO_EXECUTOR_IDENTITY | `RealKiloProductionExecutor` |
| REAL_EXECUTOR_REPORTS_CANONICAL_IDENTITY | YES |
| EA4E21_QUALIFIED_IDENTITY_MATCHES_CANONICAL | YES |
| EA4E22_RESOLVER_REQUIRES_CANONICAL_IDENTITY | YES |
| EA4E21_CONTRACT_CHANGE_REQUIRED | NO |
| REAL_KILO_EXECUTOR_WRAPPER_REQUIRED | NO |
| EXECUTOR_IDENTITY_OVERRIDDEN_BY_HARNESS | NO |
| EA4E22_IDENTITY_VALIDATION_BYPASSED | NO |

---

## LIVE ACCOUNTING DEFECT

### Defect Found

The EA-4E.24 harness used a wrapper that self-reported adapter call count, process start count, and model invocation count by incrementing counters before delegating to the real executor. These were not independently observed live facts.

| Field | Value |
|-------|-------|
| SELF_REPORTED_WRAPPER_ADAPTER_COUNT_ACCEPTABLE | NO |
| SELF_REPORTED_WRAPPER_PROCESS_COUNT_ACCEPTABLE | NO |
| SELF_REPORTED_WRAPPER_MODEL_COUNT_ACCEPTABLE | NO |

### Remediated Accounting Sources

| Field | Value |
|-------|-------|
| ADAPTER_CALL_COUNT_SOURCE | `KiloAdapter.execute()` invocation boundary — one call per executor `execute()` call |
| PROCESS_START_COUNT_SOURCE | `result.pid > 0` from `ExecutionOutcome` (set by `KiloAdapter.execute()`) |
| MODEL_INVOCATION_COUNT_SOURCE | By frozen Kilo transport contract: one adapter call = one model task |
| COUNTERS_INCREMENT_ONLY_AFTER_OR_AT_ACTUAL_EVENT | YES |
| COUNTERS_ARE_NOT_SYNTHETIC_WRAPPER_GUESSES | YES |

### Evidence Chain

1. **Adapter call = Executor call**: `RealKiloProductionExecutor.execute()` creates exactly one `KiloAdapter` and calls `adapter.execute()` once.
2. **Process start = `result.pid > 0`**: `KiloAdapter.execute()` sets `process_started = result.pid > 0` based on actual subprocess PID.
3. **Model invocation = Adapter call**: By frozen Kilo transport contract (`kilo run --format json --pure --agent ... --model ...`), each adapter invocation performs exactly one model task.

### Instrumentation Failure Semantics

| Field | Value |
|-------|-------|
| EXECUTOR_ENTERED_ADAPTER_NOT_CALLED_ACCOUNTING | PASS (tested via `NoAdapterExecutor` fake) |
| ADAPTER_CALLED_PROCESS_NOT_STARTED_ACCOUNTING | PASS (tested via mocked `pid=0`) |
| PROCESS_STARTED_EXECUTION_FAILED_ACCOUNTING | PASS (tested via mocked `returncode=1`) |

---

## LIVE CLOCK / TEMPORAL AUTHORIZATION REVIEW

### Defect Found

| Field | Value |
|-------|-------|
| EA4E24_LIVE_USED_FIXED_QUALIFICATION_CLOCK | YES |

The original harness used a fixed qualification clock (`2026-01-01T00:00:00Z`) for both non-live tests and live authorization windows. While appropriate for deterministic non-live tests, this is not sufficient evidence that a live runtime authorization window uses actual current-time semantics.

### Remediation

Introduced `LiveClock` class with dual-mode operation:

| Field | Value |
|-------|-------|
| LIVE_CLOCK_SOURCE | `LiveClock()` — uses `datetime.now(timezone.utc)` |
| LIVE_AUTHORIZATION_ISSUED_AT_SOURCE | `live_clock.now_iso()` |
| LIVE_AUTHORIZATION_EXPIRES_AT_SOURCE | `live_clock.now_plus_seconds(300)` |
| LIVE_CLOCK_INJECTED | YES |
| NONLIVE_TEST_CLOCK_REMAINS_DETERMINISTIC | YES |

The harness now accepts a `use_live_clock` parameter:
- `use_live_clock=False` (default): Uses fixed deterministic qualification clock for non-live tests
- `use_live_clock=True`: Uses actual runtime time for live qualification

---

## QUALIFICATION HARNESS REMEDIATION

### Changes Made

| Field | Value |
|-------|-------|
| EA4E24_HARNESS_REAL_EXECUTOR_DIRECT_BINDING | YES |
| EA4E24_HARNESS_IDENTITY_WRAPPER_REMOVED | YES |
| EA4E24_HARNESS_ACTUAL_EVENT_ACCOUNTING | YES |
| EA4E24_HARNESS_LIVE_CLOCK_INJECTION | YES |

### Non-Live Proof of Complete Path

| Field | Value |
|-------|-------|
| NONLIVE_COMPLETE_PATH_WITHOUT_IDENTITY_WRAPPER | PASS |
| NONLIVE_EA4E22_REAL_IDENTITY_MATCH_PROOF | PASS |
| NONLIVE_ACCOUNTING_INSTRUMENTATION_PROOF | PASS |
| NONLIVE_LIVE_CLOCK_INJECTION_PROOF | PASS |

---

## NO SECOND LIVE RUN

| Field | Value |
|-------|-------|
| EA4E24_ORIGINAL_LIVE_RESULT_PRESERVED | YES |
| EA4E24_SECOND_LIVE_RUN_PERFORMED | NO |
| NEW_KILO_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |

The prior single live attempt (EA-4E.24) is historical evidence only and was not repeated under this authorization.

---

## UPSTREAM CONTRACTS (VERIFIED UNCHANGED)

| Field | Value |
|-------|-------|
| EA4E23_INVOCATION_CONTRACT_ID | `1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8` |
| EA4E22_INTEGRATION_CONTRACT_ID | `e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a` |
| EA4E21_BINDING_CONTRACT_ID | `99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7` |
| EA4E18_INTEGRATION_CONTRACT_ID | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |
| EA4E17_ISSUANCE_CONTRACT_ID | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E14_EXECUTION_CONTRACT_ID | `89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6` |

---

## TEST RESULTS

| Field | Value |
|-------|-------|
| EA4E23_TESTS | 38 passed / 0 failed |
| EA4E24_NONLIVE_TESTS | 34 passed / 0 failed |
| KILO_LIVE_BINDING_NONLIVE_TESTS | 23 passed / 0 failed |
| KILO_ADAPTER_NONLIVE_TESTS | 121 passed / 0 failed |
| NONLIVE_REGRESSION_TOTAL | 226 passed / 0 failed |
| NONLIVE_REGRESSION_FAILURES | 0 |

---

## LIVE ACCOUNTING FOR EA-4E.24A

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_KILO_EXECUTOR_LIVE_CALLS | 0 |
| REAL_OPENCODE_EXECUTOR_LIVE_CALLS | 0 |
| REAL_KILO_ADAPTER_LIVE_CALLS | 0 |
| REAL_OPENCODE_ADAPTER_LIVE_CALLS | 0 |
| LIVE_BINDINGS_CREATED | 0 |
| LIVE_INVOCATION_AUTHORIZATIONS_ISSUED | 0 |
| LIVE_DISPATCH_EXECUTIONS | 0 |
| GPU_GENERATIONS | 0 |
| COMFYUI_CALLS | 0 |

---

## REPOSITORY

| Field | Value |
|-------|-------|
| UNRELATED_WIP_TOUCHED | NO |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## FILES MODIFIED

1. **`tools/hermes_core/kilo_live_binding.py`** — Narrow correction: `RealKiloProductionExecutor.executor_id` now returns `"RealKiloProductionExecutor"` (canonical identity)
2. **`tools/hermes_core/kilo_invocation_authorized_live.py`** — Complete rewrite:
   - Removed `RealKiloProductionExecutorWrapper` class
   - Direct binding of `RealKiloProductionExecutor`
   - Added `LiveClock` class for dual-mode clock operation
   - Accounting derived from actual event sources (adapter call = executor call, process start = `result.pid > 0`, model invocation = adapter call by frozen transport contract)
3. **`tests/hermes_core/test_kilo_invocation_authorized_live.py`** — Complete rewrite with 34 tests covering:
   - Canonical executor identity matches EA-4E.21 identity
   - No wrapper identity override
   - EA-4E.22 resolves canonical Kilo identity
   - Wrong executor identity still rejects
   - Accounting derives from real event spies
   - Executor entered but adapter not called
   - Adapter called but process not started
   - Process started but downstream failure
   - Model/task invocation counter exactness
   - Live clock collaborator used in live mode
   - Deterministic fixed clock retained in non-live mode
   - Authorization issued/expires based on injected live clock
   - No retry
   - No fallback
   - No failover
   - No second live execution
4. **`.hermes/handoffs/ea4e/EA-4E.24-KILO-INVOCATION-AUTHORIZED-LIVE.md`** — Updated evidence document

---

## FINAL DISPOSITION

```
EA-4E.24A = REMEDIATED / CANONICAL KILO EXECUTOR IDENTITY ALIGNED /
IDENTITY-MASKING WRAPPER REMOVED / ACTUAL EVENT ACCOUNTING QUALIFIED /
LIVE CLOCK INJECTION QUALIFIED / NO SECOND LIVE EXECUTION /
ALL NON-LIVE TESTS PASS / NOT COMMITTED

EA-4E.24 = HOLD / PRIOR LIVE OUTPUT PASS PRESERVED /
GOVERNED LIVE QUALIFICATION REQUIRES NEW SEPARATELY AUTHORIZED
SINGLE-SHOT AFTER REMEDIATION / NOT COMMITTED
```

## Architecture Invariant Preserved

```
ROUTING != ISSUANCE != AUTHORIZATION != ACTIVATION != BINDING != INVOCATION AUTHORIZATION != EXECUTION
```

Specifically:
```
ROUTE_SELECTED != EXECUTOR_BOUND
EXECUTOR_BOUND != INVOCATION_AUTHORIZED
INVOCATION_AUTHORIZED != RECEIVER_EXECUTED
```

## No Live Execution Performed

No live receiver execution was authorized by or performed under EA-4E.24A. All verification was done through non-live tests using fake executors, spies, and mocks.
