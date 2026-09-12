# EA-4E.13 OpenCode Production Activation Single-Shot Qualification

## Disposition

`EA-4E.13 OPENCODE PRODUCTION ACTIVATION = QUALIFIED SINGLE-SHOT LIVE / NOT COMMITTED`

---

## 1. Governing State

| Field | Value |
|-------|-------|
| GOVERNING_LOCAL_HEAD | `5d3be5123253f530487b40416642406b30d30713` |
| GOVERNING_REMOTE_HEAD | `5d3be5123253f530487b40416642406b30d30713` |
| CURRENT_BRANCH | `feature/ea4f-regional-hand-repair-pilot` |

## 2. Frozen Contracts

| Field | Value |
|-------|-------|
| EA4E6_ROUTER_CONTRACT_ID | `92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f` |
| EA4E7_AUTHORITY_CONTRACT_ID | `c21e17d125b5cb9292a5cb639e3b9b31af8e52b2577d700eb6307881aeeb2048` |
| EA4E11_ACTIVATION_CONTRACT_ID | `0d0b2d0327c5f3c4f32d47563f86fe2158b9b31a530ccbb26568f960c73df9c6` |
| OPENCODE_TRANSPORT_CONTRACT_ID | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` |
| OPENCODE_MODEL_BINDING_ID | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |

## 3. Authority

| Field | Value |
|-------|-------|
| AUTHORITY_ID | `dispatch-authority-3f8a2c9e7b1d4f6a` |
| AUTHORITY_VALID | YES |
| AUTHORITY_ATTEMPT_LIMIT | 1 |

## 4. Activation

| Field | Value |
|-------|-------|
| ACTIVATION_ID | `production-activation-7c8d9e0f1a2b3c4d` |
| ACTIVATION_VALID | YES |
| ACTIVATION_MODE | ENABLED |
| ACTIVATION_SCOPE | production |

## 5. Qualification Task

`Return exactly: EA4E13_OPENCODE_PRODUCTION_OK`

## 6. Pre-Live Negative Gates

| Gate | Result |
|------|--------|
| Missing activation | REJECT / PRODUCTION_ACTIVATION_MISSING |
| Disabled activation | REJECT / PRODUCTION_ACTIVATION_DISABLED |
| Missing authority | REJECT / EXECUTION_AUTHORITY_MISSING |
| Denied authority | REJECT / EXECUTION_AUTHORITY_DENIED |
| Authority receiver mismatch | REJECT / AUTHORITY_RECEIVER_MISMATCH |
| Activation receiver mismatch | REJECT / ACTIVATION_RECEIVER_MISMATCH |
| Router contract mismatch | REJECT / ROUTER_CONTRACT_MISMATCH |
| Authority contract mismatch | REJECT / AUTHORITY_CONTRACT_MISMATCH |
| Transport mismatch | REJECT / TRANSPORT_CONTRACT_MISMATCH |
| Model binding mismatch | REJECT / MODEL_BINDING_MISMATCH |
| Unsupported receiver | REJECT / UNSUPPORTED_RECEIVER |
| No fallback | PASS |

## 7. Live Production Activation

| Field | Value |
|-------|-------|
| ROUTE_DECISION | SELECTED |
| SELECTED_RECEIVER | opencode-cli-agent |
| DISPATCH_DECISION | AUTHORIZED |
| PRODUCTION_ACTIVATION_DECISION | ENABLED_FOR_REQUEST |
| ADAPTER_RESOLUTION | OPENCODE |
| REAL_RECEIVER_ADAPTER_CALLED | YES |
| REAL_RECEIVER_ADAPTER_CALL_COUNT | 1 |

## 8. OpenCode Result

| Field | Value |
|-------|-------|
| OPENCODE_RESULT | `EA4E13_OPENCODE_PRODUCTION_OK` |
| OPENCODE_RESULT_NORMALIZED | `EA4E13_OPENCODE_PRODUCTION_OK` |
| OPENCODE_RESULT_VALID | YES |

## 9. Process Lifecycle

| Field | Value |
|-------|-------|
| PROCESS_START_COUNT | 1 |
| PROCESS_EXIT_COUNT | 1 |
| PROCESS_EXIT_CODE | 0 |
| PROCESS_TIMEOUT | NO |
| PROCESS_KILLED | NO |

## 10. Model Accounting

| Field | Value |
|-------|-------|
| MODEL_INVOCATION_COUNT | 1 |

## 11. Live Execution Accounting

| Field | Value |
|-------|-------|
| NEW_OPENCODE_TASKS | 1 |
| NEW_KILO_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 1 |
| NEW_RECEIVER_PROCESSES | 1 |
| LIVE_ROUTER_EXECUTIONS | 1 |
| LIVE_DISPATCH_EXECUTIONS | 1 |
| PRODUCTION_ACTIVATED_EXECUTIONS | 1 |
| REAL_RECEIVER_ADAPTER_CALLS | 1 |
| FALLBACK_ATTEMPTS | 0 |
| FAILOVER_ATTEMPTS | 0 |

## 12. Post-Activation State

| Field | Value |
|-------|-------|
| ACTIVATION_REVERSION_REQUIRED | NO |
| ACTIVATION_ARTIFACT_EXPIRED_OR_CONSUMED | YES |
| PRODUCTION_ACTIVATION_DEFAULT_AFTER | DISABLED |
| PERSISTENT_PRODUCTION_EXECUTION_ENABLED_AFTER | NO |

## 13. Post-Task Cleanup

| Field | Value |
|-------|-------|
| RECEIVER_PROCESS_REMAINING_AFTER | NO |
| CLEANUP_RESULT | OpenCode self-terminated cleanly |

## 14. Test Results

| Test | Result |
|------|--------|
| EA4E13_TESTS | 12 passed / 0 failed |
| EA4E12_REGRESSION | PASS |
| EA4E11_REGRESSION | PASS |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |

## 15. Repository State

| Field | Value |
|-------|-------|
| HEAD | `5d3be5123253f530487b40416642406b30d30713` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.13 OPENCODE PRODUCTION ACTIVATION = QUALIFIED SINGLE-SHOT LIVE / NOT COMMITTED`

`EA-4E.13 = HOLD / COMMIT REQUIRED`

No Kilo execution is authorized. No persistent production activation is implied. No automatic receiver selection is implied. No fallback/failover authority is implied.
