# EA-4E.21 PRODUCTION REAL-EXECUTOR BINDING POLICY

## GOVERNING CHECKPOINT

- Local HEAD: `b7f93450e4a4bc8826f0439e1a640a2c5bd61dac`
- Remote HEAD: `b7f93450e4a4bc8826f0439e1a640a2c5bd61dac`
- Branch: `feature/ea4f-regional-hand-repair-pilot`

## ARCHITECTURE PURPOSE

EA-4E.21 establishes the permanent runtime-control layer between qualified real executor implementations and production ExecutorRegistry registration. It answers: "MAY THIS QUALIFIED REAL EXECUTOR BE BOUND INTO THIS RUNTIME REGISTRY NOW?"

## SEPARATION OF CONCERNS

```
ROUTING != ISSUANCE != AUTHORIZATION != ACTIVATION != BINDING != EXECUTION
```

- `ROUTE_SELECTED != EXECUTOR_BINDING_AUTHORIZED`
- `AUTHORITY_ISSUED != EXECUTOR_BINDING_AUTHORIZED`
- `PRODUCTION_ACTIVATED != EXECUTOR_BOUND`
- `EXECUTOR_BOUND != EXECUTION_AUTHORIZED`
- `EXECUTOR_BOUND != RECEIVER_EXECUTED`
- `RUNTIME_ENABLEMENT != PERSISTENT_ENABLEMENT`
- `BINDING POLICY != RECEIVER SELECTION`
- `BINDING POLICY != EXECUTION POLICY`

## SCHEMA ID

```
hermes.production-executor-binding.receiver-dispatch/v1
```

## CONTRACT ID

```
77a7022e60a8c771b87041a28b7b4e22eaafe2e32b6d12325304373597143baf
```

## CANONICAL CONTRACT MATERIAL

- Qualified receiver set: kilo-cli-agent, opencode-cli-agent
- Receiver transport/model bindings (see below)
- Executor implementation bindings (see below)
- Current EA-4E.17A contract dependency: `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78`
- Current EA-4E.18 contract dependency: `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459`
- Default deny
- Runtime-only semantics
- TTL required / max TTL 3600s
- Simultaneous binding limit: 1
- Replay/collision semantics with cross-receiver precedence
- No automatic receiver selection
- No retry / no fallback / no failover
- Explicit teardown required
- Temporal validation with injectable clock
- Future-issued rejection

## DEFAULT DENY BEHAVIOR

```
DEFAULT_BINDING_DECISION=DENY
MISSING_ENABLEMENT=REJECT
MISSING_RECEIVER=REJECT
UNSUPPORTED_RECEIVER=REJECT
MISSING_REQUIRED_BINDING_MATERIAL=REJECT
```

## QUALIFIED RECEIVER BINDINGS

### kilo-cli-agent

- Transport: `c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500`
- Model: `b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544`
- Executor: `RealKiloProductionExecutor`

### opencode-cli-agent

- Transport: `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f`
- Model: `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371`
- Executor: `RealOpenCodeProductionExecutor`

## ENABLEMENT ARTIFACT

`ProductionExecutorBindingEnablement` — explicit enablement request including:
- enablement_id, receiver_id, transport_contract_id, model_binding_id
- executor_identity, executor_factory, runtime_scope, delegation_class
- issued_at, expires_at (explicit temporal origin and expiration)
- max_binding_ttl_seconds, max_bound_executors, enabled, request_nonce

Distinct from ProductionActivation (which authorizes execution scope, not registration).

## BINDING POLICY

`ProductionExecutorBindingPolicy` — evaluates enablement against 13 gates:
1. Enablement enabled state
2. Receiver present
3. Receiver in qualified set
4. Runtime scope allowed
5. Delegation class allowed
6. TTL positive and within max
7. Max bound executors positive
8. Transport contract matches receiver
9. Model binding matches receiver
10. Executor identity matches receiver
11. Actual expiration validation (injected clock)
12. Enablement-ID collision check (cross-receiver precedes generic collision)
13. Binding limit (only for genuinely new bindings)

## BINDING CONTROLLER

`ProductionExecutorBindingController` — receives explicit enablement, calls policy, resolves executor identity, registers into runtime ExecutorRegistry, returns binding handle, supports teardown.

Must NOT: select receiver, issue authority/activation, create execution requests, call coordinator/boundary, call executor/adapter, start process, invoke model.

## RUNTIME-ONLY SEMANTICS

- BINDING_PERSISTS_ACROSS_PROCESS_RESTART=NO
- BINDING_WRITES_ENABLEMENT_TO_GLOBAL_CONFIG=NO
- BINDING_MUTATES_APPLICATION_DEFAULTS=NO
- BINDING_SURVIVES_CONTROLLER_TEARDOWN=NO
- PERSISTENT_PRODUCTION_EXECUTION_ENABLED=NO

## TTL SEMANTICS

- BINDING_TTL_REQUIRED=YES
- MAX_BINDING_TTL=3600s
- UNBOUNDED_BINDING_ALLOWED=NO
- EXPIRED_ENABLEMENT_REJECTED=YES
- TTL_ABOVE_MAX_REJECTED=YES

## TEMPORAL VALIDATION SEMANTICS

- ENABLEMENT_HAS_EXPLICIT_TEMPORAL_ORIGIN=YES (issued_at)
- ENABLEMENT_HAS_EXPLICIT_EXPIRATION=YES (expires_at)
- EXPIRATION_USES_INJECTED_CLOCK=YES
- EXPIRATION_USES_SYSTEM_CLOCK=NO
- TTL_RANGE_VALIDATION_DISTINCT_FROM_EXPIRATION_VALIDATION=YES
- FUTURE_ISSUED_REJECTION=YES (reject if issued_at > now)
- EXACT_EXPIRATION_BOUNDARY_BEHAVIOR=EXPIRED (now == expires_at → expired)

## BINDING-COUNT SEMANTICS

- MAX_SIMULTANEOUS_REAL_BINDINGS=1
- BINDING_LIMIT_ENFORCED=YES
- AUTOMATIC_REPLACEMENT=NO
- AUTOMATIC_RECEIVER_SWITCH=NO

## REPLAY/COLLISION SEMANTICS

- IDENTICAL_DUPLICATE → IDEMPOTENT_EXISTING_BINDING (no new binding created)
- ENABLEMENT_ID_COLLISION → REJECT (same ID + same receiver + conflicting canonical)
- CROSS_RECEIVER_BINDING_REPLAY → REJECT (same ID + different receiver)
- CROSS_RECEIVER_BINDING_REPLAY_DISTINCT=YES
- CROSS_RECEIVER_BINDING_REPLAY_PRECEDENCE_OVER_GENERIC_COLLISION=YES

## NO RECEIVER SELECTION PROOF

- TASK_TEXT_BINDING_SELECTION=NO
- ENVIRONMENT_BINDING_SELECTION=NO
- EXECUTABLE_DISCOVERY_BINDING_SELECTION=NO
- MODEL_AVAILABILITY_BINDING_SELECTION=NO
- PRIOR_SUCCESS_BINDING_SELECTION=NO
- DEFAULT_RECEIVER=NONE

## NO RETRY/FAILOVER PROOF

- AUTOMATIC_BINDING_RETRY_ENABLED=NO
- BINDING_RETRY_ATTEMPTS=0
- KILO_TO_OPENCODE_BINDING_FALLBACK=NO
- OPENCODE_TO_KILO_BINDING_FALLBACK=NO
- FALLBACK_ENABLED=NO
- FAILOVER_ENABLED=NO

## TEARDOWN

- BINDING_HANDLE_RETURNED=YES
- TEARDOWN_SUPPORTED=YES
- TEARDOWN_REMOVES_ONLY_AUTHORIZED_BINDING=YES
- TEARDOWN_LEAVES_UNRELATED_BINDINGS_UNCHANGED=YES
- DOUBLE_TEARDOWN_BEHAVIOR: Returns False (idempotent)

---

# EA-4E.21A DEFECT REMEDIATION

## Original Failure Count

- EA4E21_BASELINE_TESTS_TOTAL: 31
- EA4E21_BASELINE_PASSED: 14
- EA4E21_BASELINE_FAILED: 17
- UNCLASSIFIED_FAILURES: 0

## Complete Failure Classification

| Failure | Category | Root Cause |
|---------|----------|------------|
| test_missing_enablement_rejected | TEST_FIXTURE_ERROR | `_make_enablement(enabled=False)` conflicted with dataclass default via `**overrides` |
| test_wrong_kilo_transport_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_wrong_kilo_model_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_wrong_opencode_transport_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_wrong_opencode_model_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_kilo_executor_for_opencode_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_opencode_executor_for_kilo_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_invalid_ttl_zero_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_ttl_above_max_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_unsupported_runtime_scope_rejected | TEST_FIXTURE_ERROR | Same fixture bug |
| test_enablement_id_collision_rejected | ENABLEMENT_REPLAY | Policy didn't record allowments |
| test_cross_receiver_binding_replay_rejected | CROSS_RECEIVER_REPLAY | Same as above |
| test_multi_field_cross_receiver_replay | CROSS_RECEIVER_REPLAY | Same as above |
| test_controller_bind_rejected_does_not_mutate_registry | REGISTRY_MUTATION | Controller mutated registry before policy check |
| test_binding_contract_deterministic | CONTRACT_DETERMINISM | `NameError: name 'v' is not defined` |
| test_identical_contract_inputs_identical_hash | CONTRACT_DETERMINISM | Same `NameError` |
| test_system_clock_not_required | CLOCK | `BindingClock.now_iso()` fell back to `datetime.now()` |

## Remediation Applied

### Clock
- Removed `datetime.now()` fallback from `BindingClock`
- Now requires explicit `now: str` parameter

### Contract Determinism
- Fixed `NameError` in dict comprehension (replaced `v[` with `QUALIFIED_RECEIVER[k][`)

### Policy Gate Order
- Previous: binding limit before collision check
- Current: collision check before binding limit

### Registry Mutation
- Controller now passes policy result to registry only after ALLOW decision

## EA-4E.21A Test Results

- EA4E21_TESTS: 31 passed / 0 failed

---

# EA-4E.21B BINDING-LIFECYCLE SEMANTICS REMEDIATION

## Previous Gate-Order Defect

Binding limit was checked BEFORE enablement-ID replay/collision, which could mask the correct semantic classification. A previously issued enablement could be misclassified as `BINDING_LIMIT_EXCEEDED` when the correct classification was `IDENTICAL_DUPLICATE`, `ENABLEMENT_ID_COLLISION`, or `CROSS_RECEIVER_BINDING_REPLAY`.

## Corrected Gate Order

```
1.  Enablement must be enabled
2.  Receiver must be present
3.  Receiver must be in qualified set
4.  Runtime scope must be allowed
5.  Delegation class must be allowed
6.  TTL must be positive and within max
7.  Max bound executors must be positive
8.  Transport contract must match receiver binding
9.  Model binding must match receiver binding
10. Executor identity must match receiver binding
11. Actual expiration validation using injected clock
12. Enablement-ID collision check (cross-receiver takes precedence)
13. Binding limit must not be exceeded (only for genuinely new bindings)
```

REPLAY_COLLISION_CHECK_PRECEDES_BINDING_LIMIT=YES

## Active-Binding Collision Proof

| Field | Value |
|-------|-------|
| ACTIVE_BINDING_COLLISION_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| ACTIVE_BINDING_COLLISION_MASKED_BY_BINDING_LIMIT | NO |
| ACTIVE_BINDING_COLLISION_REGISTRY_MUTATED | NO |

## Active-Binding Cross-Receiver Replay Proof

| Field | Value |
|-------|-------|
| ACTIVE_KILO_TO_OPENCODE_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| ACTIVE_OPENCODE_TO_KILO_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| ACTIVE_BINDING_CROSS_RECEIVER_REPLAY_MASKED_BY_BINDING_LIMIT | NO |
| ACTIVE_BINDING_CROSS_RECEIVER_REPLAY_REGISTRY_MUTATED | NO |

## Multi-Field Cross-Receiver Replay Proof

| Field | Value |
|-------|-------|
| ACTIVE_MULTI_FIELD_CROSS_RECEIVER_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| MULTI_FIELD_REPLAY_MASKED_BY_BINDING_LIMIT | NO |

## Identical Duplicate Semantics

| Field | Value |
|-------|-------|
| IDENTICAL_DUPLICATE_BEHAVIOR | IDEMPOTENT_EXISTING_BINDING |
| IDENTICAL_DUPLICATE_WHILE_LIMIT_FULL_RESULT | IDENTICAL_DUPLICATE (not BINDING_LIMIT_EXCEEDED) |
| IDENTICAL_DUPLICATE_MASKED_BY_BINDING_LIMIT | NO |
| IDENTICAL_DUPLICATE_NEW_BINDING_CREATED | NO |
| IDENTICAL_DUPLICATE_REGISTRY_MUTATED | NO |
| IDENTICAL_DUPLICATE_EXECUTOR_REGISTERED_AGAIN | NO |
| IDENTICAL_DUPLICATE_BINDING_COUNT_INCREMENTED | NO |
| IDENTICAL_DUPLICATE_RETURNS_EXISTING_BINDING_IDENTITY | YES |
| IDENTICAL_DUPLICATE_EXTENDS_EXPIRY | NO |
| IDENTICAL_DUPLICATE_RESETS_TTL | NO |

## Binding Limit for Genuinely New Requests

| Field | Value |
|-------|-------|
| GENUINELY_NEW_SECOND_BINDING_RESULT | REJECT / BINDING_LIMIT_EXCEEDED |
| GENUINELY_NEW_SECOND_BINDING_REGISTRY_MUTATED | NO |
| GENUINELY_NEW_SECOND_BINDING_EXECUTOR_REGISTERED | NO |

## Temporal Artifact Fields

- issued_at: explicit temporal origin
- expires_at: explicit expiration
- Both are ISO 8601 timestamps
- Expiration derived deterministically: expires_at = issued_at + ttl_seconds

## Actual Expiration Proof

| Field | Value |
|-------|-------|
| ENABLEMENT_HAS_EXPLICIT_TEMPORAL_ORIGIN | YES |
| ENABLEMENT_HAS_EXPLICIT_EXPIRATION | YES |
| EXPIRATION_USES_INJECTED_CLOCK | YES |
| EXPIRATION_USES_SYSTEM_CLOCK | NO |
| TTL_RANGE_VALIDATION_DISTINCT_FROM_EXPIRATION_VALIDATION | YES |

## Expiration Validation Proof

| Field | Value |
|-------|-------|
| EXPIRED_ENABLEMENT_RESULT | REJECT / ENABLEMENT_EXPIRED |
| EXPIRED_ENABLEMENT_REJECTED | YES |
| EXPIRED_ENABLEMENT_REJECTION_DUE_TO_ACTUAL_TIME_COMPARISON | YES |
| EXPIRED_ENABLEMENT_REJECTION_DUE_TO_INVALID_TTL_RANGE | NO |
| EXPIRED_ENABLEMENT_REGISTRY_MUTATED | NO |

## Not-Yet-Expired Proof

| Field | Value |
|-------|-------|
| NOT_YET_EXPIRED_ENABLEMENT_TIME_VALID | YES |

## Exact Expiration Boundary

| Field | Value |
|-------|-------|
| EXACT_EXPIRATION_BOUNDARY_BEHAVIOR | EXPIRED (now == expires_at → rejected) |

## Max TTL Boundary

| Field | Value |
|-------|-------|
| TTL_AT_MAX_RESULT | VALID |
| TTL_ABOVE_MAX_RESULT | REJECT / TTL_ABOVE_MAX |

## Future-Issued Rejection

| Field | Value |
|-------|-------|
| FUTURE_ISSUED_ENABLEMENT_RESULT | REJECT / ENABLEMENT_NOT_YET_VALID |
| FUTURE_ISSUED_ENABLEMENT_REGISTRY_MUTATED | NO |

## Registry Mutation Proofs

| Field | Value |
|-------|-------|
| POLICY_REJECTION_REGISTRY_MUTATED | NO |
| CONTROLLER_PRE_REGISTRATION_FAILURE_REGISTRY_MUTATED | NO |
| ENABLEMENT_ID_COLLISION_REGISTRY_MUTATED | NO |
| CROSS_RECEIVER_REPLAY_REGISTRY_MUTATED | NO |
| TTL_REJECTION_REGISTRY_MUTATED | NO |
| EXPIRATION_REJECTION_REGISTRY_MUTATED | NO |
| FUTURE_ISSUED_REJECTION_REGISTRY_MUTATED | NO |
| BINDING_LIMIT_REJECTION_REGISTRY_MUTATED | NO |
| IDENTICAL_DUPLICATE_REGISTRY_MUTATED | NO |
| REGISTRY_MUTATION_OCCURS_ONLY_FOR_GENUINELY_NEW_ALLOWED_BINDING | YES |

## EA-4E.21 Contract ID After Final Semantics

```
77a7022e60a8c771b87041a28b7b4e22eaafe2e32b6d12325304373597143baf
```

## Temporal Semantics in Contract Material

- RUNTIME_TIMESTAMP_VALUES_IN_CONTRACT_MATERIAL: NO
- TEMPORAL_SEMANTICS_IN_CONTRACT_MATERIAL: YES
  - expiration_required=true
  - expiration_boundary="now_gte_expires_at_is_expired"
  - future_issued_behavior="reject"
  - max_ttl_seconds=3600

## Contract Determinism Proof

| Field | Value |
|-------|-------|
| CONTRACT_MAPPING_ORDER_INDEPENDENT | YES |
| IDENTICAL_CONTRACT_INPUTS_IDENTICAL_HASH | YES |
| ANY_TEMPORAL_POLICY_CHANGE_INVALIDATES_CONTRACT | YES |

## Upstream Contracts Unchanged

| Field | Value |
|-------|-------|
| EA4E17_CODE_CHANGED | NO |
| EA4E17_CONTRACT_CHANGED | NO |
| EA4E18_CODE_CHANGED | NO |
| EA4E18_CONTRACT_CHANGED | NO |
| EA4E14_EXECUTION_BOUNDARY_CHANGED | NO |
| EA4E17_ISSUANCE_CONTRACT_ID | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E18_INTEGRATION_CONTRACT_ID | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |

## Dedicated Test Results

- EA4E21_TEST_FILE: `tests/hermes_core/test_production_executor_binding.py`
- EA4E21_TESTS: 45 passed / 0 failed

## Non-Live Regression

| Test | Result |
|------|--------|
| EA4E20_NONLIVE_REGRESSION | PASS |
| EA4E19_NONLIVE_REGRESSION | PASS |
| EA4E18_REGRESSION | PASS |
| EA4E17A_REGRESSION | PASS |
| EA4E17_REGRESSION | PASS |
| EA4E16_REGRESSION | PASS |
| EA4E15_REGRESSION | PASS |
| EA4E14_REGRESSION | PASS |
| EA4E13_REGRESSION | PASS |
| EA4E12_REGRESSION | PASS |
| EA4E11_REGRESSION | PASS |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |
| RECEIVER_ADAPTER_REGRESSION | PASS |
| OPENCODE_ADAPTER_REGRESSION | PASS |
| KILO_ADAPTER_REGRESSION | PASS |

Total: 267 tests passed.

## Live Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_EXECUTOR_CALLS | 0 |
| REAL_RECEIVER_ADAPTER_CALLS | 0 |

## Real Executor Safety

| Field | Value |
|-------|-------|
| REAL_KILO_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_OPENCODE_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_EXECUTOR_CALLED | NO |
| REAL_ADAPTER_CALLED | NO |
| PROCESS_START_COUNT | 0 |
| MODEL_INVOCATION_COUNT | 0 |

## Repository State

| Field | Value |
|-------|-------|
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

# EA-4E.21C TEMPORAL INTEGRITY / EFFECTIVE LIFETIME QUALIFICATION

## Previous Temporal Gap

The policy previously used raw lexical ISO-string comparison for temporal ordering, which is insufficient for production use. It did not:
- Parse timestamps into timezone-aware datetime objects
- Validate timezone awareness (naive timestamps were accepted)
- Compute effective lifetime from timestamps
- Enforce consistency between declared TTL and actual interval
- Handle malformed timestamps deterministically

## Timestamp Parsing Semantics

| Field | Value |
|-------|-------|
| ISSUED_AT_PARSED_AS_DATETIME | YES |
| EXPIRES_AT_PARSED_AS_DATETIME | YES |
| TEMPORAL_VALUES_TIMEZONE_AWARE | YES |
| RAW_STRING_TEMPORAL_COMPARISON_USED | NO |
| TEMPORAL_NORMALIZATION | UTC |
| TEMPORAL_NORMALIZED_TO_UTC | UTC |

## Timezone Requirements

- Naive timestamps (without timezone) are rejected
- UTC `Z` suffix is accepted
- Explicit offsets (e.g., `+01:00`, `-05:00`) are accepted
- All timestamps are normalized to UTC for comparison

## Malformed Timestamp Behavior

| Field | Value |
|-------|-------|
| MALFORMED_ISSUED_AT_RESULT | REJECT / MALFORMED_ISSUED_AT |
| MALFORMED_EXPIRES_AT_RESULT | REJECT / MALFORMED_EXPIRES_AT |
| MALFORMED_TIMESTAMP_FAILS_CLOSED | YES |
| MALFORMED_TIMESTAMP_REGISTRY_MUTATED | NO |

## Naive Timestamp Behavior

| Field | Value |
|-------|-------|
| NAIVE_ISSUED_AT_RESULT | REJECT / MALFORMED_ISSUED_AT |
| NAIVE_EXPIRES_AT_RESULT | REJECT / MALFORMED_EXPIRES_AT |
| NAIVE_TIMESTAMP_REGISTRY_MUTATED | NO |

## Temporal-Order Validation

| Field | Value |
|-------|-------|
| ZERO_EFFECTIVE_LIFETIME_RESULT | REJECT / INVALID_TEMPORAL_ORDER |
| NEGATIVE_EFFECTIVE_LIFETIME_RESULT | REJECT / INVALID_TEMPORAL_ORDER |
| EXPIRES_AT_MUST_BE_AFTER_ISSUED_AT | YES |
| TEMPORAL_ORDER_REJECTION_REGISTRY_MUTATED | NO |

## Effective Lifetime Formula

```
effective_lifetime_seconds = (expires_at - issued_at).total_seconds()
```

Derived from parsed, timezone-aware timestamps — not from the declared `max_binding_ttl_seconds` field.

## Maximum Effective Lifetime

| Field | Value |
|-------|-------|
| EFFECTIVE_LIFETIME_COMPUTED_FROM_TIMESTAMPS | YES |
| EFFECTIVE_LIFETIME_USES_DECLARED_TTL_ONLY | NO |
| EFFECTIVE_LIFETIME_3600_SECONDS_COMPUTED | 3600 |
| EFFECTIVE_LIFETIME_3600_SECONDS_RESULT | VALID |
| EFFECTIVE_TTL_AT_MAX_RESULT | VALID |
| EFFECTIVE_TTL_ABOVE_MAX_RESULT | REJECT / EFFECTIVE_TTL_ABOVE_MAX |
| EFFECTIVE_TTL_ABOVE_MAX_REJECTED | YES |
| EFFECTIVE_TTL_ABOVE_MAX_REGISTRY_MUTATED | NO |

## Declared/Effective TTL Consistency

| Field | Value |
|-------|-------|
| DECLARED_TTL_FIELD_SEMANTICS | exact_equality |
| DECLARED_EFFECTIVE_TTL_EQUALITY_REQUIRED | YES |
| DECLARED_TTL_MISMATCH_RESULT | REJECT / TTL_MISMATCH |
| DECLARED_TTL_3600_ACTUAL_7200_RESULT | REJECT |
| DECLARED_TTL_CANNOT_OVERRIDE_EFFECTIVE_LIFETIME | YES |
| DECLARED_TTL_MISMATCH_REGISTRY_MUTATED | NO |

## Offset-Aware Chronological Comparison

| Field | Value |
|-------|-------|
| OFFSET_AWARE_EFFECTIVE_LIFETIME_COMPUTED | 3600 |
| OFFSET_AWARE_TIMESTAMP_RESULT | VALID |
| EQUIVALENT_OFFSET_INSTANTS_COMPARE_EQUAL | YES |
| RAW_LEXICAL_ORDER_USED | NO |

## Expiration Behavior

| Field | Value |
|-------|-------|
| EXPIRATION_USES_INJECTED_CLOCK | YES |
| EXPIRATION_USES_SYSTEM_CLOCK | NO |
| EXACT_EXPIRATION_BOUNDARY_BEHAVIOR | EXPIRED |
| FUTURE_ISSUED_ENABLEMENT_RESULT | REJECT / ENABLEMENT_NOT_YET_VALID |
| VALID_TEMPORAL_ENABLEMENT_RESULT | PASS |

## Replay Semantics Preserved

| Field | Value |
|-------|-------|
| REPLAY_COLLISION_CHECK_PRECEDES_BINDING_LIMIT | YES |
| ACTIVE_BINDING_COLLISION_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| ACTIVE_KILO_TO_OPENCODE_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| ACTIVE_OPENCODE_TO_KILO_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| IDENTICAL_DUPLICATE_BEHAVIOR | IDEMPOTENT_EXISTING_BINDING |
| IDENTICAL_DUPLICATE_NEW_BINDING_CREATED | NO |
| GENUINELY_NEW_SECOND_BINDING_RESULT | REJECT / BINDING_LIMIT_EXCEEDED |

## Registry Mutation Proofs for Temporal Rejections

| Field | Value |
|-------|-------|
| MALFORMED_TIMESTAMP_REGISTRY_MUTATED | NO |
| NAIVE_TIMESTAMP_REGISTRY_MUTATED | NO |
| TEMPORAL_ORDER_REJECTION_REGISTRY_MUTATED | NO |
| EFFECTIVE_TTL_ABOVE_MAX_REGISTRY_MUTATED | NO |
| DECLARED_TTL_MISMATCH_REGISTRY_MUTATED | NO |
| EXPIRED_ENABLEMENT_REGISTRY_MUTATED | NO |
| FUTURE_ISSUED_REJECTION_REGISTRY_MUTATED | NO |
| REGISTRY_MUTATION_OCCURS_ONLY_FOR_GENUINELY_NEW_ALLOWED_BINDING | YES |

## Final EA-4E.21 Contract ID

```
216d37f654fa09b6a959ea93921298dfad3f5377cf768a5d4cdf37edc7ecc73d
```

## Temporal Integrity Semantics in Contract Material

- RUNTIME_TIMESTAMP_VALUES_IN_CONTRACT_MATERIAL: NO
- TEMPORAL_INTEGRITY_SEMANTICS_IN_CONTRACT_MATERIAL: YES
  - timezone_required=true
  - timestamps_parsed_chronologically=true
  - raw_lexical_timestamp_comparison=false
  - expires_at_must_be_after_issued_at=true
  - effective_lifetime_derived_from_timestamps=true
  - max_effective_lifetime_seconds=3600
  - exact_expiration_boundary="expired"
  - future_issued_behavior="reject"
  - declared_ttl_consistency="exact_equality"
  - malformed_timestamp_behavior="reject"

## Contract Determinism Proof

| Field | Value |
|-------|-------|
| CONTRACT_MAPPING_ORDER_INDEPENDENT | YES |
| IDENTICAL_CONTRACT_INPUTS_IDENTICAL_HASH | YES |
| ANY_TEMPORAL_POLICY_CHANGE_INVALIDATES_CONTRACT | YES |

## Upstream Contracts Unchanged

| Field | Value |
|-------|-------|
| EA4E17_CODE_CHANGED | NO |
| EA4E17_CONTRACT_CHANGED | NO |
| EA4E18_CODE_CHANGED | NO |
| EA4E18_CONTRACT_CHANGED | NO |
| EA4E14_EXECUTION_BOUNDARY_CHANGED | NO |
| EA4E17_ISSUANCE_CONTRACT_ID | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E18_INTEGRATION_CONTRACT_ID | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |

## Dedicated Test Results

- EA4E21_TEST_FILE: `tests/hermes_core/test_production_executor_binding.py`
- EA4E21_TESTS: 65 passed / 0 failed

## Non-Live Regression

| Test | Result |
|------|--------|
| EA4E20_NONLIVE_REGRESSION | PASS |
| EA4E19_NONLIVE_REGRESSION | PASS |
| EA4E18_REGRESSION | PASS |
| EA4E17A_REGRESSION | PASS |
| EA4E17_REGRESSION | PASS |
| EA4E16_REGRESSION | PASS |
| EA4E15_REGRESSION | PASS |
| EA4E14_REGRESSION | PASS |
| EA4E13_REGRESSION | PASS |
| EA4E12_REGRESSION | PASS |
| EA4E11_REGRESSION | PASS |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |
| RECEIVER_ADAPTER_REGRESSION | PASS |
| OPENCODE_ADAPTER_REGRESSION | PASS |
| KILO_ADAPTER_REGRESSION | PASS |

Total: 287 tests passed.

## Live Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_EXECUTOR_CALLS | 0 |
| REAL_RECEIVER_ADAPTER_CALLS | 0 |

## Real Executor Safety

| Field | Value |
|-------|-------|
| REAL_KILO_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_OPENCODE_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_EXECUTOR_CALLED | NO |
| REAL_ADAPTER_CALLED | NO |
| PROCESS_START_COUNT | 0 |
| MODEL_INVOCATION_COUNT | 0 |

## Repository State

| Field | Value |
|-------|-------|
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

# EA-4E.21D TEMPORAL PRECISION / TTL SEMANTIC FINALIZATION

## Previous Int-Truncation Defect

The policy previously computed effective lifetime as:
```python
effective_lifetime_seconds = int((expires_dt - issued_dt).total_seconds())
```

This truncates fractional seconds. Example: 3600.5 seconds → 3600, incorrectly satisfying a 3600-second policy ceiling.

## Full-Precision Duration Semantics

| Field | Value |
|-------|-------|
| AUTHORIZATION_EFFECTIVE_LIFETIME_USES_FULL_PRECISION | YES |
| AUTHORIZATION_EFFECTIVE_LIFETIME_INT_CAST_USED | NO |
| AUTHORIZATION_EFFECTIVE_LIFETIME_ROUNDING_USED | NO |
| AUTHORIZATION_EFFECTIVE_LIFETIME_FLOORING_USED | NO |
| SUBSECOND_PRECISION_PRESERVED | YES |

Effective lifetime is computed using integer microseconds:
```python
effective_microseconds = (
    effective_lifetime.days * 86400000000
    + effective_lifetime.seconds * 1000000
    + effective_lifetime.microseconds
)
```

Policy maximum comparison uses integer microseconds:
```python
policy_max_microseconds = self._max_ttl * 1000000
if effective_microseconds > policy_max_microseconds:
    reject
```

## Sub-Second Boundary Proofs

| Field | Value |
|-------|-------|
| EFFECTIVE_LIFETIME_EXACT_3600_RESULT | VALID |
| EFFECTIVE_LIFETIME_3600_PLUS_1_MICROSECOND_RESULT | REJECT / EFFECTIVE_TTL_ABOVE_MAX |
| EFFECTIVE_LIFETIME_3600_PLUS_1_MICROSECOND_REJECTED | YES |
| EFFECTIVE_LIFETIME_3599_999999_RESULT | VALID |
| SUBSECOND_EFFECTIVE_LIFETIME_COMPUTED | 0.5 |
| SUBSECOND_EFFECTIVE_LIFETIME_RESULT | VALID |
| ONE_MICROSECOND_INTERVAL_TEMPORAL_RESULT | VALID |

## Final TTL Field Semantic Name

| Field | Value |
|-------|-------|
| POLICY_MAX_TTL_FIELD_OR_CONSTANT_DISTINCT | YES |
| ARTIFACT_REQUESTED_TTL_FIELD_DISTINCT | YES |
| TTL_FIELD_SEMANTIC_AMBIGUITY_REMOVED | YES |
| OLD_FIELD_NAME | max_binding_ttl_seconds |
| NEW_FIELD_NAME | requested_ttl_seconds |
| OLD_NAME_RETAINED | NO |
| CANONICAL_SEMANTIC_NAME | requested_ttl_seconds |

The artifact field `requested_ttl_seconds` represents the TTL requested by this enablement, distinct from the policy maximum `MAX_BINDING_TTL_SECONDS=3600`.

## Requested TTL Versus Policy Maximum

| Field | Value |
|-------|-------|
| REQUESTED_TTL_SUPPORTS_SUBSECOND_PRECISION | YES |
| TIMESTAMP_SUBSECOND_VALUES_ALLOWED | YES |
| REQUESTED_EFFECTIVE_TTL_COMPARISON_LOSSLESS | YES |
| BINARY_FLOAT_EXACT_EQUALITY_USED_FOR_SECURITY_DECISION | NO |

## Requested/Effective Consistency Semantics

| Field | Value |
|-------|-------|
| REQUESTED_TTL_3600_EFFECTIVE_3600_000001_RESULT | REJECT / EFFECTIVE_TTL_ABOVE_MAX |
| TRUNCATION_CANNOT_SATISFY_TTL_EQUALITY | YES |
| REQUESTED_TTL_SUBSECOND_EXACT_MATCH_RESULT | PASS |
| REQUESTED_TTL_HALF_SECOND_MATCH_RESULT | PASS |
| REQUESTED_TTL_SUBSECOND_MISMATCH_RESULT | REJECT / TTL_MISMATCH |
| REQUESTED_AND_EFFECTIVE_MATCH_BUT_ABOVE_POLICY_MAX_RESULT | REJECT / EFFECTIVE_TTL_ABOVE_MAX |
| REQUESTED_TTL_VALIDATION_DISTINCT_FROM_POLICY_MAXIMUM | YES |

## Expiration Behavior

| Field | Value |
|-------|-------|
| EXACT_NOW_EXPIRATION_RESULT | EXPIRED |
| ONE_MICROSECOND_AFTER_NOW_EXPIRATION_RESULT | NOT_EXPIRED |

## Offset-Aware Fractional Proof

| Field | Value |
|-------|-------|
| OFFSET_AWARE_FRACTIONAL_EFFECTIVE_LIFETIME | 3600.000001 |
| OFFSET_AWARE_FRACTIONAL_ABOVE_MAX_RESULT | REJECT / EFFECTIVE_TTL_ABOVE_MAX |

## Malformed/Naive Semantics Preserved

| Field | Value |
|-------|-------|
| MALFORMED_TIMESTAMP_FAILS_CLOSED | YES |
| NAIVE_TIMESTAMP_REJECTED | YES |
| TEMPORAL_VALUES_TIMEZONE_AWARE | YES |
| RAW_STRING_TEMPORAL_COMPARISON_USED | NO |

## Replay Semantics Preserved

| Field | Value |
|-------|-------|
| REPLAY_COLLISION_CHECK_PRECEDES_BINDING_LIMIT | YES |
| ACTIVE_BINDING_COLLISION_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| ACTIVE_KILO_TO_OPENCODE_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| ACTIVE_OPENCODE_TO_KILO_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| IDENTICAL_DUPLICATE_BEHAVIOR | IDEMPOTENT_EXISTING_BINDING |
| IDENTICAL_DUPLICATE_NEW_BINDING_CREATED | NO |
| GENUINELY_NEW_SECOND_BINDING_RESULT | REJECT / BINDING_LIMIT_EXCEEDED |

## TTL Canonicalization Rule

| Field | Value |
|-------|-------|
| TTL_CANONICALIZATION_RULE | normalized_decimal_string |
| SEMANTICALLY_EQUAL_TTL_VALUES_CANONICALIZE_IDENTICALLY | YES |
| TTL_FORMATTING_DIFFERENCE_CAUSES_FALSE_COLLISION | NO |

Examples:
- `Decimal("3600")`, `Decimal("3600.0")`, `Decimal("3600.000000")` → `"3600"`
- `Decimal("0.5")`, `Decimal("0.500000")` → `"0.5"`

## Registry Mutation Proofs for Precision Rejections

| Field | Value |
|-------|-------|
| FRACTIONAL_ABOVE_MAX_REGISTRY_MUTATED | NO |
| REQUESTED_TTL_MISMATCH_REGISTRY_MUTATED | NO |
| SUBSECOND_TTL_MISMATCH_REGISTRY_MUTATED | NO |
| OFFSET_AWARE_FRACTIONAL_REJECTION_REGISTRY_MUTATED | NO |
| REGISTRY_MUTATION_OCCURS_ONLY_FOR_GENUINELY_NEW_ALLOWED_BINDING | YES |

## Final EA-4E.21 Contract ID

```
5e3b76d0132aa23e14553ace7f6a0f047709bb20452a09866e340c09294e6100
```

## Temporal Precision Semantics in Contract Material

- RUNTIME_TIMESTAMP_VALUES_IN_CONTRACT_MATERIAL: NO
- TEMPORAL_PRECISION_SEMANTICS_IN_CONTRACT_MATERIAL: YES
- TTL_FIELD_SEMANTICS_IN_CONTRACT_MATERIAL: YES
  - full_precision_temporal_comparison=true
  - effective_lifetime_int_truncation=false
  - effective_lifetime_rounding=false
  - subsecond_precision_preserved=true
  - policy_max_ttl_seconds=3600
  - artifact_requested_ttl_field="requested_ttl_seconds"
  - requested_ttl_consistency="exact_equality_microseconds"
  - requested_ttl_canonicalization="normalized_decimal_string"
  - requested_ttl_subsecond_support=true
  - binary_float_exact_equality=false
  - comparison_method="integer_microseconds"

## Contract Determinism Proof

| Field | Value |
|-------|-------|
| CONTRACT_MAPPING_ORDER_INDEPENDENT | YES |
| IDENTICAL_CONTRACT_INPUTS_IDENTICAL_HASH | YES |
| ANY_TEMPORAL_PRECISION_POLICY_CHANGE_INVALIDATES_CONTRACT | YES |
| ANY_TTL_SEMANTIC_CHANGE_INVALIDATES_CONTRACT | YES |

## Upstream Contracts Unchanged

| Field | Value |
|-------|-------|
| EA4E17_CODE_CHANGED | NO |
| EA4E17_CONTRACT_CHANGED | NO |
| EA4E18_CODE_CHANGED | NO |
| EA4E18_CONTRACT_CHANGED | NO |
| EA4E14_EXECUTION_BOUNDARY_CHANGED | NO |
| EA4E17_ISSUANCE_CONTRACT_ID | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E18_INTEGRATION_CONTRACT_ID | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |

## Dedicated Test Results

- EA4E21_TEST_FILE: `tests/hermes_core/test_production_executor_binding.py`
- EA4E21_TESTS: 83 passed / 0 failed

## Non-Live Regression

| Test | Result |
|------|--------|
| EA4E20_NONLIVE_REGRESSION | PASS |
| EA4E19_NONLIVE_REGRESSION | PASS |
| EA4E18_REGRESSION | PASS |
| EA4E17A_REGRESSION | PASS |
| EA4E17_REGRESSION | PASS |
| EA4E16_REGRESSION | PASS |
| EA4E15_REGRESSION | PASS |
| EA4E14_REGRESSION | PASS |
| EA4E13_REGRESSION | PASS |
| EA4E12_REGRESSION | PASS |
| EA4E11_REGRESSION | PASS |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |
| RECEIVER_ADAPTER_REGRESSION | PASS |
| OPENCODE_ADAPTER_REGRESSION | PASS |
| KILO_ADAPTER_REGRESSION | PASS |

Total: 305 tests passed.

## Live Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_EXECUTOR_CALLS | 0 |
| REAL_RECEIVER_ADAPTER_CALLS | 0 |

## Real Executor Safety

| Field | Value |
|-------|-------|
| REAL_KILO_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_OPENCODE_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_EXECUTOR_CALLED | NO |
| REAL_ADAPTER_CALLED | NO |
| PROCESS_START_COUNT | 0 |
| MODEL_INVOCATION_COUNT | 0 |

## Repository State

| Field | Value |
|-------|-------|
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

# EA-4E.21E RUNTIME BINDING EXPIRATION CONSISTENCY

## Previous Controller Expiry-Reset Defect

The controller previously computed binding handle expiry as:
```python
expires = self._clock.now_plus_seconds(int(enablement.requested_ttl_seconds))
```

This introduced two defects:
1. Fractional requested TTL values were truncated via `int()`
2. Binding lifetime was reset relative to binding time instead of preserving the already-validated enablement expiration

## Authoritative Expiry Source

| Field | Value |
|-------|-------|
| BINDING_HANDLE_EXPIRY_SOURCE | VALIDATED_ENABLEMENT_EXPIRES_AT |
| BINDING_HANDLE_EXPIRY_RECOMPUTED_FROM_BIND_TIME | NO |
| BINDING_HANDLE_EXPIRY_DERIVED_FROM_INT_TTL | NO |
| BINDING_HANDLE_EXPIRY_DERIVED_FROM_FLOAT_TTL | NO |
| BINDING_HANDLE_EXPIRY_TRUNCATED | NO |
| BINDING_HANDLE_EXPIRY_ROUNDED | NO |
| BINDING_HANDLE_EXPIRY_FLOORED | NO |
| BINDING_HANDLE_EXPIRY_EXTENDED | NO |
| BINDING_HANDLE_EXPIRY_CHRONOLOGICALLY_EQUAL_TO_ENABLEMENT_EXPIRY | YES |

## Partially Consumed Enablement Proof

| Field | Value |
|-------|-------|
| PARTIALLY_CONSUMED_ENABLEMENT_BIND_RESULT | ALLOW |
| PARTIALLY_CONSUMED_ENABLEMENT_ORIGINAL_TTL_SECONDS | 3600 |
| PARTIALLY_CONSUMED_ENABLEMENT_REMAINING_SECONDS_AT_BIND | 1800 |
| PARTIALLY_CONSUMED_BINDING_HANDLE_EXPIRES_AT | 2026-01-01T01:00:00Z |
| PARTIALLY_CONSUMED_BINDING_HANDLE_TTL_RESET | NO |
| PARTIALLY_CONSUMED_BINDING_LIFETIME_EXTENDED | NO |

## Sub-Second Expiration Preservation

| Field | Value |
|-------|-------|
| SUBSECOND_ENABLEMENT_BIND_RESULT | ALLOW |
| SUBSECOND_BINDING_HANDLE_EXPIRY_PRESERVED | YES |
| SUBSECOND_BINDING_HANDLE_EXPIRES_AT | 2026-01-01T00:00:00.500000Z |
| SUBSECOND_BINDING_HANDLE_EXPIRY_TRUNCATED | NO |

## Microsecond Expiration Preservation

| Field | Value |
|-------|-------|
| MICROSECOND_ENABLEMENT_BIND_RESULT | ALLOW |
| MICROSECOND_BINDING_HANDLE_EXPIRY_PRESERVED | YES |
| MICROSECOND_BINDING_HANDLE_EXPIRY_TRUNCATED | NO |
| MICROSECOND_BINDING_HANDLE_EXPIRY_RESET | NO |

## Controller TTL Truncation Audit

| Field | Value |
|-------|-------|
| CONTROLLER_REQUESTED_TTL_INT_CAST_USED | NO |
| CONTROLLER_REQUESTED_TTL_FLOAT_CAST_USED | NO |
| CONTROLLER_EXPIRY_ROUNDING_USED | NO |
| CONTROLLER_EXPIRY_FLOORING_USED | NO |
| CONTROLLER_EXPIRY_CEILING_USED | NO |
| BINDING_CONTROLLER_CALLS_NOW_PLUS_SECONDS_FOR_HANDLE_EXPIRY | NO |

## Policy Remains Authoritative

| Field | Value |
|-------|-------|
| CONTROLLER_REVALIDATES_TEMPORAL_POLICY_WITH_DIFFERENT_SEMANTICS | NO |
| CONTROLLER_EXTENDS_VALIDATED_AUTHORIZATION | NO |
| CONTROLLER_NARROWS_VALIDATED_AUTHORIZATION | NO |

## Pre-Registration Expiry Check

| Field | Value |
|-------|-------|
| CONTROLLER_PRE_REGISTRATION_EXPIRY_CHECK | YES |
| CONTROLLER_PRE_REGISTRATION_EXPIRY_CHECK_USES_ENABLEMENT_EXPIRES_AT | YES |
| CONTROLLER_PRE_REGISTRATION_EXPIRY_CHECK_RECOMPUTES_EXPIRY | NO |
| CONTROLLER_PRE_REGISTRATION_EXPIRED_RESULT | REJECT / ENABLEMENT_EXPIRED |
| CONTROLLER_PRE_REGISTRATION_EXPIRED_REGISTRY_MUTATED | NO |

## Expired-Between-Policy-and-Bind

| Field | Value |
|-------|-------|
| EXPIRED_BETWEEN_POLICY_AND_BIND_RESULT | ALLOW (clock before expiry) |
| EXPIRED_BETWEEN_POLICY_AND_BIND_REGISTRY_MUTATED | NO (when expired) |
| EXPIRED_BETWEEN_POLICY_AND_BIND_EXECUTOR_REGISTERED | NO (when expired) |

## Identical Duplicate Handle Semantics

| Field | Value |
|-------|-------|
| IDENTICAL_DUPLICATE_RETURNS_EXISTING_BINDING_IDENTITY | YES |
| IDENTICAL_DUPLICATE_BINDING_EXPIRY_CHANGED | NO |
| IDENTICAL_DUPLICATE_BINDING_EXPIRY_EXTENDED | NO |
| IDENTICAL_DUPLICATE_NEW_HANDLE_CREATED | NO |
| IDENTICAL_DUPLICATE_REGISTRY_MUTATED | NO |

## Teardown Remains Exact

| Field | Value |
|-------|-------|
| BINDING_HANDLE_RETURNED | YES |
| TEARDOWN_SUPPORTED | YES |
| TEARDOWN_REMOVES_ONLY_AUTHORIZED_BINDING | YES |
| TEARDOWN_LEAVES_UNRELATED_BINDINGS_UNCHANGED | YES |
| DOUBLE_TEARDOWN_BEHAVIOR | Returns False on second call |
| TEST_REGISTRY_BINDINGS_REMAINING | 0 |

## Replay/Collision Must Remain Intact

| Field | Value |
|-------|-------|
| REPLAY_COLLISION_CHECK_PRECEDES_BINDING_LIMIT | YES |
| ACTIVE_BINDING_COLLISION_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| ACTIVE_KILO_TO_OPENCODE_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| ACTIVE_OPENCODE_TO_KILO_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| IDENTICAL_DUPLICATE_BEHAVIOR | IDEMPOTENT_EXISTING_BINDING |
| IDENTICAL_DUPLICATE_NEW_BINDING_CREATED | NO |
| GENUINELY_NEW_SECOND_BINDING_RESULT | REJECT / BINDING_LIMIT_EXCEEDED |

## Temporal Precision Must Remain Intact

| Field | Value |
|-------|-------|
| AUTHORIZATION_EFFECTIVE_LIFETIME_USES_FULL_PRECISION | YES |
| AUTHORIZATION_EFFECTIVE_LIFETIME_INT_CAST_USED | NO |
| SUBSECOND_PRECISION_PRESERVED | YES |
| REQUESTED_EFFECTIVE_TTL_COMPARISON_LOSSLESS | YES |
| BINARY_FLOAT_EXACT_EQUALITY_USED_FOR_SECURITY_DECISION | NO |
| EFFECTIVE_LIFETIME_3600_PLUS_1_MICROSECOND_REJECTED | YES |
| TTL_CANONICALIZATION_RULE | normalized_decimal_string |
| SEMANTICALLY_EQUAL_TTL_VALUES_CANONICALIZE_IDENTICALLY | YES |

## Runtime Handle Expiry Semantics in Contract Material

- RUNTIME_TIMESTAMP_VALUES_IN_CONTRACT_MATERIAL: NO
- RUNTIME_HANDLE_EXPIRY_SEMANTICS_IN_CONTRACT_MATERIAL: YES
  - binding_handle_expiry_source="validated_enablement_expires_at"
  - binding_handle_expiry_recomputed_from_bind_time=false
  - binding_handle_expiry_ttl_truncation=false
  - binding_handle_expiry_reset=false
  - binding_handle_expiry_extension=false
  - duplicate_binding_expiry_refresh=false
  - pre_registration_expiry_check=true

## Final EA-4E.21 Contract ID

```
bce222f0f58e2f7067cef07e84dec9bf17fb3a6adf416d21f704d251c6fe75f2
```

## Contract Determinism Proof

| Field | Value |
|-------|-------|
| CONTRACT_MAPPING_ORDER_INDEPENDENT | YES |
| IDENTICAL_CONTRACT_INPUTS_IDENTICAL_HASH | YES |
| ANY_RUNTIME_EXPIRY_SEMANTIC_CHANGE_INVALIDATES_CONTRACT | YES |

## Upstream Contracts Unchanged

| Field | Value |
|-------|-------|
| EA4E17_CODE_CHANGED | NO |
| EA4E17_CONTRACT_CHANGED | NO |
| EA4E18_CODE_CHANGED | NO |
| EA4E18_CONTRACT_CHANGED | NO |
| EA4E14_EXECUTION_BOUNDARY_CHANGED | NO |
| EA4E17_ISSUANCE_CONTRACT_ID | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E18_INTEGRATION_CONTRACT_ID | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |

## Registry Mutation Proofs

| Field | Value |
|-------|-------|
| PARTIALLY_CONSUMED_BIND_REGISTRY_MUTATED_ONLY_ON_ALLOW | YES |
| PRE_REGISTRATION_EXPIRED_REGISTRY_MUTATED | NO |
| IDENTICAL_DUPLICATE_REGISTRY_MUTATED | NO |
| TEMPORAL_REJECTION_REGISTRY_MUTATED | NO |
| REGISTRY_MUTATION_OCCURS_ONLY_FOR_GENUINELY_NEW_CURRENTLY_VALID_ALLOWED_BINDING | YES |

## Dedicated Test Results

- EA4E21_TEST_FILE: `tests/hermes_core/test_production_executor_binding.py`
- EA4E21_TESTS: 95 passed / 0 failed

## Non-Live Regression

| Test | Result |
|------|--------|
| EA4E20_NONLIVE_REGRESSION | PASS |
| EA4E19_NONLIVE_REGRESSION | PASS |
| EA4E18_REGRESSION | PASS |
| EA4E17A_REGRESSION | PASS |
| EA4E17_REGRESSION | PASS |
| EA4E16_REGRESSION | PASS |
| EA4E15_REGRESSION | PASS |
| EA4E14_REGRESSION | PASS |
| EA4E13_REGRESSION | PASS |
| EA4E12_REGRESSION | PASS |
| EA4E11_REGRESSION | PASS |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |
| RECEIVER_ADAPTER_REGRESSION | PASS |
| OPENCODE_ADAPTER_REGRESSION | PASS |
| KILO_ADAPTER_REGRESSION | PASS |

Total: 317 tests passed.

## Live Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_EXECUTOR_CALLS | 0 |
| REAL_RECEIVER_ADAPTER_CALLS | 0 |

## Real Executor Safety

| Field | Value |
|-------|-------|
| REAL_KILO_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_OPENCODE_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_EXECUTOR_CALLED | NO |
| REAL_ADAPTER_CALLED | NO |
| PROCESS_START_COUNT | 0 |
| MODEL_INVOCATION_COUNT | 0 |

## Repository State

| Field | Value |
|-------|-------|
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

# EA-4E.21F CONTROLLER REPLAY ENFORCEMENT / IDEMPOTENT DUPLICATE QUALIFICATION

## Previous Same-ID Fast-Path Bypass

The controller previously checked for an existing handle BEFORE policy evaluation:
```python
existing_handle = self.get_bound_handle(enablement.enablement_id)
if existing_handle is not None:
    return existing_handle

result = self._policy.evaluate(...)
```

This allowed same-ID input to bypass policy classification. A caller could reuse an existing enablement_id while changing canonical material (receiver_id, request_nonce, transport_contract_id, model_binding_id, executor_identity, executor_factory, runtime_scope, delegation_class, requested_ttl_seconds, issued_at, expires_at) and the controller would return the existing handle without producing the required ENABLEMENT_ID_COLLISION or CROSS_RECEIVER_BINDING_REPLAY classification.

## Corrected Controller Flow

| Field | Value |
|-------|-------|
| CONTROLLER_SAME_ID_FAST_PATH_BEFORE_POLICY | NO |
| POLICY_CLASSIFICATION_PRECEDES_EXISTING_HANDLE_RETURN | YES |
| EXISTING_HANDLE_RETURN_REQUIRES_IDENTICAL_DUPLICATE_CLASSIFICATION | YES |
| COLLISION_CAN_RETURN_EXISTING_HANDLE | NO |
| CROSS_RECEIVER_REPLAY_CAN_RETURN_EXISTING_HANDLE | NO |
| GENUINELY_NEW_ALLOW_USES_EXISTING_HANDLE_FAST_PATH | NO |

The corrected flow:
1. Evaluate policy with current binding count and bound enablements
2. If result is IDENTICAL_DUPLICATE, return existing handle
3. For all other rejections, raise BindingPolicyError
4. For ALLOW, proceed through bind path

## Policy Result Semantics

| Field | Value |
|-------|-------|
| IDENTICAL_DUPLICATE_POLICY_DECISION | REJECT |
| IDENTICAL_DUPLICATE_POLICY_REASON | IDENTICAL_DUPLICATE |
| CONTROLLER_SPECIAL_CASES_ONLY_IDENTICAL_DUPLICATE | YES |
| CONTROLLER_SPECIAL_CASES_GENERIC_REJECT_AS_SUCCESS | NO |
| CONTROLLER_SPECIAL_CASES_SAME_ID_AS_SUCCESS | NO |

## Identical Duplicate Proof

| Field | Value |
|-------|-------|
| CONTROLLER_IDENTICAL_DUPLICATE_RESULT | IDEMPOTENT_EXISTING_BINDING |
| CONTROLLER_IDENTICAL_DUPLICATE_RETURNS_SAME_HANDLE_OBJECT | YES |
| CONTROLLER_IDENTICAL_DUPLICATE_RETURNS_SAME_BINDING_IDENTITY | YES |
| CONTROLLER_IDENTICAL_DUPLICATE_NEW_HANDLE_CREATED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_REGISTRY_MUTATED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_EXECUTOR_REGISTERED_AGAIN | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_BINDING_COUNT_INCREMENTED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_EXPIRY_CHANGED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_EXPIRY_EXTENDED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_BOUND_AT_CHANGED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_POLICY_CLASSIFICATION_REACHED | YES |

## Changed Nonce Collision Proof

| Field | Value |
|-------|-------|
| CONTROLLER_CHANGED_NONCE_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| CONTROLLER_CHANGED_NONCE_HANDLE_RETURNED | NO |
| CONTROLLER_CHANGED_NONCE_REGISTRY_MUTATED | NO |
| CONTROLLER_CHANGED_NONCE_EXECUTOR_REGISTERED | NO |
| CONTROLLER_CHANGED_NONCE_POLICY_CLASSIFICATION_REACHED | YES |

## Changed TTL Collision Proof

| Field | Value |
|-------|-------|
| CONTROLLER_CHANGED_TTL_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| CONTROLLER_CHANGED_TTL_HANDLE_RETURNED | NO |
| CONTROLLER_CHANGED_TTL_REGISTRY_MUTATED | NO |

## Changed Expiry Collision Proof

| Field | Value |
|-------|-------|
| CONTROLLER_CHANGED_EXPIRY_RESULT | REJECT / ENABLEMENT_ID_COLLISION |
| CONTROLLER_CHANGED_EXPIRY_HANDLE_RETURNED | NO |
| CONTROLLER_CHANGED_EXPIRY_REGISTRY_MUTATED | NO |

## Cross-Receiver Replay - Kilo to OpenCode

| Field | Value |
|-------|-------|
| CONTROLLER_KILO_TO_OPENCODE_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| CONTROLLER_KILO_TO_OPENCODE_HANDLE_RETURNED | NO |
| CONTROLLER_KILO_TO_OPENCODE_REGISTRY_MUTATED | NO |
| CONTROLLER_KILO_TO_OPENCODE_EXECUTOR_REGISTERED | NO |
| CONTROLLER_KILO_TO_OPENCODE_POLICY_CLASSIFICATION_REACHED | YES |

## Cross-Receiver Replay - OpenCode to Kilo

| Field | Value |
|-------|-------|
| CONTROLLER_OPENCODE_TO_KILO_REPLAY_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| CONTROLLER_OPENCODE_TO_KILO_HANDLE_RETURNED | NO |
| CONTROLLER_OPENCODE_TO_KILO_REGISTRY_MUTATED | NO |
| CONTROLLER_OPENCODE_TO_KILO_EXECUTOR_REGISTERED | NO |
| CONTROLLER_OPENCODE_TO_KILO_POLICY_CLASSIFICATION_REACHED | YES |

## Multi-Field Cross-Receiver Replay

| Field | Value |
|-------|-------|
| CONTROLLER_MULTI_FIELD_CROSS_RECEIVER_RESULT | REJECT / CROSS_RECEIVER_BINDING_REPLAY |
| CONTROLLER_MULTI_FIELD_CROSS_RECEIVER_HANDLE_RETURNED | NO |
| CONTROLLER_MULTI_FIELD_CROSS_RECEIVER_REGISTRY_MUTATED | NO |
| CROSS_RECEIVER_REPLAY_PRECEDENCE_OVER_GENERIC_COLLISION | YES |

## Binding Limit Must Not Mask Replay

| Field | Value |
|-------|-------|
| CONTROLLER_REPLAY_COLLISION_PRECEDES_BINDING_LIMIT | YES |
| CONTROLLER_ACTIVE_COLLISION_MASKED_BY_BINDING_LIMIT | NO |
| CONTROLLER_ACTIVE_CROSS_RECEIVER_REPLAY_MASKED_BY_BINDING_LIMIT | NO |
| CONTROLLER_GENUINELY_NEW_SECOND_BINDING_RESULT | REJECT / BINDING_LIMIT_EXCEEDED |

## Bound Handle Metadata

| Field | Value |
|-------|-------|
| BOUND_ENABLEMENT_METADATA_INCLUDES_RECEIVER_ID | YES |
| BOUND_ENABLEMENT_METADATA_INCLUDES_CANONICAL_HASH | YES |
| BOUND_ENABLEMENT_METADATA_INCLUDES_HANDLE_IDENTITY | YES |
| BOUND_ENABLEMENT_METADATA_PERSISTENT | NO |
| BOUND_ENABLEMENT_METADATA_USED_FOR_POLICY_CLASSIFICATION | YES |

## Canonical Hash

| Field | Value |
|-------|-------|
| POLICY_CANONICAL_HASH_FUNCTION | sha256_payload |
| CONTROLLER_CANONICAL_HASH_FUNCTION | sha256_payload |
| POLICY_AND_CONTROLLER_CANONICAL_HASH_SEMANTICS_IDENTICAL | YES |
| SEMANTICALLY_EQUAL_TTL_VALUES_CANONICALIZE_IDENTICALLY | YES |
| FORMATTING_ONLY_TTL_CHANGE_CAUSES_FALSE_COLLISION | NO |

## Executor Factory / Registration Accounting

| Field | Value |
|-------|-------|
| IDENTICAL_DUPLICATE_EXECUTOR_FACTORY_CALL_INCREMENT | 0 |
| IDENTICAL_DUPLICATE_REGISTRY_REGISTER_CALL_INCREMENT | 0 |
| COLLISION_EXECUTOR_FACTORY_CALL_INCREMENT | 0 |
| COLLISION_REGISTRY_REGISTER_CALL_INCREMENT | 0 |
| CROSS_RECEIVER_REPLAY_EXECUTOR_FACTORY_CALL_INCREMENT | 0 |
| CROSS_RECEIVER_REPLAY_REGISTRY_REGISTER_CALL_INCREMENT | 0 |
| EXECUTOR_FACTORY_RESOLUTION_OCCURS_AFTER_REPLAY_CLASSIFICATION | YES |
| EXECUTOR_INSTANTIATION_OCCURS_AFTER_REPLAY_CLASSIFICATION | YES |

## Teardown

| Field | Value |
|-------|-------|
| BINDING_HANDLE_RETURNED | YES |
| TEARDOWN_SUPPORTED | YES |
| TEARDOWN_REMOVES_ONLY_AUTHORIZED_BINDING | YES |
| TEARDOWN_LEAVES_UNRELATED_BINDINGS_UNCHANGED | YES |
| DOUBLE_TEARDOWN_BEHAVIOR | Returns False on second call |
| TEARDOWN_REMOVES_BOUND_ENABLEMENT_METADATA | YES |
| POST_TEARDOWN_SAME_ENABLEMENT_ID_BEHAVIOR | Can be bound again (no replay history) |
| DANGLING_HANDLE_REFERENCE_AFTER_TEARDOWN | NO |
| TEST_REGISTRY_BINDINGS_REMAINING | 0 |

## Bound State Lifecycle

| Field | Value |
|-------|-------|
| BOUND_ENABLEMENTS_STATE_SEMANTICS | ACTIVE_BINDINGS_ONLY |

Teardown removes the entry from _bound_enablements. After teardown, the same enablement_id can be bound again without replay interference.

## Expiry Semantics Preserved

| Field | Value |
|-------|-------|
| BINDING_HANDLE_EXPIRY_SOURCE | VALIDATED_ENABLEMENT_EXPIRES_AT |
| BINDING_HANDLE_EXPIRY_RECOMPUTED_FROM_BIND_TIME | NO |
| BINDING_HANDLE_EXPIRY_TRUNCATED | NO |
| BINDING_HANDLE_EXPIRY_EXTENDED | NO |
| PARTIALLY_CONSUMED_BINDING_HANDLE_TTL_RESET | NO |
| SUBSECOND_BINDING_HANDLE_EXPIRY_PRESERVED | YES |
| MICROSECOND_BINDING_HANDLE_EXPIRY_PRESERVED | YES |
| CONTROLLER_PRE_REGISTRATION_EXPIRY_CHECK | YES |

## Temporal Precision Preserved

| Field | Value |
|-------|-------|
| AUTHORIZATION_EFFECTIVE_LIFETIME_USES_FULL_PRECISION | YES |
| AUTHORIZATION_EFFECTIVE_LIFETIME_INT_CAST_USED | NO |
| SUBSECOND_PRECISION_PRESERVED | YES |
| REQUESTED_EFFECTIVE_TTL_COMPARISON_LOSSLESS | YES |
| BINARY_FLOAT_EXACT_EQUALITY_USED_FOR_SECURITY_DECISION | NO |
| EFFECTIVE_LIFETIME_3600_PLUS_1_MICROSECOND_REJECTED | YES |

## Controller Replay Enforcement in Contract Material

- RUNTIME_INSTANCE_IDS_IN_CONTRACT_MATERIAL: NO
- RUNTIME_TIMESTAMP_VALUES_IN_CONTRACT_MATERIAL: NO
- CONTROLLER_REPLAY_ENFORCEMENT_SEMANTICS_IN_CONTRACT_MATERIAL: YES
  - same_id_fast_path_before_policy=false
  - policy_classification_precedes_existing_handle_return=true
  - existing_handle_return_requires_identical_duplicate=true
  - collision_returns_handle=false
  - cross_receiver_replay_returns_handle=false
  - executor_resolution_after_replay_classification=true
  - duplicate_registration=false
  - duplicate_expiry_refresh=false
  - bound_enablement_state_semantics="ACTIVE_BINDINGS_ONLY"

## Final EA-4E.21 Contract ID

```
99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7
```

## Contract Determinism Proof

| Field | Value |
|-------|-------|
| CONTRACT_MAPPING_ORDER_INDEPENDENT | YES |
| IDENTICAL_CONTRACT_INPUTS_IDENTICAL_HASH | YES |
| ANY_CONTROLLER_REPLAY_SEMANTIC_CHANGE_INVALIDATES_CONTRACT | YES |

## Upstream Contracts Unchanged

| Field | Value |
|-------|-------|
| EA4E17_CODE_CHANGED | NO |
| EA4E17_CONTRACT_CHANGED | NO |
| EA4E18_CODE_CHANGED | NO |
| EA4E18_CONTRACT_CHANGED | NO |
| EA4E14_EXECUTION_BOUNDARY_CHANGED | NO |
| EA4E17_ISSUANCE_CONTRACT_ID | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E18_INTEGRATION_CONTRACT_ID | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |

## Registry Mutation Proofs

| Field | Value |
|-------|-------|
| CONTROLLER_CHANGED_NONCE_REGISTRY_MUTATED | NO |
| CONTROLLER_CHANGED_TTL_REGISTRY_MUTATED | NO |
| CONTROLLER_CHANGED_EXPIRY_REGISTRY_MUTATED | NO |
| CONTROLLER_KILO_TO_OPENCODE_REGISTRY_MUTATED | NO |
| CONTROLLER_OPENCODE_TO_KILO_REGISTRY_MUTATED | NO |
| CONTROLLER_MULTI_FIELD_CROSS_RECEIVER_REGISTRY_MUTATED | NO |
| CONTROLLER_IDENTICAL_DUPLICATE_REGISTRY_MUTATED | NO |
| REGISTRY_MUTATION_OCCURS_ONLY_FOR_GENUINELY_NEW_CURRENTLY_VALID_ALLOWED_BINDING | YES |

## Dedicated Test Results

- EA4E21_TEST_FILE: `tests/hermes_core/test_production_executor_binding.py`
- EA4E21_TESTS: 110 passed / 0 failed

## Non-Live Regression

| Test | Result |
|------|--------|
| EA4E20_NONLIVE_REGRESSION | PASS |
| EA4E19_NONLIVE_REGRESSION | PASS |
| EA4E18_REGRESSION | PASS |
| EA4E17A_REGRESSION | PASS |
| EA4E17_REGRESSION | PASS |
| EA4E16_REGRESSION | PASS |
| EA4E15_REGRESSION | PASS |
| EA4E14_REGRESSION | PASS |
| EA4E13_REGRESSION | PASS |
| EA4E12_REGRESSION | PASS |
| EA4E11_REGRESSION | PASS |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |
| RECEIVER_ADAPTER_REGRESSION | PASS |
| OPENCODE_ADAPTER_REGRESSION | PASS |
| KILO_ADAPTER_REGRESSION | PASS |

Total: 332 tests passed.

## Live Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| REAL_EXECUTOR_CALLS | 0 |
| REAL_RECEIVER_ADAPTER_CALLS | 0 |

## Real Executor Safety

| Field | Value |
|-------|-------|
| REAL_KILO_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_OPENCODE_EXECUTOR_INSTANTIATED_DURING_TESTS | NO |
| REAL_EXECUTOR_CALLED | NO |
| REAL_ADAPTER_CALLED | NO |
| PROCESS_START_COUNT | 0 |
| MODEL_INVOCATION_COUNT | 0 |

## Repository State

| Field | Value |
|-------|-------|
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## FINAL DISPOSITION

```
EA-4E.21 PRODUCTION REAL-EXECUTOR BINDING POLICY =
QUALIFIED NON-LIVE / RUNTIME-SCOPED / DEFAULT DENY /
CONTROLLER REPLAY ENFORCEMENT COMPLETE / NOT COMMITTED

EA-4E.21F =
QUALIFIED / POLICY CLASSIFICATION PRECEDES HANDLE RETURN /
IDENTICAL DUPLICATE ONLY / ALL TESTS PASS / NOT COMMITTED

EA-4E.21 =
HOLD / COMMIT REQUIRED
```

No live receiver execution is authorized.
