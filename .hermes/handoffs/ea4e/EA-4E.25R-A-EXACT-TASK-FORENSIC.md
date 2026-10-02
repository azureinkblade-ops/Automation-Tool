# EA-4E.25R-A OPENCODE EXACT-TASK / EVIDENCE FORENSIC CORRECTION

## Historical Sequence

1. **EA-4E.25** (historical): Live task produced exact expected output, but qualification was HOLD because the identity stop condition was violated (inline modification of `opencode_live_binding.py` instead of STOP).
2. **EA-4E.25A** (non-live): Remediation verified the canonical identity, corrected the `executor_id` property, qualified actual-event accounting, and corrected the evidence package.
3. **EA-4E.25R** (historical): Live requalification produced correct output, but the executed task text differed from the authorized task text. Qualification HOLD.
4. **EA-4E.25R-A** (this phase): Non-live exact-task/evidence forensic correction.

---

## Governing State

```
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=0e42a2923fcfb1a687cbcfa7e326938a04fc1653
GOVERNING_REMOTE_HEAD=0e42a2923fcfb1a687cbcfa7e326938a04fc1653
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
```

---

## Historical EA-4E.25R

```
EA4E25R_HISTORICAL_LIVE_EXECUTION_OCCURRED=YES
EA4E25R_HISTORICAL_NEW_OPENCODE_TASKS=1
EA4E25R_HISTORICAL_NEW_MODEL_INVOCATIONS=1
EA4E25R_HISTORICAL_NEW_RECEIVER_PROCESSES=1
EA4E25R_HISTORICAL_LIVE_RESULT=PASS
EA4E25R_HISTORICAL_OUTPUT=EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK
EA4E25R_HISTORICAL_AUTHORIZATION_CONSUMED=YES
EA4E25R_HISTORICAL_SECOND_LIVE_EXECUTION_PERFORMED=NO
EA4E25R_HISTORICAL_BINDING_TORN_DOWN=YES
EA4E25R_HISTORICAL_RETRY_ATTEMPTS=0
EA4E25R_HISTORICAL_FALLBACK_ATTEMPTS=0
EA4E25R_HISTORICAL_FAILOVER_ATTEMPTS=0
```

---

## Exact Task Forensics

```
EA4E25R_AUTHORIZED_TASK=Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK
EA4E25R_EXECUTED_TASK=Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK
EA4E25R_EXECUTED_TASK_MATCHED_AUTHORIZED_TASK=NO
EA4E25R_OUTPUT_MATCHED_EXPECTED_MARKER=YES
EA4E25R_EXACT_TASK_STOP_CONDITION_VIOLATED=YES
EA4E25R_QUALIFICATION_STATUS=HOLD
```

### Task Substitution Source

```
TASK_SUBSTITUTION_SOURCE_FILE=tools/hermes_core/opencode_invocation_authorized_live.py
TASK_SUBSTITUTION_SOURCE_SYMBOL=task_payload
TASK_SUBSTITUTION_OCCURRED_IN=HARNESS_CONSTANT
```

**Mechanism**: The harness constant `task_payload` in `opencode_invocation_authorized_live.py` was modified from `"Return exactly: EA4E25_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"` to `"Write exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"` instead of preserving the authorized `"Return exactly:"` prefix. The temporary runner `run_ea4e25r_opencode_requalification.py` also mutated the module-global `EXPECTED_LIVE_OUTPUT` at runtime, which is not an acceptable permanent qualification mechanism.

---

## Task Handling Remediation

```
CANONICAL_EA4E25R_TASK=Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK
CANONICAL_EA4E25R_EXPECTED_OUTPUT=EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK
CANONICAL_TASK_AND_EXPECTED_OUTPUT_SEPARATE=YES
MODULE_GLOBAL_TASK_MUTATION_USED=NO
MODULE_GLOBAL_EXPECTED_OUTPUT_MUTATION_USED_FOR_TASK_CONSTRUCTION=NO
EXACT_TASK_PASSED_EXPLICITLY=YES
TASK_TEXT_IMMUTABLE_DURING_QUALIFICATION=YES
AUTHORIZED_AND_EXECUTED_TASK_CAN_BE_COMPARED_BEFORE_EXECUTION=YES
```

---

## Temporary Runner

```
EA4E25R_TEMP_RUNNER_FILE_PRESENT=NO (deleted)
EA4E25R_TEMP_RUNNER_PURPOSE=One-off live runner for consumed EA-4E.25R attempt
EA4E25R_TEMP_RUNNER_REQUIRED_FOR_PERMANENT_IMPLEMENTATION=NO
TEMP_RUNNER_REMOVED_FROM_WIP=YES
TEMP_RUNNER_EVIDENCE_PRESERVED_ELSEWHERE=YES
```

The temporary runner `run_ea4e25r_opencode_requalification.py` was a one-off script created only for the consumed EA-4E.25R attempt. It contained no unique evidence beyond what is captured in this document and the EA-4E.25R evidence. Its behavior is fully described in the evidence. It has been deleted from WIP.

---

## Contracts

```
CONTRACTS_RECOMPUTED_FROM_FINAL_WIP=YES
EA4E23_INVOCATION_CONTRACT_ID=1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8
EA4E22_INTEGRATION_CONTRACT_ID=e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a
EA4E21_BINDING_CONTRACT_ID=99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7
EA4E18_INTEGRATION_CONTRACT_ID=d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459
EA4E17_ISSUANCE_CONTRACT_ID=26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78
EA4E14_EXECUTION_CONTRACT_ID=89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6
OPENCODE_TRANSPORT_CONTRACT_ID=192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f
OPENCODE_MODEL_BINDING_ID=cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371
ALL_GOVERNING_CONTRACTS_UNCHANGED=YES
```

---

## Identity / Accounting / Clock

```
CANONICAL_OPENCODE_EXECUTOR_IDENTITY=RealOpenCodeProductionExecutor
REAL_OPENCODE_EXECUTOR_REPORTED_IDENTITY=RealOpenCodeProductionExecutor
OPENCODE_EXECUTOR_IDENTITY_MATCH=YES
OPENCODE_IDENTITY_MASKING_WRAPPER_PRESENT=NO
EA4E22_IDENTITY_VALIDATION_BYPASSED=NO

SELF_REPORTED_WRAPPER_COUNTS_USED=NO
COUNTERS_ARE_ACTUAL_EVENT_DERIVED=YES

LIVE_CLOCK_INJECTED=YES
FIXED_QUALIFICATION_CLOCK_USED_FOR_LIVE_AUTHORIZATION=NO
NONLIVE_TEST_CLOCK_REMAINS_DETERMINISTIC=YES
```

---

## Evidence

```
EA4E25_HISTORICAL_DEFECT_PRESERVED=YES
EA4E25A_REMEDIATION_PRESERVED=YES
EA4E25R_HISTORICAL_OUTPUT_PASS_PRESERVED=YES
EA4E25R_EXACT_TASK_MISMATCH_PRESERVED=YES
EA4E25R_QUALIFICATION_RECORDED_AS_HOLD=YES
```

---

## Tests

```
EA4E23_TESTS=38 passed / 0 failed
EA4E22_TESTS=45 passed / 0 failed
EA4E21_TESTS=53 passed / 0 failed
EA4E25_NONLIVE_TESTS=16 passed / 0 failed
EA4E25A_TESTS=16 passed / 0 failed
EA4E25RA_TESTS=28 passed / 0 failed
OPENCODE_LIVE_BINDING_NONLIVE_TESTS=18 passed / 0 failed
OPENCODE_ADAPTER_NONLIVE_TESTS=43 passed / 0 failed
EA4E14_TESTS=31 passed / 0 failed
NONLIVE_REGRESSION_TOTAL=346 passed / 0 failed
NONLIVE_REGRESSION_FAILURES=0
```

---

## No New Live Execution

```
EA4E25R_SECOND_LIVE_RUN_PERFORMED=NO
NEW_OPENCODE_TASKS=0
NEW_KILO_TASKS=0
NEW_MODEL_INVOCATIONS=0
NEW_RECEIVER_PROCESSES=0
REAL_OPENCODE_EXECUTOR_LIVE_CALLS=0
REAL_OPENCODE_ADAPTER_LIVE_CALLS=0
LIVE_BINDINGS_CREATED=0
LIVE_INVOCATION_AUTHORIZATIONS_ISSUED=0
LIVE_DISPATCH_EXECUTIONS=0
PRODUCTION_EXECUTION_BOUNDARY_REAL_EXECUTIONS=0
```

---

## Proposed Permanent Scope

```
PROPOSED_PERMANENT_EA4E25_FILES=
  tools/hermes_core/opencode_live_binding.py
  tools/hermes_core/opencode_invocation_authorized_live.py
  tests/hermes_core/test_opencode_invocation_authorized_live.py
  tests/hermes_core/test_opencode_invocation_authorized_live_25a.py
  tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py
  .hermes/handoffs/ea4e/EA-4E.25-OPENCODE-INVOCATION-AUTHORIZED-LIVE.md
  .hermes/handoffs/ea4e/EA-4E.25A-OPENCODE-IDENTITY-REMEDIATION.md
  .hermes/handoffs/ea4e/EA-4E.25R-OPENCODE-REQUALIFICATION.md
  .hermes/handoffs/ea4e/EA-4E.25R-A-EXACT-TASK-FORENSIC.md
PROPOSED_PERMANENT_EA4E25_FILE_COUNT=9
TEMPORARY_FILES_EXCLUDED=run_ea4e25r_opencode_requalification.py (deleted)
UNRELATED_WIP_FILES=(none)
```

---

## Repository

```
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

---

## Final Disposition

```
EA-4E.25R-A =
FORENSIC COMPLETE /
EXACT TASK MISMATCH CONFIRMED /
CANONICAL TASK RESTORED /
MODULE-GLOBAL TASK OVERRIDE REMOVED /
TEMPORARY RUNNER DISPOSITION DETERMINED /
HISTORICAL EVIDENCE CORRECTED /
NO NEW LIVE EXECUTION /
ALL NON-LIVE TESTS PASS /
NOT COMMITTED

EA-4E.25R =
HOLD /
HISTORICAL OUTPUT PASS PRESERVED /
EXACT AUTHORIZED TASK WAS NOT USED /
NEW SEPARATELY AUTHORIZED LIVE REQUALIFICATION REQUIRED

EA-4E.25 =
HOLD /
NOT COMMITTED
```

---

## Files Created/Modified

1. **`tools/hermes_core/opencode_invocation_authorized_live.py`** — Restored task payload to `"Return exactly: EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"`; updated `EXPECTED_LIVE_OUTPUT` to `"EA4E25R_OPENCODE_INVOCATION_AUTHORIZED_LIVE_OK"`
2. **`tests/hermes_core/test_opencode_invocation_authorized_live_25ra.py`** — 28 non-live forensic tests covering exact-task validation, no module-global mutation, identity remediation intact, actual-event accounting intact, live-clock intact, historical mismatch recorded, contracts unchanged
3. **`.hermes/handoffs/ea4e/EA-4E.25R-A-EXACT-TASK-FORENSIC.md`** — This document

### Files Deleted

1. **`run_ea4e25r_opencode_requalification.py`** — Temporary one-off live runner; evidence preserved in this document

---

## Lessons

1. **Exact task text is a governance requirement**: The authorized task text must be executed byte-for-byte. Substituting "Write exactly:" for "Return exactly:" violates the exact-task stop condition, even if the output matches.

2. **Module-global mutation is not a qualification mechanism**: The temporary runner mutated `EXPECTED_LIVE_OUTPUT` at runtime. This is not acceptable for permanent qualification — the task and expected output must be explicit constants or immutable arguments.

3. **Temporary runners must be dispositioned**: One-off live runners created for consumed attempts should be deleted after the attempt, with evidence preserved in the handoff document.

4. **Evidence must preserve the full sequence**: Each phase's defects and corrections must be preserved, not erased. The qualification status reflects the full history.
