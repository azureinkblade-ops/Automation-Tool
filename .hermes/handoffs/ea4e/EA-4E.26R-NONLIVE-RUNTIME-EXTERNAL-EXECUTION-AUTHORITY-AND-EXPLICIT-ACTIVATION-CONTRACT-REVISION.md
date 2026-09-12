# EA-4E.26R Non-Live Runtime External Execution-Authority and Explicit Activation Contract Revision

## Qualification Result

```ini
EA4E26R=QUALIFIED_NONLIVE_DOWNSTREAM_REBIND_REQUIRED
EA4E26R_EVIDENCE_CREATED=YES
NEXT_PHASE=EA-4E.26R DOWNSTREAM SEALED-ARTIFACT REBIND IMPACT REVIEW
COMMIT=NO
PUSH=NO
```

This is a continuation of the authorized EA-4E.26R work. No live receiver, model, GPU, ComfyUI, or production execution was used.

## Governing State

```ini
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=968d7b371726dc1db8301f4497d9b7a6587c9905
GOVERNING_REMOTE_HEAD=968d7b371726dc1db8301f4497d9b7a6587c9905
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

The EA-4E.48 readiness history remains unchanged:

```ini
EA4E48_RESULT=HOLD_BOUNDARY_VIOLATION
HIDDEN_AUTHORITY_MANUFACTURE_FOUND=YES
HIDDEN_AUTO_ACTIVATION_FOUND=YES
EA4E48_HOLD_HISTORY_PRESERVED=YES
```

## Blocker and Contract Change

EA-4E.48 identified that the prior runtime created execution authority internally and performed activation internally. Its request could not accept externally issued authority or an explicit activation artifact. The blocker was reproduced against the pre-change runtime contract before editing.

Before this revision, the runtime constructed a `ProductionIssuancePolicy` and `ProductionIssuanceRequest`, evaluated them, and passed the resulting authority and activation to the execution boundary. The request had no external `execution_authority` or `activation` fields.

After this revision, `GovernedProductionRuntimeRequest` accepts:

```text
execution_authority: DispatchAuthority | None = None
activation: ProductionActivation | None = None
```

Missing or malformed values fail closed. The runtime validates both supplied artifacts, preserves their object references, and passes those same references to the execution boundary. It does not create, issue, refresh, replace, widen, or synthesize either artifact.

The existing activation contract is reused:

```ini
QUALIFIED_ACTIVATION_SOURCE=ProductionAppAuthorityCollaborator.issue(...).issuance_result.activation
ACTIVATION_SOURCE_IS_RUNTIME=NO
REUSED_EXISTING_ACTIVATION_CONTRACT=YES
```

The application-facing authority collaborator remains the authority issuer boundary. Its result can reach runtime without reissue.

```ini
APP_AUTHORITY_RESULT_CAN_BE_PASSED_TO_RUNTIME_WITHOUT_REISSUE=YES
```

## Runtime Boundaries

```ini
RUNTIME_REQUEST_REQUIRES_EXECUTION_AUTHORITY=YES
RUNTIME_REQUEST_DEFAULT_EXECUTION_AUTHORITY=NONE
RUNTIME_ACCEPTS_EXTERNALLY_ISSUED_EXECUTION_AUTHORITY=YES
RUNTIME_CREATES_EXECUTION_AUTHORITY=NO
RUNTIME_ISSUES_EXECUTION_AUTHORITY=NO
RUNTIME_SELF_AUTHORIZES=NO

RUNTIME_REQUEST_REQUIRES_ACTIVATION_STATE_OR_INTENT=YES
RUNTIME_REQUEST_DEFAULT_ACTIVATION=DISABLED
RUNTIME_ACCEPTS_EXPLICIT_ACTIVATION=YES
RUNTIME_AUTO_ACTIVATES=NO
RUNTIME_CREATES_ACTIVATION=NO
RUNTIME_DEFAULTS_ACTIVATION_TO_ENABLED=NO

RUNTIME_BINDS_EXECUTOR=NO
RUNTIME_REGISTERS_EXECUTOR=NO
RUNTIME_AUTO_SELECTS_EXECUTOR=NO

RUNTIME_INITIALIZES_AUTH_STORE=NO
RUNTIME_REPLACES_AUTH_STORE=NO
RUNTIME_BOOTSTRAPS_AUTH_STORE=NO

RUNTIME_AUTO_SELECTS_RECEIVER=NO
RUNTIME_FALLBACK=NO
RUNTIME_FAILOVER=NO
RUNTIME_AUTO_RETRY=NO
RUNTIME_AUTO_REISSUE=NO
RUNTIME_AUTO_REACTIVATE=NO
```

Authority and activation remain independent. Valid authority with disabled or missing activation is denied; invalid or missing authority is denied even when activation is supplied. The receiver, router, transport, model, delegation, operation, attempt scope, execution scope, and cross-artifact identity checks remain fail closed.

## Invocation-Authorization Lifecycle Clarification

The original EA-4E.26R packet contained a tension between the blanket `RUNTIME_CLAIMS_INVOCATION_AUTH=NO` field and its narrower instruction not to redesign the existing qualified invocation lifecycle. The qualified runtime already performs the atomic invocation-authorization claim/consume lifecycle after the authority, activation, binding, and resolver gates. This continuation preserves that lifecycle exactly; it does not issue or manufacture invocation authorization and does not broaden claim or consume authority.

```ini
RUNTIME_ISSUES_INVOCATION_AUTH=NO
RUNTIME_EXISTING_ATOMIC_INVOCATION_AUTH_CLAIM_PRESERVED=YES
RUNTIME_INVOCATION_AUTH_CLAIM_CHANGED_BY_EA4E26R=NO
RUNTIME_INVOCATION_AUTH_CONSUME_CHANGED_BY_EA4E26R=NO
EA4E26R_INVOCATION_AUTH_LIFECYCLE_SCOPE_CHANGE=NO
```

## Pass-Through Surface

The six production modules changed for pass-through are:

```text
tools/hermes_core/governed_production_runtime.py
tools/hermes_core/production_entrypoint.py
tools/hermes_core/production_application_caller.py
tools/hermes_core/production_app_adapter.py
tools/hermes_core/production_app_callsite.py
tools/hermes_core/production_app_user_action.py
```

The adapter, callsite, and user-action changes are required because they are the existing application path between the user-facing request and the entrypoint. They only carry the two supplied artifacts; they do not issue, activate, bind, select, or execute anything.

## Fake Qualification

```ini
KILO_EXTERNAL_AUTHORITY_ACCEPTED=YES
KILO_EXPLICIT_ACTIVATION_ACCEPTED=YES
KILO_RUNTIME_SELF_ISSUANCE_COUNT=0
KILO_RUNTIME_AUTO_ACTIVATION_COUNT=0

OPENCODE_EXTERNAL_AUTHORITY_ACCEPTED=YES
OPENCODE_EXPLICIT_ACTIVATION_ACCEPTED=YES
OPENCODE_RUNTIME_SELF_ISSUANCE_COUNT=0
OPENCODE_RUNTIME_AUTO_ACTIVATION_COUNT=0

REAL_RECEIVER_PROCESS_STARTED=NO
REAL_MODEL_INVOKED=NO
REAL_EXECUTOR_EXECUTED=NO
REAL_ADAPTER_EXECUTED=NO
```

The positive paths use fake executors only. The test matrix covers Kilo and OpenCode, both cross-receiver authority directions, missing and malformed requests, missing/denied/expired/malformed authorities, transport/model/router/delegation/scope/attempt mismatches, disabled/missing/malformed activations, unsupported receivers, and Grok receiver inputs.

## Runtime Tripwires

The runtime-level tripwire test was run after all externally supplied artifacts had been constructed. It rejects any attempt to invoke the forbidden capability and passed, proving no such call occurred during runtime execution.

```ini
RUNTIME_EXECUTION_AUTH_ISSUANCE_TRIPWIRE_HITS=0
RUNTIME_ACTIVATION_CREATION_TRIPWIRE_HITS=0
INVOCATION_AUTH_ISSUANCE_TRIPWIRE_HITS=0
AUTH_STORE_BOOTSTRAP_TRIPWIRE_HITS=0
EXECUTOR_BINDING_TRIPWIRE_HITS=0
RECEIVER_PROCESS_TRIPWIRE_HITS=0
MODEL_INVOCATION_TRIPWIRE_HITS=0
REAL_EXECUTOR_EXECUTE_TRIPWIRE_HITS=0
REAL_ADAPTER_TRIPWIRE_HITS=0
```

## Contract Identity and Downstream Impact

```ini
EA4E26_CONTRACT_ROLL_REQUIRED=YES
OLD_EA4E26_CONTRACT_ID=2e7a4b360c54541ff408e8430d3ac9a28cdee76e0feef5e1da03b87a889657ba
NEW_EA4E26_CONTRACT_ID=52edc7ad0be1bf446034ad31189a9172a6a35c98c8619b113f4a836320b8887e
EA4E26_CONTRACT_ID_CHANGED=YES
EA4E26_CONTRACT_CHANGE_REASON=external execution-authority input + explicit activation input added; runtime self-issuance/auto-activation removed

DOWNSTREAM_ARTIFACT_REBIND_REQUIRED=YES
DOWNSTREAM_ARTIFACTS_AFFECTED=EA-4E.29 caller contract at minimum; any sealed artifact binding the EA-4E.26 or derived EA-4E.29 IDs requires separate impact review
NEW_EA4E29_CALLER_CONTRACT_ID=2d2e42ebbaaa1eacabfbd9a09cf3a542f0424b26c96fb4e6b0a7984245039d87
OLD_EA4E29_CALLER_CONTRACT_ID=00c6808dada4c9cf74a0310a31c9a51b10c1a8ee770f8f6c8a45d4d1f4962dd2
```

The intentionally stale frozen EA-4E.26/29 assertion remains untouched. No downstream sealed artifact was regenerated or rebound in this phase.

## Tests

All commands used the qualified local `pytest 9.1.1` environment and were fake/non-live.

```ini
EA4E26R_DEDICATED_TEST_TOTAL=33
EA4E26R_DEDICATED_TEST_FAILURES=0

EA4E26_COMPATIBILITY_TEST_TOTAL=116
EA4E26_COMPATIBILITY_TEST_FAILURES=0

ENTRYPOINT_CALLER_RUNTIME_COMPATIBILITY_TEST_TOTAL=130
ENTRYPOINT_CALLER_RUNTIME_COMPATIBILITY_TEST_FAILURES=0

EA4E44_COMPATIBILITY_TEST_TOTAL=22
EA4E44_COMPATIBILITY_TEST_FAILURES=0

EA4E45_COMPATIBILITY_TEST_TOTAL=34
EA4E45_COMPATIBILITY_TEST_FAILURES=0

EA4E46_COMPATIBILITY_TEST_TOTAL=53
EA4E46_COMPATIBILITY_TEST_FAILURES=0

RESTART_DURABILITY_COMPATIBILITY_TEST_TOTAL=51
RESTART_DURABILITY_COMPATIBILITY_TEST_FAILURES=0
BROAD_TEST_SUITE_RUN=NO
```

The consolidated selected run completed with `438 passed, 16 deselected, 0 failed`.

The 16 deselected tests are not normalized as passing:

1. Fourteen app-layer compatibility tests attempt two simultaneous executor bindings while `MAX_SIMULTANEOUS_REAL_BINDINGS=1`. The same fixture shape and binding policy exist at the governing baseline; the failure reason is `BINDING_LIMIT_EXCEEDED`. EA-4E.26R did not introduce these failures, and the one-binding limit was not weakened.
2. One existing direct EA-4E.26B/27 test attempts the same dual-binding pattern and is classified with the same legacy fixture family. Thus the expanded combined inventory contains 15 pre-existing dual-binding exclusions, while the app-layer compatibility slice contains the 14 reported in the continuation packet.
3. One frozen EA-4E.32 contract-chain assertion still expects the old EA-4E.26/29 IDs. It remains deliberately stale as downstream rebind evidence.

```ini
DUAL_BINDING_FAILURES_PRESENT_AT_GOVERNING_BASELINE=YES
DUAL_BINDING_FAILURE_REASON=BINDING_LIMIT_EXCEEDED
EA4E26R_INTRODUCED_DUAL_BINDING_FAILURES=NO
MAX_SIMULTANEOUS_REAL_BINDINGS=1
BINDING_LIMIT_WEAKENED=NO
```

## Changed Files

```ini
EA4E26R_REQUIRED_PRODUCTION_FILES=6
EA4E26R_REQUIRED_TEST_FILES=12
EA4E26R_REQUIRED_EVIDENCE_FILES=1
```

The 12 test/support files are the dedicated EA-4E.26R support and test, existing runtime/caller/wiring compatibility fixtures, and the six application-layer compatibility fixture files. No `app.py` change was made.

```ini
APP_PY_CHANGED_BY_EA4E26R=NO
APP_PY_RUNTIME_AUTHORITY_WIRING_CHANGED=NO
APP_PY_ACTIVATION_WIRING_CHANGED=NO
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
```

## No-Live Accounting

```ini
NEW_KILO_TASKS=0
NEW_OPENCODE_TASKS=0
NEW_KILO_RECEIVER_PROCESSES=0
NEW_OPENCODE_RECEIVER_PROCESSES=0
NEW_KILO_MODEL_INVOCATIONS=0
NEW_OPENCODE_MODEL_INVOCATIONS=0
NEW_LIVE_EXECUTION_AUTHS_ISSUED=0
NEW_LIVE_INVOCATION_AUTHS_ISSUED=0
NEW_LIVE_INVOCATION_AUTHS_CLAIMED=0
NEW_LIVE_INVOCATION_AUTHS_CONSUMED=0
NEW_REAL_EXECUTOR_BINDINGS=0
GROK_TASKS=0
GROK_AUTHORIZATIONS=0
GROK_RECEIVER_PROCESSES=0
GROK_MODEL_INVOCATIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

EA-4E.26R is qualified non-live, but the changed EA-4E.26 identity means downstream sealed artifacts must be reviewed and selectively rebound in the next separately governed phase. Stop here; do not retry EA-4E.48, begin EA-4E.49, commit, push, activate production, or perform live execution in this phase.
