# EA-4E.49 Non-Live Real-App Live-Pilot Readiness and Single-Shot Authorization Design

## Governing Baseline

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=de60e08be8f3ff9756bf2d977f309b7e84406ed8
GOVERNING_REMOTE_HEAD=de60e08be8f3ff9756bf2d977f309b7e84406ed8
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
INITIAL_STAGED=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

## EA-4E.48 Dependency

```text
EA4E48_RETRY_RESULT=PASS
FAKE_E2E_READINESS=QUALIFIED
EA4E40_ALL_PRELIVE_PREREQUISITES_CLOSED=YES
EA4E49_ALLOWED_FROM_CHECKPOINT=YES
LIVE_EXECUTION_AUTHORIZED=NO
```

Committed runtime at this baseline requires external `execution_authority` and explicit `activation`. It does not construct `ProductionIssuancePolicy` or auto-activate.

## Sealed 13-Artifact Roll

```text
EA-4E.6=292f7deeb479cd45c6f33f3466305e7f225c05d9f48f9eeb8dc13f944d7162a1
EA-4E.7=6de9f8b959db33bd2c2885396507baed47a3eadf07423c0e545afe4cc3274661
EA-4E.8=9785647334992c514ef56013c2e410be48c42a3c1813b377e601823387be67a2
EA-4E.11=af7d731ff21614f3ab0e92beb8927d3063e06707af7a9a89bc3d3b7c91e7927a
EA-4E.14=b057272ee70a4f5fceb9500ccf699097ed2de2edfc21e8f47fe3f9247e52f20b
EA-4E.17=5082b1a227a53cfe711bcf3c5d2193cd47031d75d7ec7650d8ab4c2389194e93
EA-4E.18=56471e6509ccc2e99a7b609354748c51a0ada18bda8b92648c21bec584c1ceb3
EA-4E.21=a25a6ba03b6a44f35511bec4b89c332043cd252ea3d1e185bd1b0a5c966fee33
EA-4E.22=0e9d206a0b5d78592bafad624421439774e6c7ffe34a7c9d4c41a66aeb0504bd
EA-4E.23=7bc3d2e036beacaef5aaabd054730dfbd49c57a0c36bbaab6f56894798be4687
EA-4E.26=52edc7ad0be1bf446034ad31189a9172a6a35c98c8619b113f4a836320b8887e
EA-4E.28=90c96695f6294bed90eed1b630b1b44f7faca859b6b818ea2a744c1b753eb5b1
EA-4E.29=2d2e42ebbaaa1eacabfbd9a09cf3a542f0424b26c96fb4e6b0a7984245039d87
SEALED_13_ARTIFACT_ROLL_MATCHES_CHECKPOINT=YES
```

## Receiver Identities

```text
KILO_RECEIVER_IDENTITY_MATCH=YES
KILO_VERSION=7.5.15
KILO_SHA256=78414b3fc2b908ee5cfd52433697c8493c97de2930cbedb4508c9babcb681c25
KILO_TRANSPORT_CONTRACT_ID=d38653cdceb5fceed79e3f4d251a84bac0a5d5731e44977df3c34ca00141d5bd
KILO_EXECUTABLE_BINDING_ID=01274cc23910aebfbbd4666fffea5ce560d80720160a6909e2157576ad177982
KILO_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
OPENCODE_RECEIVER_IDENTITY_MATCH=YES
OPENCODE_TRANSPORT_ID=192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f
OPENCODE_MODEL_BINDING_ID=cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371
GROK_QUALIFIED=NO
GROK_FALLBACK=NO
GROK_LIVE_AUTHORIZED=NO
```

Kilo pin hash was rechecked by reading the pinned binary bytes. `--version` was not run.

## Qualified Real-App Live Path

```text
QUALIFIED_REAL_APP_LIVE_PATH=
  ProductionInvocationAuthStoreBootstrapper.bootstrap
  ProductionAppAuthorityCollaborator.issue
  ProductionAppBindingProvisioner.bind
  ProductionAppInvocationAuthorizationProvisioner.provision
  ProductionAppFactory.build
  -> ProductionAppUserAction.submit
  -> ProductionAppCallSite.invoke
  -> ProductionAppAdapter.submit
  -> ProductionApplicationCaller.submit
  -> ProductionEntryPoint.handle
  -> GovernedProductionCaller.invoke
  -> ProductionInvocationAuthorizationIssuer.issue
  -> GovernedProductionRuntime.execute
  -> ProductionExecutionBoundary.execute
  -> RealKiloProductionExecutor.execute or RealOpenCodeProductionExecutor.execute
  -> KiloAdapter.execute or OpenCodeReceiverAdapter.execute
  -> KiloProcessController.execute / OpenCodeLiveProcess.start
```

This matches the EA-4E.48 fake path except the execution-boundary collaborator is the real executor instead of the fake one.

## Operator vs Application vs Runtime

```text
OPERATOR_CONTROLLED_STEPS=
  isolated store bootstrap/reopen
  feature-gate ENABLED in in-memory ProductionAppRuntimeConfig
  master_enable ENABLED in ProductionWiringConfig for that graph only
  explicit receiver_id
  explicit request_id
  ProductionAppAuthorityCollaborator.issue
  ProductionAppBindingProvisioner.bind of one already-constructed real executor identity
  ProductionAppInvocationAuthorizationProvisioner.provision
  teardown of binding after the request
APPLICATION_CONTROLLED_STEPS=
  ProductionAppUserAction.submit through entrypoint
RUNTIME_CONTROLLED_STEPS=
  GovernedProductionCaller.invoke issues invocation auth from the explicit issue-request
  GovernedProductionRuntime.execute validates authority/activation/binding then claim_for_execution then one executor.execute
```

```text
USER_ACTION_CREATES_AUTHORITY=NO
USER_ACTION_CREATES_ACTIVATION=NO
USER_ACTION_BINDS_EXECUTOR=NO
USER_ACTION_BOOTSTRAPS_STORE=NO
USER_ACTION_ISSUES_INVOCATION_AUTH=NO
```

## Authority / Activation

```text
LIVE_EXECUTION_AUTHORITY_ISSUER=ProductionAppAuthorityCollaborator.issue
LIVE_EXECUTION_AUTHORITY_POLICY=ProductionIssuancePolicy.evaluate
LIVE_EXECUTION_AUTHORITY_INPUT_TYPE=ProductionAppAuthorityRequest
LIVE_EXECUTION_AUTHORITY_OUTPUT_TYPE=ProductionAppAuthorityResult / DispatchAuthority
LIVE_ACTIVATION_SOURCE=issuance_result.activation sibling artifact from the same evaluate()
LIVE_ACTIVATION_TYPE=ProductionActivation
LIVE_AUTHORITY_WOULD_BE_ISSUED_EXTERNALLY_TO_RUNTIME=YES
RUNTIME_WOULD_NOT_REISSUE_AUTHORITY=YES
ACTIVATION_IS_EXPLICIT=YES
ACTIVATION_IS_SEPARATE_FROM_AUTHORITY=YES
ACTIVATION_IS_NOT_DERIVED_BY_RUNTIME=YES
ACTIVATION_IS_NOT_DERIVED_FROM_FEATURE_GATE=YES
EA4E49_LIVE_EXECUTION_AUTHORITY_ISSUED=NO
```

## Binding

```text
KILO_PRODUCTION_EXECUTOR_CLASS=tools.hermes_core.kilo_live_binding.RealKiloProductionExecutor
OPENCODE_PRODUCTION_EXECUTOR_CLASS=tools.hermes_core.opencode_live_binding.RealOpenCodeProductionExecutor
EXECUTOR_REGISTRY_CLASS=ExecutorRegistry
EXECUTOR_BINDING_PROVISIONER=ProductionAppBindingProvisioner.bind
MAX_SIMULTANEOUS_REAL_BINDINGS=1
LIVE_BINDING_LIFETIME=CONTROLLER_SCOPED until ProductionExecutorBindingController.teardown(handle)
LIVE_BINDING_CLEANUP_ACTION=explicit teardown after the single request
EA4E49_REAL_EXECUTOR_REGISTRATION=NO
EA4E49_REAL_EXECUTOR_BINDING=NO
```

Real executor classes were not instantiated in this phase.

## Invocation Authorization

```text
INVOCATION_AUTH_REQUEST_PROVISIONER=ProductionAppInvocationAuthorizationProvisioner.provision
INVOCATION_AUTH_ISSUER=ProductionInvocationAuthorizationIssuer.issue via GovernedProductionCaller.invoke
INVOCATION_AUTH_STORE=DurableInvocationAuthorizationStore reopened from explicitly bootstrapped EA-4E.47 store
INVOCATION_AUTH_CLAIM_BOUNDARY=GovernedProductionRuntime / claim_for_execution
INVOCATION_AUTH_CONSUME_BOUNDARY=atomic claim_for_execution transition to consumed state
APP_FACING_PROVISIONER_ISSUES_INVOCATION_AUTH=NO
GOVERNED_PRODUCTION_CALLER_ISSUES_INVOCATION_AUTH=YES
RUNTIME_ISSUES_INVOCATION_AUTH=NO
EXISTING_ATOMIC_INVOCATION_AUTH_CLAIM_PRESERVED=YES
EA4E49_LIVE_INVOCATION_AUTH_ISSUED=NO
EA4E49_LIVE_INVOCATION_AUTH_CLAIMED=NO
EA4E49_LIVE_INVOCATION_AUTH_CONSUMED=NO
INVOCATION_AUTH_FINAL_STATE=CONSUMED
INVOCATION_AUTH_REPLAY_ALLOWED=NO
SECOND_EXECUTION_WITH_SAME_AUTH=DENY
```

## Store

```text
LIVE_STORE_PATH_REQUIREMENT=operator-chosen isolated sqlite3 file, not named automation_state.db, parent directory already exists
LIVE_ANCHOR_PATH_REQUIREMENT=distinct operator-chosen anchor file
LIVE_STORE_BOOTSTRAP_ACTION=ProductionInvocationAuthStoreBootstrapper.bootstrap with bootstrap_explicit=True
LIVE_STORE_REOPEN_ACTION=assemble_production_composition / open_production_auth_store fail-closed reopen
STORE_BOOTSTRAP_REMAINS_OPERATOR_CONTROLLED=YES
AUTOMATION_STATE_DB_ALLOWED=NO
EA4E49_DURABLE_STORE_MUTATED=NO
```

Do not use the default production store path for the first live pilot. Use a dedicated isolated path under the Hermes runtime tree.

## Historical Incidents

```text
EA27_REPEATED_OPENCODE_INCIDENT_REVIEWED=YES
EA33A_KILO_VERSION_PROBE_INCIDENT_REVIEWED=YES
OTHER_RELEVANT_LIVE_INCIDENTS=EA-4E.33B OpenCode --version probes from qualify_runtime / _version_probe
```

EA-4E.27/27A: live OpenCode tests ran without a fake executor and polled a shared spool, producing repeated real-path activity. Mitigation: do not import or run live-capable test modules; one application request; isolated store; no retry.

EA-4E.33A/33B: metadata `--version` probes started receiver binaries from tests. Mitigation: no `--version`, no `qualify_runtime`, no adapter metadata subprocesses in EA-4E.50A/B.

```text
PROPOSED_EA4E50_LIVE_PLAN_CANNOT_REPEAT_EA27_PATTERN=YES
PROPOSED_EA4E50_LIVE_PLAN_CANNOT_REPEAT_EA33A_PATTERN=YES
```

## Process Accounting

Adapter/executor contracts: one `execute()` per request, no retry, no fallback. Process controller: one `Popen` per `execute()`. Runtime `max_invocations=1`.

```text
KILO_EXPECTED_PROCESS_COUNT=1
KILO_EXPECTED_MODEL_INVOCATION_COUNT=1
OPENCODE_EXPECTED_PROCESS_COUNT=1
OPENCODE_EXPECTED_MODEL_INVOCATION_COUNT=1
```

These are governed adapter-call counts. A second receiver process is an immediate stop. In-binary HTTP retries inside kilo.exe/opencode.exe are not a second governed process; they are outside this contract. Unexpected second `Popen` is the tripwire.

## Single-Shot Structure

```text
SINGLE_SHOT_PILOT_REQUEST_COUNT=1
KILO_AND_OPENCODE_CAN_SHARE_SIMULTANEOUS_REAL_BINDING=NO
RECOMMENDED_LIVE_PILOT_ORDER=kilo-cli-agent then opencode-cli-agent
ORDER_REASON=Kilo is the first qualified live successor (7.5.15 pin+hash); one-binding limit forbids simultaneous real bindings
LIVE_PILOT_AUTO_RETRY=NO
LIVE_PILOT_FALLBACK=NO
LIVE_PILOT_FAILOVER=NO
LIVE_PILOT_AUTHORITY_REISSUE=NO
LIVE_PILOT_INVOCATION_AUTH_REISSUE=NO
FAILED_LIVE_ATTEMPT_CONSUMES_SINGLE_SHOT_AUTHORIZATION=YES
RERUN_REQUIRES_SEPARATE_EXPLICIT_AUTHORIZATION=YES
```

Claim happens before executor.execute. Crossing into claim consumes the authorization even if the later process fails.

## Proposed Task

```text
PROPOSED_LIVE_PILOT_TASK=Reply with exactly EA4E50A_KILO_LIVE_OK (or EA4E50B_OPENCODE_LIVE_OK). Do not use tools. Do not write files. Do not run commands.
PROPOSED_LIVE_PILOT_EXPECTED_OUTPUT=exact marker string in adapter verified payload text
PILOT_TASK_MUTATES_FILES=NO
PILOT_TASK_COMMITS=NO
PILOT_TASK_PUSHES=NO
PILOT_TASK_INVOKES_SUBAGENTS=NO
PILOT_TASK_USES_GPU=NO
PILOT_TASK_REQUIRES_NETWORK_SIDE_EFFECTS=NO
PILOT_TASK_CAN_TRIGGER_RETRY_LOOP=NO
```

Kilo argv uses `--pure` and isolated HOME. Do not pass `--auto`. Do not use `--version`.

## Authorization Scope

```text
PROPOSED_EXECUTION_AUTHORITY_RECEIVER=kilo-cli-agent for 50A; opencode-cli-agent for 50B
PROPOSED_EXECUTION_AUTHORITY_OPERATION=receiver-dispatch
PROPOSED_EXECUTION_AUTHORITY_SCOPE=production
PROPOSED_EXECUTION_AUTHORITY_TTL=300
PROPOSED_EXECUTION_AUTHORITY_NONCE_POLICY=unique per request, never reused
PROPOSED_EXECUTION_AUTHORITY_REQUEST_ID_POLICY=explicit unique request_id, never reused
PROPOSED_EXECUTION_AUTHORITY_SINGLE_USE_SCOPE=YES
PROPOSED_INVOCATION_AUTH_RECEIVER=same as authority receiver
PROPOSED_INVOCATION_AUTH_OPERATION=receiver-dispatch
PROPOSED_INVOCATION_AUTH_SCOPE=production
PROPOSED_INVOCATION_AUTH_TTL=60
PROPOSED_INVOCATION_AUTH_NONCE_POLICY=unique per request
PROPOSED_INVOCATION_AUTH_SINGLE_USE=YES
PROPOSED_INVOCATION_AUTH_REPLAY_DENIED=YES
PROPOSED_ACTIVATION_MODE=ENABLED
PROPOSED_ACTIVATION_SCOPE=production / same receiver
PROPOSED_ACTIVATION_REQUEST_BOUND=YES
PERSISTENT_PRODUCTION_ACTIVATION=NO
ACTIVATION_SURVIVES_REQUEST=NO
DEFAULT_FEATURE_GATE=DISABLED
PROPOSED_LIVE_FEATURE_GATE_ENABLEMENT_EXPLICIT=YES
FEATURE_GATE_ENABLEMENT_PERSISTS_AFTER_PILOT=NO
```

Feature gate and master enable live only in the in-memory factory graph for that request. They are not written to app.py or a durable app config.

## Kilo Live Packet

```text
receiver_id=kilo-cli-agent
request_id=ea4e50a-kilo-<unique>
operation=receiver-dispatch
scope=production
feature_gate=ENABLED (in-memory factory config only)
master_enable=ENABLED (same graph only)
execution_authority=external ProductionAppAuthorityCollaborator.issue, TTL 300
activation=ENABLED sibling ProductionActivation
executor=RealKiloProductionExecutor constructed once, registered, bound via provisioner
invocation-auth issue-request=ProductionAppInvocationAuthorizationProvisioner.provision then caller.issue
store=isolated operator sqlite3 + distinct anchor
expected_process_count=1
expected_model_invocation_count=1
expected_output=EA4E50A_KILO_LIVE_OK
stop_conditions=any second process; Grok; retry; fallback; git mutation; GPU
post_run=teardown binding; prove invocation auth CONSUMED; git head unchanged
KILO_LIVE_PACKET_COMPLETE=YES
```

## OpenCode Live Packet

```text
receiver_id=opencode-cli-agent
request_id=ea4e50b-opencode-<unique>
same operator sequence after Kilo teardown
expected_output=EA4E50B_OPENCODE_LIVE_OK
OPENCODE_LIVE_PACKET_COMPLETE=YES
```

## Future Live Phase Structure

```text
SEPARATE_LIVE_AUTHORIZATION_PER_RECEIVER=YES
FUTURE_LIVE_PHASE_STRUCTURE=
  EA-4E.50A KILO REAL-APP SINGLE-SHOT LIVE PILOT
  checkpoint/review
  EA-4E.50B OPENCODE REAL-APP SINGLE-SHOT LIVE PILOT
  checkpoint/review
NEXT_LIVE_RECEIVER=kilo-cli-agent
NEXT_LIVE_PHASE_NAME=EA-4E.50A KILO REAL-APP SINGLE-SHOT LIVE PILOT — EXPLICIT LIVE AUTHORIZATION REQUIRED
```

## Abort Matrix

Abort before process start on: missing/denied authority; receiver/transport/model/router mismatch; activation disabled or missing; missing/mismatched binding; binding-limit exceeded; missing invocation-auth request; issue denial; expired auth; scope mismatch; store unavailable/integrity failure; feature gate disabled; unsupported receiver; Grok.

```text
PRE_EXECUTION_ABORT_MATRIX_COMPLETE=YES
```

## Tripwire Plan

Arm: unexpected Kilo process count; unexpected OpenCode process count; unexpected model invocation count; second execution; fallback; auth reissue; store bootstrap during app path; second binding; Grok; GPU.

```text
FUTURE_LIVE_TRIPWIRE_PLAN_COMPLETE=YES
```

## Evidence Plan

Capture: request_id, receiver_id, authority id, activation id/mode, binding id, invocation-auth id, claim/consume status, process-start count, model-invocation count, adapter result, receiver output, execution result, replay-denial, git before/after, unrelated WIP unchanged.

```text
LIVE_EVIDENCE_PLAN_COMPLETE=YES
```

## Repository Safety

```text
GIT_HEAD_UNCHANGED_BY_LIVE_PILOT=YES
STAGED_UNCHANGED_BY_LIVE_PILOT=YES
UNRELATED_WIP_UNCHANGED_BY_LIVE_PILOT=YES
RECEIVER_WRITES_REPO_FILES=NO
RECEIVER_COMMITS=NO
RECEIVER_PUSHES=NO
```

Check `git rev-parse HEAD`, `git diff --cached`, and `git status --porcelain` immediately before and after the live request. Isolated Kilo HOME may write under Hermes runtime, not the git worktree.

## Environment / Credentials

```text
KILO_EXECUTABLE_AVAILABLE=YES
OPENCODE_EXECUTABLE_AVAILABLE=YES
KILO_VERSION_MATCH=YES
OPENCODE_EXPECTED_RUNTIME_AVAILABLE=YES
REQUIRED_STORE_PARENT_AVAILABLE=YES (operator must still choose isolated paths)
KILO_LIVE_CREDENTIAL_DEPENDENCY=YES
OPENCODE_LIVE_CREDENTIAL_DEPENDENCY=YES
KILO_REQUIRED_SECRET_NAMES=isolated Hermes Kilo config under KILO_CONFIG_DIR; ambient API keys are not inherited
OPENCODE_REQUIRED_SECRET_NAMES=isolated OpenCode config; ambient API keys are not inherited
SECRET_VALUES_PRINTED=NO
```

Presence of provider tokens inside isolated config was not opened or printed.

## Hidden Audit

```text
HIDDEN_AUTHORITY_MANUFACTURE_FOUND=NO
HIDDEN_AUTO_ACTIVATION_FOUND=NO
HIDDEN_AUTO_BIND_FOUND=NO
HIDDEN_AUTO_BOOTSTRAP_FOUND=NO
HIDDEN_AUTO_RECEIVER_SELECTION_FOUND=NO
HIDDEN_UNAUTHORIZED_INVOCATION_AUTH_ISSUANCE_FOUND=NO
HIDDEN_RETRY_FOUND=NO
HIDDEN_FALLBACK_FOUND=NO
HIDDEN_FAILOVER_FOUND=NO
IMPORT_STARTS_KILO_PROCESS=NO
IMPORT_STARTS_OPENCODE_PROCESS=NO
FACTORY_BUILD_STARTS_RECEIVER=NO
```

## Repo / Activity

```text
PRODUCTION_FILES_CHANGED_BY_EA4E49=0
TEST_FILES_CHANGED_BY_EA4E49=0
APP_PY_CHANGED_BY_EA4E49=NO
LIVE_CAPABLE_TESTS_EXECUTED=NO
REAL_RECEIVER_PROCESS_TESTS_EXECUTED=NO
STAGED=0
COMMIT=NO
PUSH=NO
EA4E49_GPU_GENERATIONS=0
EA4E49_COMFYUI_CALLS=0
FUTURE_LIVE_PILOT_GPU_AUTHORIZED=NO
```

## Next Boundary

```text
NEXT_PHASE=EA-4E.50A KILO REAL-APP SINGLE-SHOT LIVE PILOT — EXPLICIT LIVE AUTHORIZATION REQUIRED
LIVE_READINESS=QUALIFIED
LIVE_EXECUTION_AUTHORIZED=NO
```
