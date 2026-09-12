# EA-4E.7 Execution-Authority Integration Boundary

## Disposition

`EA-4E.7 EXECUTION-AUTHORITY BOUNDARY = QUALIFIED FAKE / NON-LIVE / NOT COMMITTED`

---

## 1. Governing State

| Field | Value |
|-------|-------|
| GOVERNING_HEAD | `8246a9671eaeb22fe047afa7952b7d8bc93bf047` |
| EA4E6_COMMIT | `8246a9671eaeb22fe047afa7952b7d8bc93bf047` |
| EA4E6_ROUTER_CONTRACT_ID | `92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f` |

## 2. Authority Schema

| Field | Value |
|-------|-------|
| AUTHORITY_SCHEMA | `hermes.execution-authority.receiver-dispatch/v1` |
| AUTHORITY_SCHEMA_VERSION | `ea4e.7` |
| AUTHORITY_ARTIFACT_VERSION | `1` |
| AUTHORITY_CONTRACT_ID | `c21e17d125b5cb9292a5cb639e3b9b31af8e52b2577d700eb6307881aeeb2048` |

## 3. Qualified Receiver Set

| Receiver ID | Transport Contract ID | Model Binding ID |
|-------------|----------------------|------------------|
| opencode-cli-agent | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |
| kilo-cli-agent | `c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500` | `b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544` |

## 4. Positive Fake Authorization Cases

| Case | Route Decision | Authority Valid | Dispatch Decision | Process Started | Model Invoked |
|------|---------------|-----------------|-------------------|-----------------|---------------|
| OpenCode | SELECTED | YES | AUTHORIZED | NO | NO |
| Kilo | SELECTED | YES | AUTHORIZED | NO | NO |

## 5. Fail-Closed Cases

| Case | Reason | Process Started |
|------|--------|-----------------|
| Missing authority | EXECUTION_AUTHORITY_MISSING | NO |
| Denied authority | EXECUTION_AUTHORITY_DENIED | NO |
| Receiver mismatch | AUTHORITY_RECEIVER_MISMATCH | NO |
| Router contract mismatch | ROUTER_CONTRACT_MISMATCH | NO |
| Transport contract mismatch | TRANSPORT_CONTRACT_MISMATCH | NO |
| Model binding mismatch | MODEL_BINDING_MISMATCH | NO |
| Malformed authority | MALFORMED_AUTHORITY | NO |
| Expired authority | AUTHORITY_EXPIRED | NO |
| Unsupported receiver | ROUTE_NOT_SELECTED | NO |

## 6. Execution Boundary

| Field | Value |
|-------|-------|
| ROUTER_CREATES_EXECUTION_AUTHORITY | NO |
| ROUTER_STARTS_RECEIVER | NO |
| AUTHORITY_VALIDATION_STARTS_RECEIVER | NO |
| FAKE_DISPATCH_STARTS_RECEIVER | NO |
| ROUTE_SELECTED != EXECUTION_AUTHORIZED | YES |
| EXECUTION_AUTHORIZED != PROCESS_STARTED | YES |

## 7. Security Invariants

| Field | Value |
|-------|-------|
| PERMISSION_POLICY_MUTATED | NO |
| ISOLATION_POLICY_MUTATED | NO |
| MODEL_BINDING_MUTATED | NO |
| PROCESS_LIFECYCLE_MUTATED | NO |

## 8. Test Results

| Test | Result |
|------|--------|
| EA4E7_TESTS | 28 passed / 0 failed |
| RECEIVER_ROUTER_REGRESSION | 24 passed / 0 failed |
| RECEIVER_ADAPTER_REGRESSION | 14 passed / 0 failed |
| KILO_ADAPTER_REGRESSION | 107 passed / 0 failed |
| FULL_REGRESSION_RESULT | 1596 passed / 3 failed (inherited Codex env) |

## 9. Live Execution Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |
| LIVE_ROUTER_EXECUTIONS | 0 |
| LIVE_DISPATCH_EXECUTIONS | 0 |

## 10. Implementation Scope

| Path | Purpose |
|------|---------|
| `tools/hermes_core/receiver_dispatch.py` | New dispatch module |
| `tests/hermes_core/test_receiver_dispatch.py` | Dispatch qualification tests |

## 11. Current Repository State

| Field | Value |
|-------|-------|
| HEAD | `8246a9671eaeb22fe047afa7952b7d8bc93bf047` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.7 EXECUTION-AUTHORITY BOUNDARY = QUALIFIED FAKE / NON-LIVE / NOT COMMITTED`

`EA-4E.7 = HOLD / COMMIT REQUIRED`

No live router execution is implied. No receiver execution is implied. No production routing is implied. No fallback/failover authority is implied.
