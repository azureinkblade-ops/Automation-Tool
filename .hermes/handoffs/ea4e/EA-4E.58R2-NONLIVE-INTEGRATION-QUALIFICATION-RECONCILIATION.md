# EA-4E.58R2 Non-Live Integration Qualification Reconciliation

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

## Prior HOLD

EA-4E.58R implemented wiring for both original blockers, then reported PASS with a 527/15 "sealed" collection and 31/91 count drift. That PASS is withdrawn. Checkpoint remains disallowed.

```text
EA4E58R_CURRENT_DISPOSITION=HOLD
ORIGINAL_BLOCKER_1_CREDENTIAL_PREFLIGHT_INTEGRATION_STATUS=CLOSED
ORIGINAL_BLOCKER_2_DURABLE_ACCOUNTING_INTEGRATION_STATUS=WIRED_BUT_BOUNDARY_SEMANTICS_NOT_QUALIFIED
EA4E58R_CHECKPOINT_ALLOWED=NO
EA4E58_RETRY_ALLOWED=NO
EA4E59_ALLOWED=NO
```

## Self-Improvement Patch Isolation

```text
SELF_IMPROVEMENT_SKILL_PATCH_PRESENT=YES
SELF_IMPROVEMENT_SKILL_PATCH_PATHS=C:\Users\David\AppData\Local\hermes\skills\software-development\hermes-execution-authorization-milestones\references\ea4e-nonlive-production-layers.md
SELF_IMPROVEMENT_SKILL_PATCH_TOUCHED_BY_EA4E58R2=NO
SELF_IMPROVEMENT_SKILL_PATCH_ELIGIBLE_FOR_EA4E58R_CHECKPOINT=NO
```

The skill lives outside the Automation Tool worktree. It was not modified in this phase.

## Sealed-Suite Command Comparison

Historical sealed-aligned command (EA-4E.52 through EA-4E.57, 171/0):

```text
pytest
  tests/hermes_core/test_ea4e42_nonlive_app_factory.py
  tests/hermes_core/test_ea4e44_nonlive_app_authority.py
  tests/hermes_core/test_ea4e45_nonlive_app_binding.py
  tests/hermes_core/test_ea4e45a_nonlive_binding_occupancy_semantics.py
  tests/hermes_core/test_ea4e46_nonlive_invocation_auth_request_provisioning.py
  tests/hermes_core/test_ea4e47_nonlive_invocation_auth_store_bootstrap.py
  tests/hermes_core/test_ea4e48_retry_nonlive_fake_e2e.py
```

EA-4E.58R instead ran an expanded mix including ea4e26r, ea4e32, ea4e33, ea4e35-ea4e45a, ea4e46, ea4e48, test_governed_production_runtime, test_governed_production_caller.

```text
SEALED_COMMANDS_EQUIVALENT=NO
SEALED_ALIGNED_RECONCILED_PASSED=171
SEALED_ALIGNED_RECONCILED_FAILED=0
EXPANDED_COMPATIBILITY_RUN=YES
EXPANDED_COMPATIBILITY_PASSED=527
EXPANDED_COMPATIBILITY_FAILED=15
```

## Fifteen Expanded Failures

All 15 are from the expanded collection, not the 171 sealed command.

1-2. test_ea4e36 test_kilo_activation_cannot_run_opencode / test_opencode_activation_cannot_run_kilo
   BINDING_LIMIT_EXCEEDED on second bind_fake. Expects two active bindings. Contradicts EA-4E.54 MAX=1.
   Classification: OBSOLETE_EXPECTATION_AFTER_ALREADY_QUALIFIED_CONTRACT

3-5. test_ea4e37 receiver mutation / kilo cannot become opencode / opencode cannot become kilo
   Same dual-bind. Classification: OBSOLETE_EXPECTATION_AFTER_ALREADY_QUALIFIED_CONTRACT

6-8. test_ea4e38 same pattern. Classification: OBSOLETE_EXPECTATION_AFTER_ALREADY_QUALIFIED_CONTRACT

9-11. test_ea4e39 same pattern. Documented as 3 of 7 inherited failures in EA-4E.52.
   Classification: PREEXISTING_FAILURE / OBSOLETE_EXPECTATION_AFTER_ALREADY_QUALIFIED_CONTRACT

12-14. test_ea4e41 same pattern. Documented as 3 of 7 inherited failures in EA-4E.52.
   Classification: PREEXISTING_FAILURE / OBSOLETE_EXPECTATION_AFTER_ALREADY_QUALIFIED_CONTRACT

15. test_ea4e43_nonlive_feature_gate_config.py::test_explicit_enabled_fake_kilo_path
   Expects ALLOW while omitting execution_authority and activation on ProductionAppUserActionRequest.
   Documented in EA-4E.52 as the seventh inherited broader failure.
   Classification: PREEXISTING_FAILURE / TEST_FIXTURE_MISSING_NEW_REQUIRED_DEPENDENCY
   Production path does not bypass authority. The fixture never supplies it.

```text
DUAL_BIND_FAILURE_COUNT=14
DUAL_BIND_TESTS_EXPECT_SIMULTANEOUS_ACTIVE_BINDINGS=YES
DUAL_BIND_EXPECTATION_CONTRADICTS_EA4E54_SINGLE_SLOT_CONTRACT=YES
EA4E43_FAILURE_TEST=tests/hermes_core/test_ea4e43_nonlive_feature_gate_config.py::test_explicit_enabled_fake_kilo_path
EA4E43_FAILURE_CLASSIFICATION=PREEXISTING_FAILURE
EA4E43_PATH_OMITS_EXPLICIT_EXECUTION_AUTHORITY=YES
EA4E58R_NEW_REAL_SEALED_REGRESSIONS=0
EA4E58R_INHERITED_OR_STALE_SEALED_FAILURES=15
EA4E58R_TEST_COLLECTION_ONLY_FAILURES=15
CHECKPOINTED_HEAD_SEALED_BASELINE_VERIFIED=NO
```

HEAD baseline was not re-run in an isolated worktree. The 15 tests match the EA-4E.52 written inherited set plus the same dual-bind pattern in ea4e36/37/38. The historical 171 command passes on current WIP.

## Count Drift

```text
EA4E56_PRIOR_COUNT=32
EA4E56_CURRENT_COUNT=32
EA4E56_COUNT_DRIFT_EXPLAINED=YES
EA4E56_COLLECTION_COUNT_DRIFT_REASON=58R report arithmetic. collect-only still lists 32 tests including the parametrized dual-receiver case as two.
EA4E56_COUNT_DRIFT_HIDES_FAILURE=NO
EA4E56_EQUIVALENT_PRIOR_TEST_COVERAGE_PRESERVED=YES

EA4E55_52_PRIOR_COUNT=90
EA4E55_52_CURRENT_COUNT=90
EA4E55_52_COUNT_DRIFT_EXPLAINED=YES
EA4E55_52_COLLECTION_COUNT_DRIFT_REASON=58R report allocated 91 by subtracting a 31-count 56 suite from a 178 combined run. collect-only is 27+23+18+22=90.
EA4E55_52_COUNT_DRIFT_HIDES_FAILURE=NO
```

## Admission vs Bind

Operator/host path (EA-4E.52, unchanged by 58R):

1. BindingProvisioner.bind runs preflight then controller.bind. This creates the active executor binding.
2. lifecycle.submit acquires admission.
3. lifecycle preflight runs again.
4. get_binding_for_receiver looks up the already-active binding.
5. governed action / runtime execute.

```text
BIND_REQUEST_CREATION_POINT=ProductionAppBindingRequest construction in tests/operators
BINDING_PROVISION_POINT=ProductionAppBindingProvisioner.bind
ACTIVE_BINDING_ESTABLISHMENT_POINT=ProductionExecutorBindingController.bind
ADMISSION_ACQUIRE_POINT=ProductionAppRequestLifecycleOwner.submit
BINDING_PREFLIGHT_POINT=ProductionAppBindingProvisioner.bind before controller.bind
LIFECYCLE_PREFLIGHT_POINT=ProductionAppRequestLifecycleOwner._submit_admitted before get_binding_for_receiver
PRIOR_REPORT_BIND_MEANS=ACTIVE_EXECUTOR_BINDING
ADMISSION_BEFORE_REAL_BINDING=NO
ACTIVE_BINDING_CAN_EXIST_BEFORE_ADMISSION=YES
```

This split is the EA-4E.52/53/54 design: lifecycle requires a pre-existing explicit binding; admission serializes request execution, not operator provisioning. 58R did not move bind inside admission. 58R2 does not redesign that.

## Duplicate Preflight

```text
PREFLIGHT_CHECK_COUNT_PER_SUCCESSFUL_HOST_REQUEST=2
PREFLIGHT_CHECK_1_PURPOSE=defense in depth before active binding in BindingProvisioner.bind
PREFLIGHT_CHECK_2_PURPOSE=lifecycle gate before binding lookup and governed action
DUPLICATE_PREFLIGHT_INTENTIONAL=YES
DUPLICATE_PREFLIGHT_RESULTS_CAN_CONTRADICT_WITH_SAME_INPUTS=NO
DUPLICATE_PREFLIGHT_CAUSES_NETWORK_OR_PROCESS_ACTIVITY=NO
```

Both checks use ProductionCredentialReadinessPreflight.config_for(receiver_id, transport, model) from the explicit request. Same policy object when composition injects one preflight.

## Accounting Boundary Semantics

ProductionExecutionBoundary.execute sets executor_called=True after executor.execute returns, and always sets process_started=False and model_invoked=False.

58R runtime then records PROCESS_STARTED and MODEL_INVOCATION_ENTERED when executor_called is True, using process_id=`proc-{request_id}` and process_token=`token-{request_id}`.

```text
EXECUTOR_CALLED_FLAG_SEMANTICS=ProductionExecutionBoundary invoked executor.execute
EXECUTOR_CALLED_FLAG_PROVES_PROCESS_START_BOUNDARY_CROSSED=NO
EXECUTOR_CALLED_FLAG_PROVES_MODEL_INVOCATION_BOUNDARY_CROSSED=NO
PROCESS_STARTED_EVENT_BOUNDARY=after executor.execute returns
PROCESS_STARTED_ACCOUNTING_BOUNDARY_SEMANTICALLY_VALID=NO
MODEL_INVOCATION_ENTERED_EVENT_BOUNDARY=after executor.execute returns
MODEL_ENTERED_ACCOUNTING_BOUNDARY_SEMANTICALLY_VALID=NO
PROCESS_ID_SOURCE=synthetic f-string from request_id
PROCESS_TOKEN_SOURCE=synthetic f-string from request_id
PROCESS_ID_REPRESENTS_REAL_OS_PROCESS_ID=NO
PROCESS_TOKEN_REPRESENTS_REAL_PROCESS_OWNERSHIP_TOKEN=NO
ACCOUNTING_PROCESS_IDENTITY_SEMANTICS_ACCURATE=NO
ACCOUNTING_MODEL_ENTRY_SEMANTICS_ACCURATE=NO
SYNTHETIC_ACCOUNTING_IDENTITY_CONFLATED_WITH_RECOVERY_OS_IDENTITY=NO
```

Recovery still uses ProductionRecoveryRecord.process_id / process_token from the recovery journal, not the synthetic accounting ids.

Intent writes happen before boundary.execute. If they raise ProductionAccountingError, execute is skipped.

Post-boundary writes catch ProductionAccountingError and pass. Intent rows already committed remain. That leaves durable unresolved intent.

```text
POST_BOUNDARY_ACCOUNTING_FAILURE_HANDLER=except ProductionAccountingError: pass
NORMAL_EXECUTION_PATH_CREATES_DURABLE_UNRESOLVED_PROCESS_INTENT=YES
NORMAL_EXECUTION_PATH_CREATES_DURABLE_UNRESOLVED_MODEL_INTENT=YES
NORMAL_EXECUTION_PATH_RESOLVES_PROCESS_INTENT_ON_TERMINAL_WRITE=YES
NORMAL_EXECUTION_PATH_RESOLVES_MODEL_INTENT_ON_TERMINAL_WRITE=YES
POST_BOUNDARY_ACCOUNTING_FAILURE_PRESERVES_UNCERTAINTY_DURABLY=YES
```

## Recovery Accounting

```text
RECOVERY_ACCOUNTING_HOOK_CONFIGURED=YES
RECOVERY_ACCOUNTING_HOOK_CONSTRUCTION_FILE=app.py
RECOVERY_ACCOUNTING_HOOK_CONSTRUCTION_SYMBOL=configure_governed_production_action
RECOVERY_ACCOUNTING_LEDGER_SOURCE=components.composition.accounting_ledger
RECOVERY_ACCOUNTING_LEDGER_IS_SAME_LOGICAL_DURABLE_LEDGER_AS_RUNTIME=YES
RECOVERY_ACCOUNTING_CLOCK_INJECTED=YES
ORPHAN_EVENT_ADDS_PROCESS_STARTED=NO
RECOVERED_EVENT_ADDS_PROCESS_STARTED=NO
RECOVERY_SECOND_PASS_SIDE_EFFECT_COUNT=0
RECOVERY_SECOND_PASS_ACCOUNTING_EVENT_COUNT=0
```

## Tests This Phase

```text
TEST_ONLY_CORRECTIONS_REQUIRED=NO
ASSERTIONS_REMOVED_TO_FORCE_PASS=NO
SECURITY_ASSERTIONS_WEAKENED=NO
SINGLE_SLOT_ASSERTION_WEAKENED=NO
EXPLICIT_AUTHORITY_REQUIREMENT_WEAKENED=NO
PREFLIGHT_REQUIREMENT_WEAKENED=NO

EA4E58R_DEDICATED_TESTS_PASSED=11
EA4E58R_DEDICATED_TESTS_FAILED=0
EA4E57_REGRESSION_TESTS_PASSED=45
EA4E57_REGRESSION_TESTS_FAILED=0
EA4E56_RECONCILED_TESTS_PASSED=32
EA4E56_RECONCILED_TESTS_FAILED=0
EA4E55_52_RECONCILED_TESTS_PASSED=90
EA4E55_52_RECONCILED_TESTS_FAILED=0
SEALED_ALIGNED_RECONCILED_PASSED=171
SEALED_ALIGNED_RECONCILED_FAILED=0
BROADER_COMPATIBILITY_NEW_FAILURES=0
```

EA4E58R2_PRODUCTION_CODE_CHANGE_REQUIRED=NO. Accounting boundary correction needs 58R3.

## Live Activity

All requested live/process/network/credential/GPU counters remain 0.

## Checkpoint Eligibility

Fails because PROCESS_STARTED / MODEL_ENTERED accounting is not semantically valid against the execution-boundary flags or real process identity.

```text
EA4E58R2_RESULT=HOLD
EA4E58R_CHECKPOINT_ALLOWED=NO
PRODUCTION_ACTIVATION_READINESS=NOT_QUALIFIED
BLOCKING_DOMAIN=ACCOUNTING_BOUNDARY_SEMANTICS
BLOCKING_FILE_OR_SYMBOL=tools/hermes_core/governed_production_runtime.py::GovernedProductionRuntime.execute
BLOCKING_INVARIANT=PROCESS_STARTED and MODEL_INVOCATION_ENTERED must correspond to observed process-start and model-entry boundaries
BLOCKING_REASON=runtime records those events from executor_called after executor.execute returns, with synthetic proc/token ids, while ProductionExecutionResult.process_started and model_invoked stay False
EA4E58_RETRY_ALLOWED=NO
EA4E59_ALLOWED=NO
NEXT_PHASE=EA-4E.58R3 NON-LIVE INTEGRATION REMEDIATION
STAGED=0
COMMIT=NO
PUSH=NO
```
