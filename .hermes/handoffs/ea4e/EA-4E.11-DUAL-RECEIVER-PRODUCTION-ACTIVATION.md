# EA-4E.11 Dual-Receiver Production Activation

## Disposition

`EA-4E.11 DUAL-RECEIVER PRODUCTION ACTIVATION = QUALIFIED NON-LIVE / NOT COMMITTED`

---

## 1. Governing State

| Field | Value |
|-------|-------|
| HEAD | `81d05e6435ce0669a2ced9cb24c5cbbee35217d8` |

## 2. Frozen Contracts

| Field | Value |
|-------|-------|
| EA4E6_ROUTER_CONTRACT_ID | `92b4a457bcfbe70fb993d44ba3f087c33f2804820398e107d44af6a90fdd0e9f` |
| EA4E7_AUTHORITY_CONTRACT_ID | `c21e17d125b5cb9292a5cb639e3b9b31af8e52b2577d700eb6307881aeeb2048` |
| KILO_TRANSPORT_CONTRACT_ID | `c05d4baf553e0d3b5d2631d5cc5957dd763f96913237c9a3b33fd51555631500` |
| KILO_MODEL_BINDING_ID | `b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544` |
| OPENCODE_TRANSPORT_CONTRACT_ID | `192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f` |
| OPENCODE_MODEL_BINDING_ID | `cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371` |

## 3. Activation Contract

| Field | Value |
|-------|-------|
| ACTIVATION_SCHEMA | `hermes.production-activation.receiver-dispatch/v1` |
| ACTIVATION_CONTRACT_ID | `0d0b2d0327c5f3c4f32d47563f86fe2158b9b31a530ccbb26568f960c73df9c6` |
| PRODUCTION_ACTIVATION_DEFAULT | DISABLED |

## 4. Production Integration

| Field | Value |
|-------|-------|
| PRODUCTION_INTEGRATION_SEAM | `ProductionReceiverCoordinator` |
| RECEIVER_RESOLVER | `ReceiverAdapterResolver` |

## 5. Positive Fake Results

| Case | Route | Authority | Activation | Adapter | Process | Model |
|------|-------|-----------|------------|---------|---------|-------|
| Kilo | SELECTED | YES | YES | KILO | NO | NO |
| OpenCode | SELECTED | YES | YES | OPENCODE | NO | NO |

## 6. Fail-Closed Results

| Case | Reason |
|------|--------|
| Missing activation | PRODUCTION_ACTIVATION_MISSING |
| Disabled activation | PRODUCTION_ACTIVATION_DISABLED |
| Activation receiver mismatch | ACTIVATION_RECEIVER_MISMATCH |
| Authority receiver mismatch | AUTHORITY_RECEIVER_MISMATCH |
| Unsupported receiver | UNSUPPORTED_RECEIVER |
| Router contract mismatch | ROUTER_CONTRACT_MISMATCH |
| Transport contract mismatch | TRANSPORT_CONTRACT_MISMATCH |
| Model binding mismatch | MODEL_BINDING_MISMATCH |
| Malformed activation | MALFORMED_ACTIVATION |

## 7. No Fallback

| Field | Value |
|-------|-------|
| KILO_TO_OPENCODE_FALLBACK | NO |
| OPENCODE_TO_KILO_FALLBACK | NO |
| FALLBACK_ENABLED | NO |
| FAILOVER_ENABLED | NO |

## 8. Execution Boundary

| Field | Value |
|-------|-------|
| ROUTER_CREATES_EXECUTION_AUTHORITY | NO |
| ACTIVATION_GATE_CREATES_EXECUTION_AUTHORITY | NO |
| PRODUCTION_COORDINATOR_CREATES_EXECUTION_AUTHORITY | NO |
| ROUTER_STARTS_RECEIVER | NO |
| AUTHORITY_VALIDATOR_STARTS_RECEIVER | NO |
| ACTIVATION_VALIDATOR_STARTS_RECEIVER | NO |
| ADAPTER_RESOLVER_STARTS_RECEIVER | NO |
| QUALIFICATION_FAKE_ADAPTER_STARTS_RECEIVER | NO |

## 9. Test Results

| Test | Result |
|------|--------|
| EA4E11_TESTS | 25 passed / 0 failed |
| EA4E8_REGRESSION | PASS |
| EA4E7_REGRESSION | PASS |
| EA4E6_REGRESSION | PASS |
| RECEIVER_ADAPTER_REGRESSION | PASS |
| KILO_ADAPTER_REGRESSION | PASS |
| TOTAL | 201 passed / 0 failed |

## 10. Live Execution Accounting

| Field | Value |
|-------|-------|
| NEW_KILO_TASKS | 0 |
| NEW_OPENCODE_TASKS | 0 |
| NEW_MODEL_INVOCATIONS | 0 |
| NEW_RECEIVER_PROCESSES | 0 |

---

## GOVERNANCE

`EA-4E.11 DUAL-RECEIVER PRODUCTION ACTIVATION = QUALIFIED NON-LIVE / NOT COMMITTED`

`EA-4E.11 = HOLD / COMMIT REQUIRED`
