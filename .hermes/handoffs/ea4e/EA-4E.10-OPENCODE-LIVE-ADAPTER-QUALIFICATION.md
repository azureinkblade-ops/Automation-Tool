# EA-4E.10 OpenCode Live-Adapter Single-Shot Qualification

## Disposition

`EA-4E.10 OPENCODE LIVE ADAPTER = QUALIFIED SINGLE-SHOT / NOT COMMITTED`

---

## 1. Governing State

| Field | Value |
|-------|-------|
| GOVERNING_LOCAL_HEAD | `d660154b7afe7c31ac813e10a7382ae0a21df088` |
| GOVERNING_REMOTE_HEAD | `d660154b7afe7c31ac813e10a7382ae0a21df088` |
| CURRENT_BRANCH | `feature/ea4f-regional-hand-repair-pilot` |

## 2. Frozen Contracts

| Field | Value |
|-------|-------|
| EA4E6_ROUTER_CONTRACT_ID | `92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f` |
| EA4E7_AUTHORITY_CONTRACT_ID | `c21e17d125b5cb9292a5cb639e3b9b31af8e52b2577d700eb6307881aeeb2048` |
| OPENCODE_TRANSPORT_CONTRACT_ID | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` |
| OPENCODE_MODEL_BINDING_ID | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |

## 3. Authority

| Field | Value |
|-------|-------|
| AUTHORITY_ID | `dispatch-authority-7c3c175a46db8e2e` |
| AUTHORITY_VALID | YES |
| AUTHORITY_ATTEMPT_LIMIT | 1 |

## 4. Qualification Task

`Return exactly: EA4E10_OPENCODE_LIVE_OK`

## 5. Pre-Live Negative Gates

| Gate | Result |
|------|--------|
| PRELIVE_MISSING_AUTHORITY | REJECT / EXECUTION_AUTHORITY_MISSING |
| PRELIVE_DENIED_AUTHORITY | REJECT / EXECUTION_AUTHORITY_DENIED |
| PRELIVE_RECEIVER_MISMATCH | REJECT / AUTHORITY_RECEIVER_MISMATCH |
| PRELIVE_ROUTER_CONTRACT_MISMATCH | REJECT / ROUTER_CONTRACT_MISMATCH |
| PRELIVE_TRANSPORT_MISMATCH | REJECT / TRANSPORT_CONTRACT_MISMATCH |
| PRELIVE_MODEL_BINDING_MISMATCH | REJECT / MODEL_BINDING_MISMATCH |
| PRELIVE_UNSUPPORTED_RECEIVER | REJECT / UNSUPPORTED_RECEIVER |
| PRELIVE_NO_FALLBACK | PASS |

## 6. Live Dispatch

| Field | Value |
|-------|-------|
| ROUTE_DECISION | SELECTED |
| SELECTED_RECEIVER | opencode-cli-agent |
| DISPATCH_DECISION | AUTHORIZED |
| REAL_RECEIVER_ADAPTER_CALLED | YES |
| REAL_RECEIVER_ADAPTER_CALL_COUNT | 1 |

## 7. OpenCode Result

| Field | Value |
|-------|-------|
| OPENCODE_RESULT | `EA4E10_OPENCODE_LIVE_OK` |
| OPENCODE_RESULT_NORMALIZED | `EA4E10_OPENCODE_LIVE_OK` |
| OPENCODE_RESULT_VALID | YES |

## 8. Process Lifecycle

| Field | Value |
|-------|-------|
| PROCESS_START_COUNT | 1 |
| PROCESS_EXIT_COUNT | 1 |
| PROCESS_EXIT_CODE | 0 |
| PROCESS_TIMEOUT | NO |
| PROCESS_KILLED | NO |

## 9. Model Accounting

| Field | Value |
|-------|-------|
| MODEL_INVOCATION_COUNT | 1 |

## 10. Live Execution Accounting

| Field | Value |
|-------|-------|
| NEW_OPENCODE_TASKS | 1 |
| NEW_KILO_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 1 |
| NEW_RECEIVER_PROCESSES | 1 |
| LIVE_ROUTER_EXECUTIONS | 1 |
| LIVE_DISPATCH_EXECUTIONS | 1 |
| REAL_RECEIVER_ADAPTER_CALLS | 1 |
| FALLBACK_ATTEMPTS | 0 |
| FAILOVER_ATTEMPTS | 0 |

## 11. Post-Task Cleanup

| Field | Value |
|-------|-------|
| RECEIVER_PROCESS_REMAINING_AFTER | NO |
| CLEANUP_RESULT | OpenCode self-terminated cleanly |

## 12. Test Results

| Test | Result |
|------|--------|
| EA4E10_TESTS | (see regression) |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |

## 13. Repository State

| Field | Value |
|-------|-------|
| HEAD | `d660154b7afe7c31ac813e10a7382ae0a21df088` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.10 OPENCODE LIVE ADAPTER = QUALIFIED SINGLE-SHOT / NOT COMMITTED`

`EA-4E.10 = HOLD / COMMIT REQUIRED`

No Kilo execution is authorized. No general production receiver execution is implied. No automatic routing is implied. No fallback/failover authority is implied.
