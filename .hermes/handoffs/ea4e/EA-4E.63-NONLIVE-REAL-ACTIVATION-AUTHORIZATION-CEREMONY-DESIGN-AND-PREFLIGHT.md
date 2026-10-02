# EA-4E.63 Non-Live Real Activation-Authorization Ceremony Design and Preflight

## Result

```ini
EA4E63_DESIGN=PASS
EA4E63_PREFLIGHT=HOLD
EA4E63_CHECKPOINT_ELIGIBLE=YES
EA4E64_ISSUANCE_ALLOWED=NO

PRODUCTION_ACTIVATED=NO
RECEIVER_EXECUTED=NO
MODEL_INVOKED=NO
AUTHORIZATION_ISSUED=NO
```

EA-4E.63 froze the first-real-use ceremony contract without issuing an
authorization, activating production, starting a receiver, or invoking a model.
The non-live inspection found that the current deployment does not yet contain
the durable and process-local prerequisites required for a valid EA-4E.64
issuance. The correct result is therefore a fail-closed preflight HOLD.

## Governing State

```ini
WORKTREE=C:/Users/David/Documents/Automation tool/.worktrees/ea4f-regional-hand-repair-pilot
BRANCH=feature/ea4f-regional-hand-repair-pilot
PREFLIGHT_LOCAL_HEAD=9b0cfd845a4e320a9f5f93e8058a1a9d453f9cbf
PREFLIGHT_REMOTE_HEAD=9b0cfd845a4e320a9f5f93e8058a1a9d453f9cbf
PREFLIGHT_AHEAD=0
PREFLIGHT_BEHIND=0
PREFLIGHT_STAGED=0
EA4E64_GOVERNING_COMMIT=THE_SYNCHRONIZED_EA4E63_EVIDENCE_CHECKPOINT_COMMIT
```

The working tree contains pre-existing tracked and untracked WIP. EA-4E.63 did
not modify, stage, delete, or normalize that work. Its evidence checkpoint is
restricted to this file.

## Frozen Ceremony Contract

### Identity and target

```ini
OPERATOR_ID=hermes-local-operator
OPERATOR_IDENTITY_PROVIDER=trusted-local-host
OPERATOR_PRINCIPAL_TYPE=local-operator
OPERATOR_VERIFIER=ProductionOperatorIdentityVerifier
TASK_TEXT_CAN_SET_OPERATOR_ID=NO
REQUEST_BODY_CAN_OVERRIDE_OPERATOR_ID=NO

TARGET_RECEIVER=kilo-cli-agent
TARGET_SELECTION_REASON=FIRST_QUALIFIED_RECEIVER_IN_THE_APPROVED_KILO_THEN_OPENCODE_REAL_PILOT_ORDER
FALLBACK_RECEIVER=NONE
FAILOVER_RECEIVER=NONE
GROK_ALLOWED=NO
```

Kilo is the first target because the existing production-readiness evidence
specifies Kilo before OpenCode. This selection does not start or probe Kilo.

### Durable store and binding

```ini
ACTIVATION_AUTHORIZATION_STORE_TYPE=ProductionActivationAuthorizationStore
ACTIVATION_AUTHORIZATION_STORE_SCHEMA_VERSION=2
ACTIVATION_STORE_PATH=OPERATOR_CHOSEN_DISTINCT_HERMES_RUNTIME_PATH_REQUIRED
ACTIVATION_STORE_ANCHOR_PATH=OPERATOR_CHOSEN_DISTINCT_HERMES_RUNTIME_PATH_REQUIRED
ACTIVATION_STORE_ID=UNRESOLVED_NO_ESTABLISHED_STORE
ACTIVATION_STORE_EPOCH=UNRESOLVED_NO_ESTABLISHED_STORE

EXECUTOR_BINDING_OWNER=ProductionExecutorBindingController
EXECUTOR_BINDING_PROVISIONER=ProductionAppBindingProvisioner
EXECUTOR_BINDING_ID=UNRESOLVED_NO_LIVE_COMPOSITION_OR_EXISTING_BINDING
EXECUTOR_BINDING_MUST_PREEXIST_ISSUANCE=YES
EXECUTOR_BINDING_TRANSFER_ALLOWED=NO
MAX_SIMULTANEOUS_REAL_BINDINGS=1
```

The activation store is separate from the invocation-authorization store and
from `automation_state.db`. Its exact store and anchor paths must be explicitly
chosen and the store must be explicitly bootstrapped before EA-4E.64. The exact
binding must exist in the same configured app composition that will retain it;
an ephemeral helper-process binding is not acceptable because the issued
authorization would become unusable when that process exits.

### Authority and timing

```ini
CAPABILITY_SCOPE=production_activation.enter_request_scope
WILDCARD_SCOPE_ALLOWED=NO
SCOPE_EXPANSION_ALLOWED=NO
ACTIVATION_MODE=EXPLICIT
FEATURE_GATE_STATE=ENABLED
OPERATOR_INTENT=ISSUE_ONE_REAL_REQUEST_SCOPED_ACTIVATION_AUTHORIZATION_ONLY
REQUESTED_TTL_SECONDS=300
MAX_ISSUANCE_COUNT=1
AUTOMATIC_RETRY=NO
AUTOMATIC_REISSUE=NO
CEREMONY_ID_POLICY=FRESH_COORDINATOR_GENERATED_UUID_PER_ATTEMPT
CEREMONY_ID_REUSE_ALLOWED=NO
NONCE_POLICY=FRESH_SINGLE_USE_OPERATOR_REQUEST_NONCE
```

The 300-second TTL is the existing production authority default. Issuance must
not outlive the exact executor binding. The future EA-4E.64 request ID and nonce
must be generated once after every prerequisite is frozen and must not be reused
after a denial or partial ceremony.

### Required inputs and dependencies

EA-4E.64 may begin only when all of the following are simultaneously true:

1. Local and remote HEAD are synchronized at the exact EA-4E.63 checkpoint SHA.
2. The production activation-authorization store and separate anchor exist,
   validate as schema version 2, and expose one durable store ID and epoch.
3. A configured app composition remains alive with a pre-registered qualified
   Kilo executor and exactly one unexpired Kilo binding.
4. The binding's receiver, executor identity, transport contract, model binding,
   runtime scope, and expiry match the frozen Kilo contract.
5. Kilo credential readiness passes structurally without starting or probing the
   receiver and without logging credential material.
6. Recovery reports no unresolved request and the activation store reports no
   outstanding `ISSUED` or `CLAIMED` authorization.
7. The verified configured operator is `hermes-local-operator`.
8. The activation feature gate is explicitly enabled for the composed host, but
   no governed production request is submitted.

### Ceremony order

```text
verify synchronized governing commit
-> verify configured operator identity
-> verify durable activation store identity and epoch
-> verify no outstanding authorization or unresolved recovery
-> verify exact existing Kilo binding and remaining TTL
-> run structural credential readiness preflight
-> construct one request with minimal capability scope
-> coordinator creates one fresh ceremony ID
-> durably begin ceremony and write verification events
-> issue and persist at most one authorization
-> reload and verify the stored artifact and ISSUED state
-> stop before claim, activation, invocation authorization, submit, or execution
```

Required successful event prefix:

```text
CEREMONY_REQUESTED
-> OPERATOR_IDENTITY_VERIFIED
-> STORE_LINEAGE_VERIFIED
-> CEREMONY_PREFLIGHT_PASSED
-> CEREMONY_BINDING_RESERVED
-> ACTIVATION_AUTH_ISSUED
```

### Cancellation, revocation, and expiry

An `ISSUED` authorization remains cancellable only by the same verified operator
through `ProductionActivationAuthorizationCeremonyCoordinator.cancel`, using an
allowed reason. Cancellation releases the exact reserved binding and records
`ACTIVATION_AUTH_CANCELLED`, `BINDING_RELEASED`, and `CEREMONY_CANCELLED`.

Revocation applies only after claim and is outside EA-4E.64 because EA-4E.64 may
not claim the authorization. Expiry makes the authorization unusable. No expiry,
denial, cancellation, or failure may trigger an automatic retry, replacement
binding, fallback receiver, or reissue.

### Audit and one-shot accounting

EA-4E.64 must record and verify:

- one ceremony ID;
- one request ID and one nonce;
- the verified operator ID;
- the exact synchronized governing commit;
- the durable activation store ID and epoch;
- the exact Kilo executor binding ID;
- the canonical capability-scope hash;
- at most one authorization ID and artifact hash;
- the complete durable event prefix and final `ISSUED` state;
- zero claims, activations, invocation authorizations, receiver processes, model
  invocations, retries, fallbacks, or failovers.

## Preflight Evidence

Read-only source and runtime inspection produced:

```ini
APP_CONFIGURE_FUNCTION_PRESENT=YES
APP_CONFIGURE_PRODUCTION_CALL_SITES=0
APP_ISSUE_ACTION_PRESENT=YES
APP_ISSUER_CONFIGURED_BY_STARTUP=NO
PRODUCTION_RUNTIME_DIRECTORY_EXISTS=NO
ESTABLISHED_ACTIVATION_AUTHORIZATION_STORE_FOUND=NO
ESTABLISHED_ACTIVATION_AUTHORIZATION_ANCHOR_FOUND=NO
RUNNING_CONFIGURED_APP_HOST_FOUND=NO
EXISTING_PRODUCTION_EXECUTOR_BINDING_FOUND=NO
```

`configure_governed_production_action()` correctly rejects a missing activation
store and forbids automatic real-executor registration. The ceremony coordinator
correctly requires an existing receiver binding before issuance. No production
caller currently invokes the configuration function, and bindings are owned by
an in-memory controller. Creating a store and binding in a short-lived helper
would not satisfy the frozen contract because the binding would disappear when
the helper exits.

## Abort Conditions

EA-4E.64 must stop before issuance if any frozen input is absent, stale, changed,
expired, mismatched, unverified, or ambiguous. It must also stop on remote drift,
protected-WIP overlap, existing outstanding authorization, unresolved recovery,
credential-readiness denial, more than one active binding, receiver substitution,
or any request to broaden capability scope.

Any unexpected receiver process, model invocation, browser, network, GPU,
ComfyUI, scheduler, fallback, failover, retry, claim, activation, or governed
production submission is an immediate incident and terminates the ceremony.

## Required Narrow Remediation

Before EA-4E.64 can be re-authorized, a separate non-live phase must define and
qualify the durable deployment owner for:

1. explicit activation-store and anchor bootstrap/reopen;
2. explicit qualified Kilo executor registration;
3. explicit one-binding provisioning;
4. configured app-composition lifetime across issuance and later activation;
5. safe operator inspection of store lineage, binding identity, recovery state,
   and outstanding authorization count.

This is deployment composition work, not permission to issue authority or run a
receiver. It must preserve all existing fail-closed defaults and must not auto-run
at import, application startup, scheduler startup, or ordinary user action.

## Final State

```ini
EA4E63_DESIGN_RESULT=PASS
EA4E63_PREFLIGHT_RESULT=HOLD
EA4E63_EVIDENCE_CHECKPOINT_NEXT=YES
EA4E64_REAL_ISSUANCE_NEXT=NO
EA4E64_BLOCKER=NO_DURABLE_ACTIVATION_STORE_AND_NO_PERSISTENT_CONFIGURED_EXACT_EXECUTOR_BINDING

PRODUCTION_ACTIVATED=NO
PRODUCTION_ACTIVATION_AUTHORIZED=NO
REAL_ACTIVATION_AUTHORIZATION_ISSUED=NO
RECEIVER_EXECUTED=NO
MODEL_INVOKED=NO
```
