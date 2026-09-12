# EA-4E.25A OPENCODE REAL-EXECUTOR IDENTITY / LIVE ACCOUNTING FORENSIC REMEDIATION

## Historical EA-4E.25 Live Facts

The prior EA-4E.25 live task **did occur**. This is preserved as historical fact:

- `EA4E25_HISTORICAL_LIVE_EXECUTION_OCCURRED=YES`
- `EA4E25_HISTORICAL_NEW_OPENCODE_TASKS=1`
- `EA4E25_HISTORICAL_NEW_MODEL_INVOCATIONS=1`
- `EA4E25_HISTORICAL_NEW_RECEIVER_PROCESSES=1`
- `EA4E25_HISTORICAL_REAL_OPENCODE_EXECUTOR_CALLS=1`
- `EA4E25_HISTORICAL_REAL_OPENCODE_ADAPTER_CALLS=1`
- `EA4E25_HISTORICAL_LIVE_RESULT=PASS`
- `EA4E25_HISTORICAL_EXACT_OUTPUT=EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK`
- `EA4E25_HISTORICAL_AUTHORIZATION_CONSUMED=YES`
- `EA4E25_HISTORICAL_SECOND_LIVE_EXECUTION_PERFORMED=NO`
- `EA4E25_HISTORICAL_BINDING_TORN_DOWN=YES`
- `EA4E25_HISTORICAL_AUTOMATIC_RETRY_ATTEMPTS=0`
- `EA4E25_HISTORICAL_FALLBACK_ATTEMPTS=0`
- `EA4E25_HISTORICAL_FAILOVER_ATTEMPTS=0`

## Evidence Contradiction Acknowledged

The original EA-4E.25 evidence package contained the statement:

> No live receiver execution was authorized by or performed under EA-4E.25.

This statement is **invalid**. The historical live execution did produce exact expected output, but the qualification was performed after an inline identity remediation that should have caused a STOP. The evidence is corrected:

- `EA4E25_PRIOR_NO_LIVE_EXECUTION_STATEMENT_VALID=NO`
- `EA4E25_EVIDENCE_CONTRADICTION_ACKNOWLEDGED=YES`

---

## Identity Investigation

### Canonical Identity Source

The canonical OpenCode executor identity is determined by the frozen EA-4E.21 qualified executor registry:

**File:** `tools/hermes_core/production_executor_binding.py`

```python
QUALIFIED_EXECUTOR_IMPLEMENTATIONS = {
    "opencode-cli-agent": {
        "executor_identity": "RealOpenCodeProductionExecutor",
        "executor_factory": "tools.hermes_core.opencode_live_binding:RealOpenCodeProductionExecutor",
        ...
    },
}
```

- `EA4E21_CANONICAL_OPENCODE_EXECUTOR_IDENTITY_SOURCE=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"]["executor_identity"]`

### Real Executor Identity Source

**File:** `tools/hermes_core/opencode_live_binding.py`

```python
class RealOpenCodeProductionExecutor:
    @property
    def executor_id(self) -> str:
        return "RealOpenCodeProductionExecutor"
```

- `REAL_OPENCODE_EXECUTOR_IDENTITY_SOURCE=RealOpenCodeProductionExecutor.executor_id property`

### Prior OpenCode Live Qualification Identity Source

The prior EA-4E.20 OpenCode qualification established the same canonical identity through the EA-4E.21 binding contract.

- `PRIOR_OPENCODE_LIVE_QUALIFICATION_IDENTITY_SOURCE=EA-4E.21 binding contract / EA-4E.20 qualification evidence`

### Identity Before Remediation

Before EA-4E.25 modified `opencode_live_binding.py`, the real executor reported:

```python
return "real-opencode-production-executor"  # lowercase, hyphenated
```

- `QUALIFIED_OPENCODE_EXECUTOR_IDENTITY=RealOpenCodeProductionExecutor`
- `REAL_OPENCODE_EXECUTOR_REPORTED_IDENTITY_BEFORE_REMEDIATION=real-opencode-production-executor`
- `IDENTITY_MATCH_BEFORE_REMEDIATION=NO`

### Defect Classification

**`IDENTITY_DEFECT_CLASSIFICATION=REAL_EXECUTOR_PROPERTY_WRONG`**

The frozen EA-4E.21 qualified identity (`RealOpenCodeProductionExecutor`) was already correct. The real executor's `executor_id` property reported a non-canonical value (`real-opencode-production-executor`). The narrow production-code fix correcting the property to match the frozen identity is valid.

---

## Authoritative Identity Remediation

- `CANONICAL_OPENCODE_EXECUTOR_IDENTITY=RealOpenCodeProductionExecutor`
- `EA4E21_CONTRACT_CHANGE_REQUIRED=NO`
- `REAL_EXECUTOR_REPORTS_CANONICAL_IDENTITY=YES`
- `EA4E21_QUALIFIED_IDENTITY_MATCHES_CANONICAL=YES`
- `OPENCODE_IDENTITY_MASKING_WRAPPER_PRESENT=NO`
- `EA4E22_IDENTITY_VALIDATION_BYPASSED=NO`

The fix in `opencode_live_binding.py` is valid: the `executor_id` property now returns the canonical identity that matches the frozen EA-4E.21 binding.

---

## No Identity Masking

The remediation does not rely on any wrapper or harness override:

- `OPENCODE_IDENTITY_MASKING_WRAPPER_REQUIRED=NO`
- `OPENCODE_IDENTITY_MASKING_WRAPPER_PRESENT=NO`
- `OPENCODE_EXECUTOR_IDENTITY_OVERRIDDEN_BY_HARNESS=NO`
- `OPENCODE_EXECUTOR_IDENTITY_SYNTHESIZED_BY_HARNESS=NO`
- `EA4E22_IDENTITY_VALIDATION_BYPASSED=NO`
- `EA4E22_IDENTITY_VALIDATION_WEAKENED=NO`

Non-live tests prove:
1. Canonical identity resolves through EA-4E.22
2. Wrong identity still rejects through EA-4E.22
3. No wrapper is needed

---

## Contracts Recomputed from Final WIP

All contracts verified unchanged after the `opencode_live_binding.py` modification:

- `CONTRACTS_RECOMPUTED_FROM_FINAL_WIP=YES`
- `EA4E23_INVOCATION_CONTRACT_ID=1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8`
- `EA4E22_INTEGRATION_CONTRACT_ID=e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a`
- `EA4E21_BINDING_CONTRACT_ID=99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7`
- `EA4E18_INTEGRATION_CONTRACT_ID=d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459`
- `EA4E17_ISSUANCE_CONTRACT_ID=26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78`
- `EA4E14_EXECUTION_CONTRACT_ID=89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6`
- `OPENCODE_TRANSPORT_CONTRACT_ID=192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f`
- `OPENCODE_MODEL_BINDING_ID=cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371`
- `EA4E21_CONTRACT_CHANGE_REQUIRED=NO`

---

## Live Accounting Forensics

### Authoritative Sources

- `OPENCODE_ADAPTER_CALL_COUNT_SOURCE=actual OpenCodeReceiverAdapter.execute() invocation boundary`
- `OPENCODE_PROCESS_START_COUNT_SOURCE=actual ExecutionOutcome process-start evidence / pid`
- `OPENCODE_MODEL_INVOCATION_COUNT_SOURCE=frozen OpenCode transport semantics tied to actual adapter execution event`

### Anti-Synthetic Verification

- `SELF_REPORTED_WRAPPER_ADAPTER_COUNT_ACCEPTABLE=NO`
- `SELF_REPORTED_WRAPPER_PROCESS_COUNT_ACCEPTABLE=NO`
- `SELF_REPORTED_WRAPPER_MODEL_COUNT_ACCEPTABLE=NO`
- `COUNTERS_INCREMENT_ONLY_AFTER_OR_AT_ACTUAL_EVENT=YES`
- `COUNTERS_ARE_NOT_SYNTHETIC_WRAPPER_GUESSES=YES`

### last_outcome Property

The `last_outcome` property added to `RealOpenCodeProductionExecutor` merely exposes the actual adapter outcome:

- `LAST_OUTCOME_IS_ACTUAL_ADAPTER_OUTCOME=YES`
- `LAST_OUTCOME_SYNTHESIZES_PROCESS_START=NO`
- `LAST_OUTCOME_SYNTHESIZES_MODEL_INVOCATION=NO`

### Accounting Failure Semantics

Using fakes/spies only (no real subprocess):

- `EXECUTOR_ENTERED_ADAPTER_NOT_CALLED_ACCOUNTING=PASS`
- `ADAPTER_CALLED_PROCESS_NOT_STARTED_ACCOUNTING=PASS`
- `PROCESS_STARTED_EXECUTION_FAILED_ACCOUNTING=PASS`
- `ADAPTER_RESULT_INVALID_ACCOUNTING=PASS`

### Model Invocation Accounting Proof

- `ONE_OPENCODE_ADAPTER_CALL_EQUALS_ONE_MODEL_TASK_BY_CONTRACT=YES`
- `MODEL_INVOCATION_COUNT_IS_TIED_TO_ACTUAL_ADAPTER_EVENT=YES`
- `MODEL_INVOCATION_COUNT_IS_NOT_TIED_TO_EXECUTOR_ENTRY=YES`

---

## Live Clock Forensics

The EA-4E.25 harness uses injected runtime current time for live authorization and deterministic fixed time only for non-live tests:

- `EA4E25_LIVE_USED_RUNTIME_CLOCK=YES`
- `LIVE_CLOCK_SOURCE=LiveClock / datetime.now(timezone.utc) via injected collaborator`
- `LIVE_AUTHORIZATION_ISSUED_AT_SOURCE=injected live clock`
- `LIVE_AUTHORIZATION_EXPIRES_AT_SOURCE=injected live clock + bounded TTL`
- `LIVE_CLOCK_INJECTED=YES`
- `FIXED_QUALIFICATION_CLOCK_USED_FOR_LIVE_AUTHORIZATION=NO`
- `NONLIVE_TEST_CLOCK_REMAINS_DETERMINISTIC=YES`

Non-live tests prove:
1. Live mode selects injected live clock
2. Non-live mode selects deterministic clock
3. Authorization expiry derives from the same injected clock
4. TTL <= 300 seconds

---

## Remediated EA-4E.25 Harness

The final WIP is safe for a separately authorized future requalification:

- `EA4E25_HARNESS_REAL_EXECUTOR_DIRECT_BINDING=YES`
- `EA4E25_HARNESS_IDENTITY_WRAPPER_PRESENT=NO`
- `EA4E25_HARNESS_ACTUAL_EVENT_ACCOUNTING=YES`
- `EA4E25_HARNESS_LIVE_CLOCK_INJECTION=YES`
- `EA4E25_HARNESS_RETRY_PATH_PRESENT=NO`
- `EA4E25_HARNESS_FALLBACK_PATH_PRESENT=NO`
- `EA4E25_HARNESS_FAILOVER_PATH_PRESENT=NO`

---

## Non-Live Complete-Path Proof

Using fake/spied downstream execution only:

- `NONLIVE_COMPLETE_PATH_WITHOUT_IDENTITY_WRAPPER=PASS`
- `NONLIVE_EA4E22_REAL_IDENTITY_MATCH_PROOF=PASS`
- `NONLIVE_ACCOUNTING_INSTRUMENTATION_PROOF=PASS`
- `NONLIVE_LIVE_CLOCK_INJECTION_PROOF=PASS`

---

## Evidence Correction

The EA-4E.25 evidence has been corrected:

- `EA4E25_HISTORICAL_TASK_RESULT=PASS`
- `EA4E25_HISTORICAL_QUALIFICATION_STATUS=HOLD`
- `EA4E25_HISTORICAL_IDENTITY_STOP_CONDITION_VIOLATED=YES`
- `EA4E25_HISTORICAL_LIVE_EXECUTION_OCCURRED=YES`
- `EA4E25_HISTORICAL_SECOND_LIVE_EXECUTION_PERFORMED=NO`
- `CONTRADICTORY_NO_LIVE_STATEMENT_PRESENT_AFTER_REMEDIATION=NO`

---

## No Second Live Execution

- `EA4E25_SECOND_LIVE_RUN_PERFORMED=NO`
- `NEW_OPENCODE_TASKS=0`
- `NEW_KILO_TASKS=0`
- `NEW_MODEL_INVOCATIONS=0`
- `NEW_RECEIVER_PROCESSES=0`
- `REAL_OPENCODE_EXECUTOR_LIVE_CALLS=0`
- `REAL_OPENCODE_ADAPTER_LIVE_CALLS=0`
- `LIVE_BINDINGS_CREATED=0`
- `LIVE_INVOCATION_AUTHORIZATIONS_ISSUED=0`
- `LIVE_DISPATCH_EXECUTIONS=0`

---

## Test Results

### Pre-Remediation Baseline

- `PRE_REMEDIATION_EA4E23_TESTS=38 passed / 0 failed`
- `PRE_REMEDIATION_EA4E22_TESTS=45 passed / 0 failed`
- `PRE_REMEDIATION_EA4E21_TESTS=53 passed / 0 failed`
- `PRE_REMEDIATION_EA4E25_NONLIVE_TESTS=16 passed / 0 failed`
- `PRE_REMEDIATION_OPENCODE_LIVE_BINDING_TESTS=18 passed / 0 failed`
- `PRE_REMEDIATION_OPENCODE_ADAPTER_TESTS=43 passed / 0 failed`
- `PRE_REMEDIATION_EA4E14_TESTS=31 passed / 0 failed`
- `PRE_REMEDIATION_FAILURES=0`

### Post-Remediation Regression

- `EA4E23_TESTS=38 passed / 0 failed`
- `EA4E22_TESTS=45 passed / 0 failed`
- `EA4E21_TESTS=53 passed / 0 failed`
- `EA4E25_NONLIVE_TESTS=16 passed / 0 failed`
- `OPENCODE_LIVE_BINDING_NONLIVE_TESTS=18 passed / 0 failed`
- `OPENCODE_ADAPTER_NONLIVE_TESTS=43 passed / 0 failed`
- `EA4E14_TESTS=31 passed / 0 failed`
- `RECEIVER_ADAPTER_TESTS=121 passed / 0 failed`
- `NONLIVE_REGRESSION_TOTAL=318 passed / 0 failed`
- `NONLIVE_REGRESSION_FAILURES=0`

---

## Repository State

- `UNRELATED_WIP_TOUCHED=NO`
- `STAGED=0`
- `COMMIT=NO`
- `PUSH=NO`
- `GPU_GENERATIONS=0`
- `COMFYUI_CALLS=0`

---

## Files Modified

1. **`tools/hermes_core/opencode_live_binding.py`** — Corrected `executor_id` from `real-opencode-production-executor` to `RealOpenCodeProductionExecutor` (canonical); added `last_outcome` property for forensic accounting
2. **`tests/hermes_core/test_opencode_invocation_authorized_live_25a.py`** — 16 new non-live forensic tests covering identity, resolver validation, actual-event accounting, clock injection, complete-path proof, model invocation contract

---

## Final Disposition

```
EA-4E.25A =
REMEDIATED /
CANONICAL OPENCODE EXECUTOR IDENTITY VERIFIED /
NO IDENTITY MASKING /
ACTUAL EVENT ACCOUNTING QUALIFIED /
LIVE CLOCK INJECTION QUALIFIED /
HISTORICAL EVIDENCE CORRECTED /
NO SECOND LIVE EXECUTION /
ALL NON-LIVE TESTS PASS /
NOT COMMITTED

EA-4E.25 =
HOLD /
HISTORICAL LIVE TASK PASS PRESERVED /
GOVERNED LIVE QUALIFICATION REQUIRES NEW SEPARATELY AUTHORIZED SINGLE-SHOT AFTER REMEDIATION /
NOT COMMITTED
```

---

## Lessons

1. **Identity STOP condition is mandatory**: EA-4E.25 should have STOPped when the real executor identity did not match the canonical identity. Instead, it modified the production code inline. This violates the governance principle that identity mismatches are STOP conditions, not fix-up opportunities.

2. **Narrow production-code fix is valid when**: The frozen contract identity is correct, and the real executor property is wrong. The fix is to correct the property to match the contract, not to weaken the contract.

3. **Evidence must be truthful**: The original claim "No live receiver execution was authorized by or performed under EA-4E.25" contradicted the actual historical record. Evidence packages must accurately reflect what occurred.

4. **last_outcome is not synthetic**: The `last_outcome` property merely stores the actual adapter `ExecutionOutcome` for later inspection. It does not synthesize process starts or model invocations — it exposes what actually happened.
