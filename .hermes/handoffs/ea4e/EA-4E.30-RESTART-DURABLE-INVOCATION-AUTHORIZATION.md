# EA-4E.30 Restart-Durable Invocation Authorization

Date: 2026-09-06

## Disposition

EA-4E.30 reached its mandatory contract-impact stop. The current EA-4E.23
policy and EA-4E.28 issuer keep their authoritative replay state only in
process memory. Making issuance and consumption durable would change governed
semantics under the existing contract IDs. EA-4E.30 therefore defines the
required architecture and downstream impact, but does not implement or roll
the affected contracts.

```text
EA-4E.30=PARTIALLY QUALIFIED NON-LIVE
RESTART_DURABILITY_ARCHITECTURE=ESTABLISHED
EA4E23_CONTRACT_ROLL_REQUIRED=YES
CONTRACT_ROLL_PERFORMED=NO
PRODUCTION_INTEGRATION_PERFORMED=NO
LIVE_EXECUTION=NO
COMMIT=NO
PUSH=NO
```

## Governing State

The remote was freshly fetched before analysis.

```text
GIT_STATE_REVERIFIED_AT_START=YES
GOVERNING_LOCAL_HEAD=fe3f4c0eb9cfe38ac1d7b62ee789be5e2de8eb14
GOVERNING_REMOTE_HEAD=fe3f4c0eb9cfe38ac1d7b62ee789be5e2de8eb14
CURRENT_BRANCH=feature/ea4f-regional-hand-repair-pilot
LOCAL_AHEAD=0
LOCAL_BEHIND=0
STAGED_BEFORE=0
UNRELATED_WIP_PRESENT=YES
UNRELATED_WIP_TOUCHED=NO
```

## Recomputed Contracts

```text
EA4E14_EXECUTION_CONTRACT_ID=89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6
EA4E17_ISSUANCE_CONTRACT_ID=26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78
EA4E18_INTEGRATION_CONTRACT_ID=d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459
EA4E21_BINDING_CONTRACT_ID=99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7
EA4E22_INTEGRATION_CONTRACT_ID=e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a
EA4E23_INVOCATION_CONTRACT_ID=1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8
EA4E26_RUNTIME_CONTRACT_ID=c49556e63645fefc31a3f03df726d99447620b7ae6ae4a2c78b96ae0feeb8393
EA4E28_AUTH_ISSUER_CONTRACT_ID=cbf86c71356366d489920b226dfb181c3fcafc581ec567d19433a94159a6c5da
EA4E29_CALLER_INTEGRATION_CONTRACT_ID=aa9b2e1a6bb2307e814bb66913f7fdb8134a3fbb0273bfb8be000da6e480ee9a
ALL_GOVERNING_CONTRACTS_RECOMPUTED_AT_START=YES
```

Qualified receivers and their frozen transport/model bindings remain
unchanged:

```text
QUALIFIED_RECEIVER_SET=kilo-cli-agent,opencode-cli-agent
KILO_TRANSPORT_CONTRACT_ID=c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500
KILO_MODEL_BINDING_ID=b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544
OPENCODE_TRANSPORT_CONTRACT_ID=192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f
OPENCODE_MODEL_BINDING_ID=cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371
QUALIFIED_RECEIVER_SET_UNCHANGED=YES
FROZEN_RECEIVER_BINDINGS_UNCHANGED=YES
```

## Current Semantics

The canonical EA-4E.23 payload says consumption is
`atomic_at_execution_attempt_boundary`, but does not define persistence,
restart lifetime, backend identity, transaction ordering, crash atomicity, or
recovery. The implementation uses `threading.RLock`,
`_consumed_authorizations`, and `_authorization_identities`; reconstructing the
policy loses all three. EA-4E.28 similarly stores issuance replay state only in
`_issued`.

```text
EA4E23_CANONICAL_PAYLOAD_INSPECTED=YES
EA4E23_CURRENT_CONSUMPTION_LIFETIME_SEMANTIC=PROCESS-LIFETIME ONLY
EA4E23_CURRENT_RESTART_SEMANTIC=UNDEFINED; RECONSTRUCTION LOSES STATE
EA4E23_CURRENT_PERSISTENCE_SEMANTIC=NONE
CAN_RESTART_DURABILITY_BE_ADDED_WITHOUT_CHANGING_EA4E23_CONTRACT=NO
```

## Proposed Architecture

Use a dedicated SQLite invocation-authorization repository. The repository,
not the issuer, runtime, executor, adapter, or router, owns durable issuance
identity and consumption state. EA-4E.28 writes through it; EA-4E.23 validates
and atomically claims through it. EA-4E.29 continues to pass the committed
artifact explicitly. EA-4E.26 continues to own no issuance behavior and holds
no database transaction while the executor runs.

```text
PERSISTENCE_BACKEND=SQLite with explicit schema metadata and transactional rows
PERSISTENCE_BACKEND_JUSTIFICATION=local, bounded, crash-safe, transactional, and consistent with existing repository architecture
EXTERNAL_SERVICE_REQUIRED=NO
DURABLE_STATE_OWNER_COMPONENT=dedicated invocation-authorization repository
DURABLE_STATE_OWNER_REASON=one authority for issuance identity, collision history, and atomic consumption without collapsing issuer/policy/runtime roles
RUNTIME_OWNS_DURABLE_AUTH_STATE=NO
EXECUTOR_OWNS_DURABLE_AUTH_STATE=NO
ADAPTER_OWNS_DURABLE_AUTH_STATE=NO
```

### Storage Contract

Proposed schema identity:

```text
AUTH_STORE_SCHEMA_ID=hermes.production-invocation-authorization-store/v1
AUTH_STORE_SCHEMA_VERSION=1
UNKNOWN_STORE_SCHEMA_VERSION_DECISION=DENY
```

One authorization row stores:

```text
issue_request_id
issue_request_canonical_hash
authorization_id
authorization_canonical_hash
receiver_id
binding_id
enablement_id
execution_request_id
attempt_number
issued_at
expires_at
runtime_scope
delegation_class
nonce
consumed_state
consumed_at
```

Task text, prompts, outputs, executor details, adapter details, model data, and
receiver payloads are excluded. They are unnecessary for authorization replay
protection and would enlarge the sensitive state surface.

Store initialization must be explicit. A newly initialized empty temporary
store grants nothing. A configured production store that disappears, has no
recognized schema metadata, contains malformed rows, or cannot complete a
transaction fails closed; it is not silently recreated as permissive state.

### Atomic Issuance

```text
canonicalize request
-> validate resolved binding and bounded lifetime
-> BEGIN IMMEDIATE
-> check issue-request replay/collision
-> insert authorization and canonical identities
-> COMMIT
-> return immutable authorization
```

No authorization is returned before commit. Persistence failure returns a
deny/error result and no artifact. Identical issue replay returns only the
verified durable row. Divergent use of the same issue-request ID denies.

### Atomic Consumption

```text
BEGIN IMMEDIATE
-> load durable authorization by ID
-> verify schema and row integrity
-> verify canonical hash
-> verify receiver/binding/enablement/request/attempt/time identities
-> verify unconsumed
-> set consumed_state=CONSUMED and consumed_at
-> COMMIT
-> release transaction
-> call injected fake executor
```

The database lock is never held during executor execution. A crash after the
consume commit but before the executor call leaves the authorization consumed
and denies retry. A crash before commit rolls back and leaves it unconsumed.
Executor failure after commit also leaves it consumed. This is at-most-once
authorization consumption, not guaranteed executor completion.

### Restart and Replay Semantics

```text
AUTHORIZATION_ISSUANCE_DURABLE=YES (PROPOSED)
AUTHORIZATION_CONSUMPTION_DURABLE=YES (PROPOSED)
UNCONSUMED_AUTH_SURVIVES_RESTART=YES (PROPOSED)
CONSUMED_AUTH_REMAINS_CONSUMED_AFTER_RESTART=YES (PROPOSED)
EXPIRED_AUTH_REMAINS_DENIED_AFTER_RESTART=YES (PROPOSED)
CANONICAL_COLLISION_STATE_SURVIVES_RESTART=YES (PROPOSED)
MISSING_PERSISTENCE_STATE_FAILS_CLOSED=YES (PROPOSED)
CORRUPT_PERSISTENCE_STATE_FAILS_CLOSED=YES (PROPOSED)
PARTIAL_WRITE_FAILS_CLOSED=YES (PROPOSED)
```

Expiry is reevaluated against the injected current clock after restart. Old
authorizations cannot be rebound to a new binding or enablement. Cross-receiver
use reaches EA-4E.23 and denies. Consumed or expired authorizations are never
automatically reissued or refreshed. Missing records are never reconstructed
from task text, a binding, or a caller-provided artifact.

Two or more claimers use separate repository connections. `BEGIN IMMEDIATE`
plus a conditional unconsumed-to-consumed transition permits exactly one
claim. The same rule applies after reopening the store.

## Contract Impact

### EA-4E.23

```text
EA4E23_CONTRACT_CHANGE_REQUIRED=YES
EA4E23_CONTRACT_IMPACT_REASON=authoritative identity and consumed state acquire durable cross-restart lifetime, transaction ordering, corruption handling, and crash semantics not present in the frozen canonical payload
EA4E23_CANONICAL_FIELDS_CHANGED=YES; add store contract ID/schema identity and durable claim/fail-closed semantics to canonical contract material
EA4E23_CANONICAL_SEMANTICS_CHANGED=YES; consumed and collision history become restart-durable rather than process-local
EA4E23_CONTRACT_ROLL_PERFORMED=NO
```

Proposed EA-4E.23 canonical additions for a separately authorized roll:

```text
authorization_store_contract_id=<new durable-store contract ID>
consumption_lifetime=restart_durable
authorization_identity_lifetime=restart_durable
atomic_issue_order=durable_commit_before_return
atomic_consume_order=durable_commit_before_executor_call
persistence_lock_held_during_executor_call=false
post_consume_pre_executor_crash=deny_retry
precommit_crash=rollback_unconsumed
executor_failure_restores_authorization=false
missing_or_corrupt_store=deny
unknown_store_schema_version=deny
concurrent_allowed_claims=1
```

### Downstream

```text
EA4E26_CONTRACT_CHANGE_REQUIRED=YES
EA4E28_CONTRACT_CHANGE_REQUIRED=YES
EA4E29_CONTRACT_CHANGE_REQUIRED=YES
```

EA-4E.26 canonically depends on EA-4E.23, so its contract ID must roll even if
its role remains consume-only. EA-4E.28 both depends on EA-4E.23 and changes
issuance replay from process-local to durable. EA-4E.29 depends on EA-4E.26 and
EA-4E.28, so it rolls transitively while preserving explicit handoff behavior.

```text
EA4E26_CONTRACT_ROLL_PERFORMED=NO
EA4E28_CONTRACT_ROLL_PERFORMED=NO
EA4E29_CONTRACT_ROLL_PERFORMED=NO
```

## Qualification Status

The required implementation and 26-case restart matrix were not run because
they would require changing EA-4E.23 and dependent canonical contracts. Doing
that under their frozen IDs would create an ungoverned semantic change; rolling
them is expressly unauthorized in EA-4E.30.

```text
EA4E30_DEDICATED_TESTS=0
EA4E30_DEDICATED_FAILURES=0
SAFE_NONLIVE_REGRESSION_TOTAL=0
SAFE_NONLIVE_REGRESSION_FAILURES=0
QUALIFICATION_STORE_IS_TEMPORARY=NOT CREATED
PRODUCTION_AUTH_STORE_TOUCHED=NO
EXISTING_RUNTIME_STATE_MUTATED=NO
```

The next authorized implementation must use a temporary store and real
close/reopen reconstruction in its tests. It must cover all 26 cases in the
EA-4E.30 packet, use separate connections for concurrency, and retain the
EA-4E.27A executor/adapter/process tripwires.

## No-Live Accounting

```text
NEW_KILO_TASKS=0
NEW_OPENCODE_TASKS=0
NEW_MODEL_INVOCATIONS=0
NEW_RECEIVER_PROCESSES=0
REAL_KILO_EXECUTOR_CALLS=0
REAL_OPENCODE_EXECUTOR_CALLS=0
REAL_KILO_ADAPTER_CALLS=0
REAL_OPENCODE_ADAPTER_CALLS=0
LIVE_BINDINGS_CREATED=0
LIVE_INVOCATION_AUTHS_ISSUED=0
LIVE_DISPATCH_EXECUTIONS=0
PRODUCTION_BOUNDARY_REAL_EXECUTIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Repository Accounting

```text
EA4E30_MODIFIED_FILES=none
EA4E30_CREATED_FILES=.hermes/handoffs/ea4e/EA-4E.30-RESTART-DURABLE-INVOCATION-AUTHORIZATION.md
EA4E30_FILE_COUNT=1
UNRELATED_WIP_TOUCHED=NO
STAGED=0
COMMIT=NO
PUSH=NO
```

## Final State

```text
EA-4E.30=
PARTIALLY QUALIFIED NON-LIVE /
RESTART-DURABILITY SEMANTICS ESTABLISHED /
EA-4E.23 CONTRACT ROLL REQUIRED /
DOWNSTREAM CONTRACT IMPACT CLASSIFIED /
NO CONTRACT ROLL PERFORMED /
NO LIVE EXECUTION /
NOT COMMITTED

NEXT_PHASE=SEPARATE EA-4E.23 RESTART-DURABILITY CONTRACT-ROLL AUTHORIZATION
```
