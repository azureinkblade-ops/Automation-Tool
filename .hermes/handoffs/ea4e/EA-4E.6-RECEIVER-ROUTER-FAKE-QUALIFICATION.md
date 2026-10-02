# EA-4E.6 Receiver Router Fake/Non-Live Qualification

## Disposition

`EA-4E.6 RECEIVER ROUTER = QUALIFIED FAKE / NON-LIVE / NOT COMMITTED`

---

## 1. Governing Commit

| Field | Value |
|-------|-------|
| HEAD | `939ff55003cc27b987cdfab77e42fbe7e1985f3e` |

## 2. Qualified Receiver Set

| Receiver ID | Class | Transport Contract ID | Model Binding ID |
|-------------|-------|----------------------|------------------|
| opencode-cli-agent | OPENCODE | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |
| kilo-cli-agent | KILO | `c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500` | `b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544` |

## 3. Router Canonical Material

```json
{
  "schema_id": "hermes.receiver-router/v1",
  "schema_version": "ea4e.6",
  "qualified_receivers": {
    "kilo-cli-agent": {
      "transport_contract_id": "c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500",
      "model_binding_id": "b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544",
      "receiver_class": "KILO"
    },
    "opencode-cli-agent": {
      "transport_contract_id": "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f",
      "model_binding_id": "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371",
      "receiver_class": "OPENCODE"
    }
  },
  "fallback_policy": "NONE",
  "execution_authority_required": true,
  "routing_precedence": "EXPLICIT_RECEIVER_ID",
  "fail_closed_behaviors": [
    "EMPTY_RECEIVER_ID",
    "UNSUPPORTED_RECEIVER",
    "CONTRACT_MISMATCH"
  ]
}
```

## 4. Router Contract ID

| Field | Value |
|-------|-------|
| EA4E6_ROUTER_CONTRACT_ID | `92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f` |

## 5. Fake Routing Cases

| Case | Input | Decision | Reason | Process Started |
|------|-------|----------|--------|-----------------|
| OpenCode selection | `receiver_id=opencode-cli-agent` | SELECTED | RECEIVER_QUALIFIED | NO |
| Kilo selection | `receiver_id=kilo-cli-agent` | SELECTED | RECEIVER_QUALIFIED | NO |
| Unsupported receiver | `receiver_id=unknown-receiver` | REJECT | UNSUPPORTED_RECEIVER | NO |
| Empty receiver ID | `receiver_id=""` | REJECT | EMPTY_RECEIVER_ID | NO |
| Contract mismatch | `kilo-cli-agent` + wrong contract | REJECT | CONTRACT_MISMATCH | NO |
| Execution authority absent | `kilo-cli-agent` + no authority | SELECTED | RECEIVER_QUALIFIED | NO |

## 6. Execution-Authority Boundary

| Field | Value |
|-------|-------|
| ROUTER_CREATES_EXECUTION_AUTHORITY | NO |
| ROUTER_STARTS_WORKER_DIRECTLY | NO |
| ROUTE_SELECTED != EXECUTION_AUTHORIZED | YES |
| ROUTE_SELECTED != PROCESS_STARTED | YES |

## 7. Security Invariants

| Field | Value |
|-------|-------|
| PERMISSION_POLICY_MUTATED | NO |
| ISOLATION_POLICY_MUTATED | NO |
| MODEL_BINDING_MUTATED | NO |
| PROCESS_LIFECYCLE_MUTATED | NO |
| TASK_TEXT_CONTROLS_ROUTER | NO |
| TASK_TEXT_CONTROLS_RECEIVER_SECURITY | NO |

## 8. Deterministic Routing

| Field | Value |
|-------|-------|
| DETERMINISTIC_ROUTING | YES |
| SAME_INPUT_SAME_OUTPUT | YES |
| NO_RANDOMNESS | YES |
| NO_MODEL_BASED_ROUTER | YES |
| NO_LLM_ARBITRATION | YES |
| NO_NETWORK_LOOKUP | YES |
| NO_FALLBACK | YES |

## 9. Test Results

| Test | Result |
|------|--------|
| `test_receiver_router.py` | 24 passed / 0 failed |
| `test_receiver_adapter.py` | 14 passed / 0 failed |
| `test_kilo_adapter.py` | 107 passed / 0 failed |
| Full hermes_core regression | 1568 passed / 3 failed (inherited Codex env) |

## 10. Live Execution Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_PROVIDER_REQUESTS | 0 |
| REAL_OPENCODE_PROCESS_STARTED | NO |
| REAL_KILO_PROCESS_STARTED | NO |

## 11. Repository Mutation

| Field | Value |
|-------|-------|
| NEW_TRACKED_REPOSITORY_MUTATION_FROM_TESTS | 0 |
| UNRELATED_PREEXISTING_WIP_PRESERVED | YES |

## 12. Implementation Scope

| Path | Purpose |
|------|---------|
| `tools/hermes_core/receiver_router.py` | New router module |
| `tests/hermes_core/test_receiver_router.py` | Router qualification tests |

## 13. Current Repository State

| Field | Value |
|-------|-------|
| HEAD | `939ff55003cc27b987cdfab77e42fbe7e1985f3e` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.6 RECEIVER ROUTER = QUALIFIED FAKE / NON-LIVE / NOT COMMITTED`

`EA-4E.6 = HOLD / COMMIT REQUIRED`

No live router execution is implied. No production routing is implied.
