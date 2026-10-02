# EA-4E.31 Restart-Durability Contract Roll

Date: 2026-09-06

## Governing State

The remote reference was freshly fetched before any EA-4E.31 edit.

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

EA-4E.30 exists as permitted uncommitted evidence and remains unchanged by
this phase.

## EA-4E.30 Input

```text
EA4E30_RESULT=PARTIALLY QUALIFIED NON-LIVE
EA4E30_CONTRACT_ROLL_REQUIRED=YES
PRODUCTION_DURABILITY_IMPLEMENTATION_ADDED=NO
```

## Preserved Contracts

The unaffected contracts were recomputed from the governing checkout before
and after the roll.

```text
EA4E14_EXECUTION_CONTRACT_ID=89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6
EA4E17_ISSUANCE_CONTRACT_ID=26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78
EA4E18_INTEGRATION_CONTRACT_ID=d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459
EA4E21_BINDING_CONTRACT_ID=99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7
EA4E22_INTEGRATION_CONTRACT_ID=e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a
UNAFFECTED_CONTRACTS_RECOMPUTED=YES
UNAFFECTED_CONTRACTS_UNCHANGED=YES
EA4E14_CONTRACT_ROLLED=NO
EA4E17_CONTRACT_ROLLED=NO
EA4E18_CONTRACT_ROLLED=NO
EA4E21_CONTRACT_ROLLED=NO
EA4E22_CONTRACT_ROLLED=NO
```

No receiver, transport, model-binding, adapter, or execution contract was
rolled.

## Old Contract Chain

The old identities remain named historical constants in their owning modules.
They were not reused for the new semantics.

```text
OLD_EA4E23_CONTRACT_ID=1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8
OLD_EA4E26_CONTRACT_ID=c49556e63645fefc31a3f03df726d99447620b7ae6ae4a2c78b96ae0feeb8393
OLD_EA4E28_CONTRACT_ID=cbf86c71356366d489920b226dfb181c3fcafc581ec567d19433a94159a6c5da
OLD_EA4E29_CONTRACT_ID=aa9b2e1a6bb2307e814bb66913f7fdb8134a3fbb0273bfb8be000da6e480ee9a
OLD_CONTRACT_CHAIN_RECORDED=YES
OLD_EA4E23_CONTRACT_PRESERVED_HISTORICALLY=YES
OLD_EA4E23_NOT_MUTATED_IN_PLACE=YES
```

## New EA-4E.23 Contract

```text
NEW_EA4E23_SCHEMA_ID=hermes.production-invocation-authorization.receiver-dispatch/v2
NEW_EA4E23_VERSION=ea4e.23r1
NEW_EA4E23_ARTIFACT_VERSION=2
NEW_EA4E23_CONTRACT_ID=e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91
```

The canonical payload retains all EA-4E.23 receiver, binding, enablement,
request, attempt, TTL, default-deny, failure-consumption, and pre-execution
rejection semantics. It adds these exact restart-durability semantics:

```text
authorization_store_schema_id=hermes.production-invocation-authorization-store/v1
authorization_store_schema_version=1
authorization_identity_lifetime=restart_durable
authorization_issuance_state_lifetime=restart_durable
authorization_consumption_state_lifetime=restart_durable
consumption_semantics=atomic_durable_at_execution_attempt_boundary
consumed_remains_consumed_after_restart=true
unconsumed_valid_authorization_survives_restart=true
expiry_rechecked_against_current_clock_after_restart=true
canonical_collision_identity_survives_restart=true
replay_protection_survives_restart=true
single_use_survives_restart=true
attempt_limit_survives_restart=true
corrupt_durable_state=DENY
missing_durable_state=DENY
unsupported_store_schema=DENY
durable_consume_committed_before_executor_call=true
persistence_lock_held_during_executor_call=false
failed_executor_attempt_consumes_authorization=true
pre_execution_rejection_consumes_authorization=false
```

```text
EA4E23_IDENTICAL_PAYLOAD_IDENTICAL_CONTRACT=YES
EA4E23_MAPPING_ORDER_IRRELEVANT=YES
EA4E23_IRRELEVANT_TASK_TEXT_IRRELEVANT=YES
EA4E23_DURABILITY_SEMANTIC_CHANGE_INVALIDATES=YES
EA4E23_MAX_TTL_CHANGE_INVALIDATES=YES
EA4E23_ATTEMPT_LIMIT_CHANGE_INVALIDATES=YES
EA4E23_RECEIVER_SCOPE_CHANGE_INVALIDATES=YES
EA4E23_RESTART_DURABILITY_ENCODED=YES
```

## New EA-4E.26 Contract

```text
NEW_EA4E26_SCHEMA_ID=hermes.dual-receiver-governed-production-runtime/v2
NEW_EA4E26_VERSION=ea4e.26r1
NEW_EA4E26_ARTIFACT_VERSION=2
NEW_EA4E26_CONTRACT_ID=84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67
NEW_EA4E26_BINDS_NEW_EA4E23=YES
```

Its canonical payload requires explicit receiver selection, external
invocation authorization, a pre-existing EA-4E.21 binding, EA-4E.22
resolution, the restart-durable EA-4E.23 contract, and an atomic durable claim.
It keeps runtime issuance, automatic authorization, automatic binding, retry,
fallback, and failover disabled; default production state remains off.

```text
EA4E26_IDENTICAL_PAYLOAD_IDENTICAL_CONTRACT=YES
EA4E26_MAPPING_ORDER_IRRELEVANT=YES
EA4E26_IRRELEVANT_TASK_TEXT_IRRELEVANT=YES
EA4E23_CONTRACT_CHANGE_INVALIDATES_EA4E26=YES
RECEIVER_SET_CHANGE_INVALIDATES_EA4E26=YES
EXTERNAL_AUTH_REQUIREMENT_CHANGE_INVALIDATES_EA4E26=YES
```

## New EA-4E.28 Contract

```text
NEW_EA4E28_SCHEMA_ID=hermes.production-invocation-authorization-issuer/v2
NEW_EA4E28_VERSION=ea4e.28r1
NEW_EA4E28_ARTIFACT_VERSION=2
NEW_EA4E28_CONTRACT_ID=395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1
NEW_EA4E28_BINDS_NEW_EA4E23=YES
```

Its payload requires durable commit before authorization return, prohibits
visibility before commit, and returns no usable authorization on persistence
failure. The issuer still cannot route, bind, activate, execute, or perform
I/O.

```text
EA4E28_IDENTICAL_PAYLOAD_IDENTICAL_CONTRACT=YES
EA4E23_CONTRACT_CHANGE_INVALIDATES_EA4E28=YES
DURABLE_COMMIT_REQUIREMENT_CHANGE_INVALIDATES_EA4E28=YES
```

## New EA-4E.29 Contract

```text
NEW_EA4E29_SCHEMA_ID=hermes.governed-production-caller/v2
NEW_EA4E29_VERSION=ea4e.29r1
NEW_EA4E29_ARTIFACT_VERSION=2
NEW_EA4E29_CONTRACT_ID=821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166
NEW_EA4E29_BINDS_NEW_EA4E28=YES
NEW_EA4E29_BINDS_NEW_EA4E26=YES
```

The caller must request authorization explicitly, receive only a durably
committed artifact, and pass it explicitly to the runtime. It cannot synthesize
authorization, bypass the issuer/store, reissue after denial, refresh expiry,
or execute a receiver directly.

```text
EA4E29_IDENTICAL_PAYLOAD_IDENTICAL_CONTRACT=YES
EA4E28_CONTRACT_CHANGE_INVALIDATES_EA4E29=YES
EA4E26_CONTRACT_CHANGE_INVALIDATES_EA4E29=YES
CALLER_AUTO_REISSUE_CHANGE_INVALIDATES_EA4E29=YES
```

## Dependency Graph

```text
EA4E23_DEPENDS_ON=EA4E14,EA4E17,EA4E18,EA4E21,EA4E22
EA4E26_DEPENDS_ON=EA4E14,EA4E17,EA4E18,EA4E21,EA4E22,NEW_EA4E23
EA4E28_DEPENDS_ON=EA4E21,EA4E22,NEW_EA4E23
EA4E29_DEPENDS_ON=EA4E22,NEW_EA4E26,NEW_EA4E28
CONTRACT_DEPENDENCY_GRAPH_ACYCLIC=YES
```

## Tests

The regression selection was limited to contract/static and established fake
EA-4E.23 through EA-4E.29 suites. No live qualification file was run.

```text
EA4E31_CONTRACT_TESTS=25 passed
EA4E31_CONTRACT_TEST_FAILURES=0
EA4E30_CONTRACT_IMPACT_TESTS=covered by EA4E31 contract mutation/dependency tests
EA4E29_SAFE_CONTRACT_TESTS=passed in combined safe suite
EA4E28_SAFE_CONTRACT_TESTS=passed in combined safe suite
EA4E27_SAFE_CONTRACT_TESTS=passed in combined safe suite
EA4E26_SAFE_CONTRACT_TESTS=passed in combined safe suite
EA4E23_SAFE_CONTRACT_TESTS=passed in combined safe suite
SAFE_CONTRACT_REGRESSION_TOTAL=207 passed
SAFE_CONTRACT_REGRESSION_FAILURES=0
```

## Implementation Boundary

Only contract constants, canonical payload construction, contract hashes,
contract tests, and this evidence changed.

```text
PRODUCTION_DURABILITY_IMPLEMENTATION_ADDED=NO
SQLITE_STORE_IMPLEMENTED=NO
RUNTIME_PERSISTENCE_IMPLEMENTED=NO
ISSUER_PERSISTENCE_IMPLEMENTED=NO
CALLER_PERSISTENCE_IMPLEMENTED=NO
RUNTIME_EXECUTION_BEHAVIOR_CHANGED=NO
```

## Files

Modified:

```text
tools/hermes_core/production_invocation_authorization.py
tools/hermes_core/governed_production_runtime.py
tools/hermes_core/production_invocation_authorization_issuer.py
tools/hermes_core/governed_production_caller.py
```

Created:

```text
tests/hermes_core/test_ea4e31_restart_durability_contracts.py
.hermes/handoffs/ea4e/EA-4E.31-RESTART-DURABILITY-CONTRACT-ROLL.md
```

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

## Final Disposition

```text
EA-4E.31=
QUALIFIED NON-LIVE /
EA-4E.23 RESTART-DURABILITY CONTRACT ROLLED /
EA-4E.26 DOWNSTREAM CONTRACT ROLLED /
EA-4E.28 DOWNSTREAM CONTRACT ROLLED /
EA-4E.29 DOWNSTREAM CONTRACT ROLLED /
OLD CONTRACT CHAIN PRESERVED /
UNAFFECTED CONTRACTS UNCHANGED /
CONTRACT DEPENDENCY GRAPH VERIFIED /
DETERMINISTIC CONTRACT HASHES VERIFIED /
NO DURABILITY IMPLEMENTATION ADDED /
NO LIVE EXECUTION /
NOT COMMITTED

NEXT_PHASE=EA-4E.32 RESTART-DURABLE AUTHORIZATION IMPLEMENTATION AND NON-LIVE QUALIFICATION
```
