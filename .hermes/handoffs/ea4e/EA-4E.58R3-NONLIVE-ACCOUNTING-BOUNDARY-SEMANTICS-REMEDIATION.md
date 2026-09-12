# EA-4E.58R3 Non-Live Accounting-Boundary Semantics Remediation

## Governing Baseline

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=51185264143dbfa1d2c6bfe858b944874397dda0
GOVERNING_REMOTE_HEAD=51185264143dbfa1d2c6bfe858b944874397dda0
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

## EA-4E.58R2 Blocker

```text
EA4E58R2_RESULT=HOLD
BLOCKING_DOMAIN=ACCOUNTING_BOUNDARY_SEMANTICS
BLOCKING_FILE_OR_SYMBOL=tools/hermes_core/governed_production_runtime.py::GovernedProductionRuntime.execute
BLOCKING_INVARIANT=PROCESS_STARTED and MODEL_INVOCATION_ENTERED must correspond to observed process-start and model-entry boundaries
```

Prior false semantics: after executor.execute returned, runtime recorded PROCESS_STARTED, MODEL_INVOCATION_ENTERED, a SUCCESS/FAILED model terminal, and PROCESS_EXITED whenever executor_called was True, using synthetic proc-{request_id} / token-{request_id}. ProductionExecutionResult.process_started and model_invoked stayed False.

## Execution Result Fields

ProductionExecutionResult fields: receiver_id, route_decision, authority_valid, activation_valid, adapter_resolution, execution_decision, executor_called, executor_id, execution_status, real_adapter_called, process_started, model_invoked, reason, attempt_count, executor_output.

```text
EXECUTOR_CALLED_FIELD_PRESENT=YES
PROCESS_STARTED_FIELD_PRESENT=YES
MODEL_INVOKED_FIELD_PRESENT=YES
PROCESS_ID_FIELD_PRESENT=NO
PROCESS_TOKEN_FIELD_PRESENT=NO
MODEL_INVOCATION_ID_FIELD_PRESENT=NO
EXECUTOR_CALLED_FLAG_SEMANTICS=ProductionExecutionBoundary invoked executor.execute
EXECUTOR_CALLED_FLAG_PROVES_PROCESS_START_BOUNDARY_CROSSED=NO
EXECUTOR_CALLED_FLAG_PROVES_MODEL_INVOCATION_BOUNDARY_CROSSED=NO
PROCESS_START_OBSERVATION_SOURCE=ProductionExecutionResult.process_started
MODEL_INVOCATION_OBSERVATION_SOURCE=ProductionExecutionResult.model_invoked
ACCOUNTING_USES_EXECUTION_RESULT_PROCESS_STARTED_SIGNAL=YES
ACCOUNTING_USES_EXECUTION_RESULT_MODEL_INVOKED_SIGNAL=YES
```

Optional test-only observation attributes read via getattr, never invented by production: process_id, process_token, process_start_failed, process_exited, model_invocation_completed, model_invocation_failed.

## Prior False Semantics Removed

executor_called no longer implies PROCESS_STARTED, MODEL_INVOCATION_ENTERED, PROCESS_EXITED, or model terminal events. execution_status SUCCESS/FAILED no longer implies model completion/failure. Synthetic request-derived process IDs were removed.

## Process Accounting Truth Table

executor_called | process_started | process_start_failed | observed process_id+token | result
True | False | False | n/a | INTENT only, unresolved
True | True | False | present | PROCESS_STARTED
True | True | False | missing | INTENT only, unresolved (no fabricated ID)
False | False | True | n/a | PROCESS_START_FAILED
False | False | False | n/a | INTENT only, unresolved
any | True | any | present plus process_exited True | PROCESS_STARTED then PROCESS_EXITED

```text
PROCESS_ACCOUNTING_TRUTH_TABLE_VERIFIED=YES
GENERIC_EXECUTION_FAILURE_IMPLIES_PROCESS_STARTED=NO
PROCESS_EXITED_REQUIRES_OBSERVED_PROCESS_START=YES
PROCESS_EXITED_REQUIRES_OBSERVED_PROCESS_TERMINATION_OR_RETURN_SEMANTICS=YES
```

## Model Accounting Truth Table

model_invoked | model_invocation_completed | model_invocation_failed | result
False | any | any | INTENT only, unresolved
True | False | False | ENTERED, intent still unresolved
True | True | False | ENTERED then COMPLETED
True | False | True | ENTERED then FAILED
True | True | True | ENTERED only (contradictory terminals ignored)

```text
MODEL_ACCOUNTING_TRUTH_TABLE_VERIFIED=YES
GENERIC_EXECUTION_SUCCESS_IMPLIES_MODEL_INVOKED=NO
```

## Post-Fix Accounting Flow

PROCESS_START_INTENT
MODEL_INVOCATION_INTENT
ProductionExecutionBoundary.execute
if process_started and observed process_id and process_token: PROCESS_STARTED
if process_exited after that: PROCESS_EXITED
elif process_start_failed and not process_started: PROCESS_START_FAILED
else: leave process intent unresolved
if model_invoked: MODEL_INVOCATION_ENTERED
if observed completion xor failure: corresponding terminal
else: leave model intent unresolved
teardown (unchanged finally path)

## Identity

```text
PROCESS_ID_SOURCE=optional observed exec_result.process_id
PROCESS_TOKEN_SOURCE=optional observed exec_result.process_token
SYNTHETIC_PROCESS_ID_RECORDED_AS_REAL_OS_ID=NO
SYNTHETIC_PROCESS_TOKEN_RECORDED_AS_REAL_OWNERSHIP_TOKEN=NO
ACCOUNTING_PROCESS_IDENTITY_SEMANTICS_ACCURATE=YES
ACCOUNTING_SUPPORTS_OBSERVED_REAL_PROCESS_METADATA=YES
```

Observed IDs are recorded only when supplied by the execution result. The default production boundary does not populate them. Recovery still uses ProductionRecoveryRecord process identity, not request-derived strings.

## Schema

```text
ACCOUNTING_SCHEMA_VERSION_BEFORE=1
ACCOUNTING_SCHEMA_VERSION_AFTER=1
ACCOUNTING_EVENT_NAMES_CHANGED=NO
EA4E26_ACTIVE_ID=52edc7ad0be1bf446034ad31189a9172a6a35c98c8619b113f4a836320b8887e
EA4E29_ACTIVE_ID=2d2e42ebbaaa1eacabfbd9a09cf3a542f0424b26c96fb4e6b0a7984245039d87
```

## Tests

```text
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
EXPANDED_COMPATIBILITY_RUN=YES
EXPANDED_COMPATIBILITY_PASSED=316
EXPANDED_COMPATIBILITY_FAILED=15
BROADER_COMPATIBILITY_PASSED=316
BROADER_COMPATIBILITY_FAILED=15
BROADER_COMPATIBILITY_FAILURES_INHERITED=15
BROADER_COMPATIBILITY_NEW_FAILURES=0
```

The 15 expanded failures remain the EA-4E.58R2 dual-bind / EA-4E.43 fixture set. Not repaired here.

EA-4E.58R tests that assumed executor_called implies PROCESS_STARTED / MODEL_INVOCATION_ENTERED were corrected to expect unresolved intent on the default fake boundary.

## Changed Files

```text
EA4E58R3_CHANGED_PRODUCTION_FILES=tools/hermes_core/governed_production_runtime.py
EA4E58R3_CHANGED_TEST_FILES=tests/hermes_core/test_ea4e58r3_nonlive_accounting_boundary_semantics.py, tests/hermes_core/test_ea4e58r_nonlive_preflight_accounting_integration.py
EA4E58R3_CHANGED_EVIDENCE_FILES=.hermes/handoffs/ea4e/EA-4E.58R3-NONLIVE-ACCOUNTING-BOUNDARY-SEMANTICS-REMEDIATION.md, .hermes/handoffs/ea4e/EA-4E.58R-NONLIVE-PREFLIGHT-AND-ACCOUNTING-INTEGRATION-REMEDIATION.md
EA4E58R3_DIFF_SCOPE_MATCHES_ACCOUNTING_BOUNDARY_REMEDIATION=YES
```

## Blocker Closure

```text
BLOCKER_1_CREDENTIAL_PREFLIGHT_INTEGRATION=CLOSED
BLOCKER_2_DURABLE_ACCOUNTING_INTEGRATION=CLOSED
PROCESS_STARTED_ACCOUNTING_BOUNDARY_SEMANTICALLY_VALID=YES
MODEL_ENTERED_ACCOUNTING_BOUNDARY_SEMANTICALLY_VALID=YES
ACCOUNTING_PROCESS_IDENTITY_SEMANTICS_ACCURATE=YES
ACCOUNTING_MODEL_ENTRY_SEMANTICS_ACCURATE=YES
POST_BOUNDARY_ACCOUNTING_FAILURE_PRESERVES_UNCERTAINTY_DURABLY=YES
```

## Live Activity

All requested live/process/network/credential/GPU/ComfyUI counters remain 0.

## Repository Boundary

```text
EA4E58R_EVIDENCE_ACCOUNTING_SEMANTICS_CORRECTED=YES
EA4E58R3_EVIDENCE_CREATED=YES
SELF_IMPROVEMENT_SKILL_PATCH_TOUCHED_BY_EA4E58R3=NO
SELF_IMPROVEMENT_SKILL_PATCH_ELIGIBLE_FOR_CHECKPOINT=NO
EXTERNAL_HERMES_SKILL_PATCH_OCCURRED_DURING_OR_AFTER_RUN=YES
EXTERNAL_HERMES_SKILL_PATCH_PART_OF_AUTOMATION_TOOL_WORKTREE=NO
EXTERNAL_HERMES_SKILL_PATCH_ELIGIBLE_FOR_EA4E58R_CHECKPOINT=NO
EXTERNAL_HERMES_SKILL_PATCH_PATHS=C:\Users\David\AppData\Local\hermes\skills\software-development\hermes-execution-authorization-milestones\references\ea4e-nonlive-production-layers.md; C:\Users\David\AppData\Local\hermes\skills\software-development\hermes-execution-authorization-milestones\references\post-commit-evidence-reconciliation.md
STAGED=0
COMMIT=NO
PUSH=NO
```

## Final Disposition

```text
EA4E58R3_RESULT=PASS
EA4E58R_CHECKPOINT_ALLOWED=YES
PRODUCTION_ACTIVATION_READINESS=REQUIRES_EA4E58R_CHECKPOINT_AND_EA4E58_RETRY
PRODUCTION_ACTIVATED=NO
EA4E58_RETRY_ALLOWED=NO
EA4E59_ALLOWED=NO
NEXT_PHASE=EA-4E.58R IMPLEMENTATION + EVIDENCE CHECKPOINT REVIEW
```
