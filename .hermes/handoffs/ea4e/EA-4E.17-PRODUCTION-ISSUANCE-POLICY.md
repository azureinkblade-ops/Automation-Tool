# EA-4E.17 Governed Production Authority / Activation Issuance Policy Non-Live Qualification

## Disposition

`EA-4E.17 GOVERNED PRODUCTION AUTHORITY / ACTIVATION ISSUANCE POLICY = QUALIFIED NON-LIVE / NOT COMMITTED`

---

## 1. Governing State

| Field | Value |
|-------|-------|
| GOVERNING_LOCAL_HEAD | `a2399b624cc2c0fff5c5cfcf2ff8e29197238b5a` |
| GOVERNING_REMOTE_HEAD | `a2399b624cc2c0fff5c5cfcf2ff8e29197238b5a` |
| CURRENT_BRANCH | `feature/ea4f-regional-hand-repair-pilot` |

## 2. Frozen Contracts

| Field | Value |
|-------|-------|
| EA4E6_ROUTER_CONTRACT_ID | `92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f` |
| EA4E7_AUTHORITY_CONTRACT_ID | `c21e17d125b5cb9292a5cb639e3b9b31af8e52b2577d700eb6307881aeeb2048` |
| EA4E11_ACTIVATION_CONTRACT_ID | `0d0b2d0327c5f3c4f32d47563f86fe2158b9b31a530ccbb26568f960c73df9c6` |
| EA4E14_EXECUTION_CONTRACT_ID | `89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6` |
| KILO_TRANSPORT_CONTRACT_ID | `c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500` |
| KILO_MODEL_BINDING_ID | `b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544` |
| OPENCODE_TRANSPORT_CONTRACT_ID | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` |
| OPENCODE_MODEL_BINDING_ID | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |

## 3. Issuance Schema/Contract

| Field | Value |
|-------|-------|
| ISSUANCE_SCHEMA | `hermes.production-issuance.receiver-dispatch/v1` |
| ISSUANCE_CONTRACT_ID | `aff83b6ea62079e7ac656350f75582e46561e571593eead22dfa07feb2717084` |

## 4. Policy Configuration

| Field | Value |
|-------|-------|
| ISSUANCE_POLICY | `ProductionIssuancePolicy` |
| DEFAULT_ISSUANCE_DECISION | DENY |

## 5. Qualified Receiver Set

- `kilo-cli-agent`
- `opencode-cli-agent`

## 6. Allowed Values

| Field | Value |
|-------|-------|
| ALLOWED_OPERATION | `receiver-dispatch` |
| ALLOWED_EXECUTION_SCOPE | `production` |
| ALLOWED_DELEGATION_CLASS | `governed` |

## 7. Attempt-Limit Policy

| Field | Value |
|-------|-------|
| MAX_ISSUABLE_ATTEMPT_LIMIT | 1 |

## 8. Authority Lifetime Policy

| Field | Value |
|-------|-------|
| MAX_AUTHORITY_TTL | 3600 seconds (1 hour) |

## 9. Activation Lifetime Binding

| Field | Value |
|-------|-------|
| ACTIVATION_SCOPE | production |
| ACTIVATION_MODE | ENABLED only for explicitly eligible request |
| GLOBAL_PRODUCTION_ACTIVATION_DEFAULT | DISABLED |

## 10. Kilo Positive Issuance

| Field | Value |
|-------|-------|
| KILO_POSITIVE_POLICY_DECISION | ELIGIBLE |
| KILO_AUTHORITY_ISSUED | YES |
| KILO_AUTHORITY_VALID | YES |
| KILO_ACTIVATION_ISSUED | YES |
| KILO_ACTIVATION_VALID | YES |
| KILO_EXECUTION_OCCURRED | NO |

## 11. OpenCode Positive Issuance

| Field | Value |
|-------|-------|
| OPENCODE_POSITIVE_POLICY_DECISION | ELIGIBLE |
| OPENCODE_AUTHORITY_ISSUED | YES |
| OPENCODE_AUTHORITY_VALID | YES |
| OPENCODE_ACTIVATION_ISSUED | YES |
| OPENCODE_ACTIVATION_VALID | YES |
| OPENCODE_EXECUTION_OCCURRED | NO |

## 12. Fail-Closed Matrix

| Case | Result |
|------|--------|
| Missing receiver | REJECT / MISSING_RECEIVER |
| Unsupported receiver | REJECT / UNSUPPORTED_RECEIVER |
| Route not selected | REJECT / ROUTE_NOT_SELECTED |
| Routing receiver mismatch | REJECT / ROUTING_RECEIVER_MISMATCH |
| Router contract mismatch | REJECT / ROUTER_CONTRACT_MISMATCH |
| Transport mismatch | REJECT / TRANSPORT_CONTRACT_MISMATCH |
| Model binding mismatch | REJECT / MODEL_BINDING_MISMATCH |
| Cross-receiver binding mismatch | REJECT / TRANSPORT_CONTRACT_MISMATCH |
| Delegation class mismatch | REJECT / DELEGATION_CLASS_MISMATCH |
| Operation mismatch | REJECT / OPERATION_MISMATCH |
| Execution scope mismatch | REJECT / EXECUTION_SCOPE_MISMATCH |
| Attempt limit zero | REJECT / ATTEMPT_LIMIT_ZERO |
| Attempt limit above max | REJECT / ATTEMPT_LIMIT_ABOVE_MAX |
| Invalid TTL (zero/negative) | REJECT / INVALID_TTL |
| TTL above maximum | REJECT / TTL_ABOVE_MAX |

## 13. Duplicate/Replay Policy

| Field | Value |
|-------|-------|
| DUPLICATE_REQUEST_POLICY | Same request_id + same canonical → same deterministic result |
| REQUEST_ID_COLLISION_RESULT | REJECT / REQUEST_ID_COLLISION |

## 14. Cross-Receiver Replay

| Field | Value |
|-------|-------|
| KILO_AUTHORITY_REPLAY_AS_OPENCODE | REJECT |
| OPENCODE_AUTHORITY_REPLAY_AS_KILO | REJECT |
| KILO_ACTIVATION_REPLAY_AS_OPENCODE | REJECT |
| OPENCODE_ACTIVATION_REPLAY_AS_KILO | REJECT |

## 15. No Automatic Receiver Selection

| Field | Value |
|-------|-------|
| AUTOMATIC_RECEIVER_SELECTION_ENABLED | NO |
| TASK_TEXT_RECEIVER_SELECTION | NO |
| ENVIRONMENT_RECEIVER_SELECTION | NO |
| DEFAULT_RECEIVER | NONE |

## 16. No Fallback/Failover

| Field | Value |
|-------|-------|
| KILO_TO_OPENCODE_FALLBACK | NO |
| OPENCODE_TO_KILO_FALLBACK | NO |
| FALLBACK_ENABLED | NO |
| FAILOVER_ENABLED | NO |

## 17. No Retry Authority

| Field | Value |
|-------|-------|
| AUTOMATIC_RETRY_ENABLED | NO |

## 18. No Execution Dependency

| Field | Value |
|-------|-------|
| ISSUANCE_POLICY_DEPENDS_ON_REAL_KILO_EXECUTOR | NO |
| ISSUANCE_POLICY_DEPENDS_ON_REAL_OPENCODE_EXECUTOR | NO |
| ISSUANCE_POLICY_DEPENDS_ON_KILO_LIVE_BINDING_HARNESS | NO |
| ISSUANCE_POLICY_DEPENDS_ON_OPENCODE_LIVE_BINDING_HARNESS | NO |

## 19. Production Execution Boundary Separation

| Field | Value |
|-------|-------|
| PRODUCTION_EXECUTION_BOUNDARY_CALLED | NO |
| REAL_EXECUTOR_CALLED | NO |
| REAL_ADAPTER_CALLED | NO |
| PROCESS_STARTED | NO |
| MODEL_INVOKED | NO |

## 20. Determinism

| Field | Value |
|-------|-------|
| POLICY_CLOCK_INJECTABLE | YES |
| SYSTEM_CLOCK_READ_REQUIRED_FOR_POLICY_TESTS | NO |

## 21. Security Invariants

| Field | Value |
|-------|-------|
| ROUTER_CREATES_AUTHORITY | NO |
| ROUTER_CREATES_ACTIVATION | NO |
| ISSUANCE_POLICY_SELECTS_RECEIVER | NO |
| ISSUANCE_POLICY_EXECUTES_RECEIVER | NO |
| ISSUANCE_POLICY_STARTS_PROCESS | NO |
| ISSUANCE_POLICY_CALLS_MODEL | NO |
| AUTHORITY_BUILDER_ACTIVATES_PRODUCTION | NO |
| AUTHORITY_VALIDATOR_ACTIVATES_PRODUCTION | NO |
| ACTIVATION_BUILDER_EXECUTES_RECEIVER | NO |
| ACTIVATION_VALIDATOR_EXECUTES_RECEIVER | NO |
| DEFAULT_ISSUANCE_DECISION | DENY |
| DEFAULT_PRODUCTION_ACTIVATION | DISABLED |
| PERSISTENT_PRODUCTION_EXECUTION_ENABLED | NO |
| ROUTE_SELECTED != AUTHORITY_ISSUED | YES |
| AUTHORITY_ISSUED != ACTIVATION_ISSUED | YES |
| ACTIVATION_ISSUED != RECEIVER_EXECUTED | YES |

## 22. Test Results

| Test | Result |
|------|--------|
| EA4E17_TESTS | 24 passed / 0 failed |
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
| KILO_ADAPTER_REGRESSION | PASS |
| OPENCODE_ADAPTER_REGRESSION | PASS |
| TOTAL | 150 passed / 0 failed |

## 23. Live Execution Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| LIVE_ROUTER_EXECUTIONS | 0 |
| LIVE_DISPATCH_EXECUTIONS | 0 |
| PRODUCTION_ACTIVATED_EXECUTIONS | 0 |
| PRODUCTION_EXECUTION_BOUNDARY_EXECUTIONS | 0 |
| REAL_EXECUTOR_CALLS | 0 |
| REAL_RECEIVER_ADAPTER_CALLS | 0 |

## 24. Non-Live Issuance Accounting

| Field | Value |
|-------|-------|
| NONLIVE_AUTHORITIES_ISSUED | 2 (Kilo + OpenCode positive cases) |
| NONLIVE_ACTIVATIONS_ISSUED | 2 (Kilo + OpenCode positive cases) |

## 25. Repository State

| Field | Value |
|-------|-------|
| HEAD | `a2399b624cc2c0fff5c5cfcf2ff8e29197238b5a` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.17 GOVERNED PRODUCTION AUTHORITY / ACTIVATION ISSUANCE POLICY = QUALIFIED NON-LIVE / NOT COMMITTED`

`EA-4E.17 = HOLD / COMMIT REQUIRED`

No receiver execution is enabled. No real executor is configured by default. No automatic receiver selection is implied. No automatic retry authority is implied. No fallback/failover authority is implied. No persistent production activation is implied.
