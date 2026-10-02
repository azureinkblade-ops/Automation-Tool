# EA-4E.64A Non-Live Deployment-Composition Qualification

## Disposition

```ini
EA4E64A_RESULT=HOLD
BLOCKING_DOMAIN=EXACT_KILO_EXECUTOR_BINARY_IDENTITY
BLOCKING_INVARIANT=THE_PERSISTED_EXECUTOR_BINDING_MUST_RESOLVE_TO_THE_ALREADY_QUALIFIED_EXACT_KILO_BINARY
BLOCKING_REASON=PINNED_KILO_7_5_15_EXECUTABLE_IS_NOT_PRESENT_AND_INSTALLED_KILO_7_5_16_HAS_A_DIFFERENT_UNQUALIFIED_HASH

EA4E64_DEPLOYMENT_PREREQUISITES=NOT_YET_QUALIFIED
EA4E64_HISTORICAL_RESULT=HOLD_BEFORE_ISSUANCE_UNCHANGED
EA4E64_RETRY_ALLOWED=NO
EA4E64A_CHECKPOINT_ALLOWED=NO_PENDING_BINARY_REQUALIFICATION_OR_EXACT_BINARY_RESTORATION
```

The durable store, anchor, reconstruction, and no-execution composition work is
implemented and passes its dedicated fake-only suite. EA-4E.64A cannot pass its
full gate because the exact frozen Kilo 7.5.15 executable named by the committed
binding contract is absent from the machine. Kilo 7.5.16 is installed, but using
it would change the qualified binary identity and is outside this phase's bounded
remediation authority.

No attempt was made to restore, download, invoke, or requalify either executable.

## Governing State

```ini
WORKTREE=C:/Users/David/Documents/Automation tool/.worktrees/ea4f-regional-hand-repair-pilot
BRANCH=feature/ea4f-regional-hand-repair-pilot
GOVERNING_COMMIT=6096ee0a79299d7ffaa6e8a17860d930c87e3846
LOCAL_HEAD=6096ee0a79299d7ffaa6e8a17860d930c87e3846
REMOTE_HEAD=6096ee0a79299d7ffaa6e8a17860d930c87e3846
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
GIT_STATE_REVERIFIED_AT_START=YES

EA4E63_DESIGN=PASS
EA4E63_PREFLIGHT=HOLD
EA4E63_EVIDENCE_CHECKPOINT=PASS
EA4E64_ISSUANCE=HOLD_BEFORE_ISSUANCE
```

The historical EA-4E.64 HOLD record remains unmodified and outside the EA-4E.64A
candidate.

## Implemented Surface

```ini
ACTIVATION_STORE_IMPLEMENTATION_FILE=tools/hermes_core/production_activation_authorization_store.py
ACTIVATION_STORE_CLASS=ProductionActivationAuthorizationStore
ACTIVATION_STORE_BOOTSTRAP_OWNER=ProductionActivationAuthStoreBootstrapper
ACTIVATION_STORE_SCHEMA_VERSION=2

APP_COMPOSITION_FILE=tools/hermes_core/production_deployment_composition.py
APP_COMPOSITION_FACTORY=ProductionDeploymentCompositionOwner.provision
APP_COMPOSITION_CONFIG_SOURCE=ProductionDeploymentPaths_AND_ProductionAppRuntimeConfig
APP_COMPOSITION_LIFETIME_OWNER=app._GOVERNED_PRODUCTION_DEPLOYMENT_OWNER

DEPLOYMENT_BINDING_STORE_SCHEMA_VERSION=1
```

Candidate implementation files:

```text
app.py
tools/hermes_core/production_app_config.py
tools/hermes_core/production_app_factory.py
tools/hermes_core/production_executor_binding.py
tools/hermes_core/production_wiring.py
tools/hermes_core/production_deployment_composition.py
tests/hermes_core/test_ea4e64a_nonlive_deployment_composition.py
.hermes/handoffs/ea4e/EA-4E.64A-NONLIVE-DEPLOYMENT-COMPOSITION-QUALIFICATION.md
```

The implementation adds explicit provisioning only. Import and ordinary app
startup do not provision stores, create bindings, issue authorization, activate
production, or execute a receiver. App composition retains the explicit owner,
and reconstruction injects the restored binding controller into the existing
production factory/wiring chain.

## Production-Class Durable State

Provisioning was explicitly executed once against the production-class local
paths without issuing authorization or invoking a receiver.

```ini
PRODUCTION_CLASS_ACTIVATION_STORE_PROVISIONED=YES
ACTIVATION_STORE_PATH=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/activation-authorization.sqlite3
ACTIVATION_STORE_ID=activation-store-9a66dfbc-5c7f-4d63-9538-aaf910d76229
ACTIVATION_STORE_EPOCH=1

EXTERNAL_STORE_ANCHOR_PROVISIONED=YES
ACTIVATION_STORE_ANCHOR_PATH_OR_ID=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/activation-authorization.anchor.json
ACTIVATION_STORE_ANCHOR_FILE_SHA256=255b1c38096ddbaa3db909ae40dcc2cd19cc130d66a71d54a2337c87c40113af
ACTIVATION_STORE_ANCHOR_CANONICAL_HASH=23e003638f1bf9b7dc1f3772a13276ec06f8413e92f4ce7252a3d302d0fcdbb6
STORE_ANCHOR_MATCHES_STORE_IDENTITY=YES

BINDING_STATE_PATH=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/executor-binding.sqlite3
INVOCATION_AUTH_STORE_PATH=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/invocation-authorization.sqlite3
INVOCATION_AUTH_ANCHOR_PATH=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/invocation-authorization.anchor.json
ACCOUNTING_STORE_PATH=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/production-accounting.sqlite3
RECOVERY_STORE_PATH=C:/Users/David/AppData/Local/Hermes/runtime/ea4e/production/production-recovery.sqlite3
```

Read-only row counts after provisioning:

```ini
ACTIVATION_AUTHORIZATION_ROWS=0
ACTIVATION_AUTHORIZATION_EVENT_ROWS=0
ACTIVATION_CEREMONY_ROWS=0
INVOCATION_AUTHORIZATION_ROWS=0
PROCESS_ACCOUNTING_EVENT_ROWS=0
MODEL_ACCOUNTING_EVENT_ROWS=0
RECOVERY_ROWS=0
BINDING_DESCRIPTOR_ROWS=1
```

## Restart and Safety Results

The composition was destroyed and reconstructed in a separate fresh Python
process. The underlying authority domain and binding descriptor were reopened;
they were not regenerated.

```ini
STORE_ID_BEFORE_RESTART=activation-store-9a66dfbc-5c7f-4d63-9538-aaf910d76229
STORE_ID_AFTER_RESTART=activation-store-9a66dfbc-5c7f-4d63-9538-aaf910d76229
STORE_EPOCH_BEFORE_RESTART=1
STORE_EPOCH_AFTER_RESTART=1
STORE_ID_SURVIVES_RESTART=YES
STORE_EPOCH_SURVIVES_RESTART=YES
PROCESS_RESTART_ROTATES_STORE_EPOCH=NO

STORE_REPLACEMENT_INVALIDATES_PRIOR_AUTHORITY_DOMAIN=YES_FAKE_TEST
STORE_CLONE_DOES_NOT_CREATE_SECOND_VALID_AUTH_DOMAIN=YES_FAKE_TEST
STORE_RESTORE_DOES_NOT_RESURRECT_INVALIDATED_AUTHORITY=YES_FAKE_EPOCH_TEST

PERSISTENT_APP_COMPOSITION_CONFIGURED=YES
APP_COMPOSITION_RECONSTRUCTION_PRESERVES_STORE_ID=YES
APP_COMPOSITION_RECONSTRUCTION_PRESERVES_STORE_EPOCH=YES
APP_COMPOSITION_RECONSTRUCTION_PRESERVES_BINDING_IDENTITY_AS_DESIGNED=YES

APP_COMPOSITION_BUILD_ISSUES_ACTIVATION_AUTH=NO
APP_COMPOSITION_BUILD_ISSUES_EXECUTION_AUTHORITY=NO
APP_COMPOSITION_BUILD_CLAIMS_INVOCATION_AUTH=NO
APP_COMPOSITION_BUILD_ACTIVATES_PRODUCTION=NO
APP_COMPOSITION_BUILD_EXECUTES_RECEIVER=NO
```

## Kilo Binding Finding

The durable descriptor and reconstruction mechanics preserve this exact record:

```ini
KILO_EXECUTOR_BINDING_PROVISIONED=YES_MECHANICALLY
KILO_EXECUTOR_BINDING_ID=binding-a5fcbadb-b088-4112-a62c-c6e36f3b1e25
KILO_EXECUTOR_RECEIVER_ID=kilo-cli-agent
KILO_EXECUTOR_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
KILO_EXECUTOR_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
KILO_EXECUTOR_BINARY_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
KILO_BINDING_ISSUED_AT=2026-09-10T21:45:12.335922+00:00
KILO_BINDING_EXPIRES_AT=2026-09-10T22:45:12.335922+00:00
KILO_BINDING_SURVIVES_APP_RESTART=YES
KILO_BINDING_ID_UNCHANGED_AFTER_RECONSTRUCTION=YES

KILO_BINDING_PROVISION_STARTS_PROCESS=NO
KILO_BINDING_LOOKUP_STARTS_PROCESS=NO
KILO_BINDING_PROVISION_INVOKES_MODEL=NO
KILO_BINDING_LOOKUP_INVOKES_MODEL=NO

CORRECT_KILO_EXECUTOR_BINDING=PASS_FAKE_POLICY_ONLY
WRONG_KILO_EXECUTOR_BINDING=DENY
MISSING_KILO_EXECUTOR_BINDING=DENY
EXPIRED_KILO_EXECUTOR_BINDING=DENY
```

The runtime identity gate fails:

```ini
FROZEN_KILO_PATH=C:/Users/David/.vscode/extensions/kilocode.kilo-code-7.5.15-win32-x64/bin/kilo.exe
FROZEN_KILO_EXPECTED_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
FROZEN_KILO_PATH_PRESENT=NO

INSTALLED_KILO_PATH=C:/Users/David/.vscode/extensions/kilocode.kilo-code-7.5.16-win32-x64/bin/kilo.exe
INSTALLED_KILO_SHA256=8ddb47c7ae088c9f2118cec8824d618eea498b3d580970a5f094c7390633a851
INSTALLED_KILO_MATCHES_FROZEN_BINARY=NO
KILO_QUALIFIED_FOR_THIS_FROZEN_BINDING=NO
```

Constructing `RealKiloProductionExecutor` does not probe or start the executable,
which is why mechanical binding tests pass. The missing exact executable was
found by the required independent frozen-identity verification. Treating the
installed successor as equivalent would weaken the contract and is prohibited.

## EA-4E.64 Prerequisite Recheck

```ini
EA4E64_PREFLIGHT_STORE_READY=YES
EA4E64_PREFLIGHT_EXTERNAL_ANCHOR_READY=YES
EA4E64_PREFLIGHT_APP_COMPOSITION_READY=YES
EA4E64_PREFLIGHT_KILO_EXECUTOR_BINDING_READY=NO_EXACT_FROZEN_BINARY_ABSENT
EA4E64_PREREQUISITES_CLOSED=NO
AUTHORIZATION_ISSUED=0
```

## Verification

All tests used the pre-existing stage-2 runtime. `jsonschema` and its direct
dependencies were added to that isolated runtime after the first full collection
could not import the schema tests; no repository dependency file was changed.

```ini
EA4E64A_DEDICATED_TESTS_COLLECTED=16
EA4E64A_DEDICATED_TESTS_PASSED=16
EA4E64A_DEDICATED_TESTS_FAILED=0

EA4E62B_REGRESSION_COLLECTED=57
EA4E62B_REGRESSION_PASSED=57
EA4E62B_REGRESSION_FAILED=0

EA4E60_EA4E61B_REGRESSION_COLLECTED=60
EA4E60_EA4E61B_REGRESSION_PASSED=60
EA4E60_EA4E61B_REGRESSION_FAILED=0

EA4E58_RETRY_REGRESSION_COLLECTED=4
EA4E58_RETRY_REGRESSION_PASSED=4
EA4E58_RETRY_REGRESSION_FAILED=0

CANONICAL_PREDECESSOR_TESTS_COLLECTED=191
CANONICAL_PREDECESSOR_TESTS_PASSED=191
CANONICAL_PREDECESSOR_TESTS_FAILED=0

DIRECT_RELEVANT_COLLECTION_COLLECTED=179
DIRECT_RELEVANT_COLLECTION_PASSED=178
DIRECT_RELEVANT_COLLECTION_FAILED=1
DIRECT_RELEVANT_FAILURE_INHERITED=YES
DIRECT_RELEVANT_FAILURE=tests/hermes_core/test_ea4e43_nonlive_feature_gate_config.py::test_explicit_enabled_fake_kilo_path

FULL_HERMES_CORE_TESTS_PASSED=3126
FULL_HERMES_CORE_TESTS_FAILED=77
FULL_HERMES_CORE_TESTS_ERRORS=16
FULL_HERMES_CORE_SUBTESTS_PASSED=104
FULL_HERMES_CORE_FAILURES_NEW_TO_EA4E64A=0
```

The complete collection's failures are historical Codex/Kilo/OpenCode identity,
receiver-mutation, obsolete contract, and live-qualification tests. All 16 setup
errors are the pre-existing locked OpenCode spool file at
`run-d8aef891.stderr.txt`. Failure-only reproduction produced the same 77
failures and 16 errors. No EA-4E.64A test failed, and no failure identified the
new deployment-composition module or its injection path.

The established 171-test sealed-aligned checkpoint remains historical evidence;
it was not relabeled as a fresh run. The current canonical 191-test predecessor
collection was rerun and passed in full.

Compilation and import passed. The only compile diagnostic was the pre-existing
`app.py` invalid-escape `SyntaxWarning`. Candidate-diff scans found no process,
shell, network, browser, OAuth, GPU, ComfyUI, or receiver/model execution call.

## Remediation History

```ini
INLINE_REMEDIATION_REQUIRED=YES
INLINE_REMEDIATION_COUNT=1
INLINE_REMEDIATION_FILES=tests/hermes_core/test_ea4e64a_nonlive_deployment_composition.py
INLINE_REMEDIATION_REASONS=CORRECTED_EXPECTED_PUBLIC_BINDING_DECISION_FROM_ALLOW_TO_BOUND
POST_REMEDIATION_FULL_REQUALIFICATION=COMPLETED

OUT_OF_SCOPE_REMEDIATION_REQUIRED=YES
OUT_OF_SCOPE_REMEDIATION=RESTORE_EXACT_QUALIFIED_KILO_7_5_15_BINARY_OR_AUTHORIZE_AND_COMPLETE_A_KILO_7_5_16_SUCCESSOR_REQUALIFICATION_AND_CONTRACT_ROLL
OUT_OF_SCOPE_REMEDIATION_PERFORMED=NO
```

## Protected WIP

The worktree reported 344 modified/untracked entries at the pre-evidence check.
That count included the EA-4E.64A candidate and phase-created pytest temp
directories as well as substantial pre-existing WIP. No item was reset, deleted,
cleaned, or staged. Explicitly protected items left outside the candidate include:

```text
.hermes/handoffs/ea4e/EA-4E.6-RECEIVER-ROUTER-FAKE-QUALIFICATION.md
tools/hermes_core/__init__.py
tools/hermes_core/receiver_registry.py
tools/hermes_core/kilo_fully_governed.py
tools/image_pipeline_v2_execution.py
tools/image_pipeline_v2_provenance.py
.hermes/handoffs/ea4e/EA-4E.64-REAL-ACTIVATION-AUTHORIZATION-ISSUANCE-CEREMONY-HOLD.md
all pre-existing untracked pytest directories and historical handoff artifacts
```

## Live Counters and Repository Boundary

```ini
AUTHORIZATION_ISSUED=0
ACTIVATION_AUTH_CLAIMED=0
PRODUCTION_ACTIVATED=NO
RECEIVER_EXECUTED=NO
MODEL_INVOKED=NO

KILO_PROCESS_STARTED=0
KILO_MODEL_INVOKED=0
OPENCODE_PROCESS_STARTED=0
OPENCODE_MODEL_INVOKED=0

NETWORK_CALLS=0
PROVIDER_API_CALLS=0
DEVICE_CODE_FLOWS_STARTED=0
OAUTH_FLOWS_STARTED=0
BROWSERS_OPENED=0
CREDENTIAL_MUTATIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0

STAGED=0
COMMIT=NO
PUSH=NO
```

## Required Next Decision

EA-4E.64A must remain on HOLD until one of these separately governed paths is
completed:

1. Restore the exact previously qualified Kilo 7.5.15 executable and independently
   verify its frozen SHA-256.
2. Design, qualify, and checkpoint a Kilo 7.5.16 successor binary/transport
   contract roll, then reprovision the expired/stale binding under that new exact
   identity.

No EA-4E.64 retry, real authorization issuance, activation, or receiver/model
execution is authorized by this evidence.
