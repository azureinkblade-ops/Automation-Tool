# EA-4E.17A Replay-Policy Defect Correction / Non-Live Requalification

## Disposition

`EA-4E.17A REPLAY POLICY = CORRECTED / QUALIFIED NON-LIVE / NOT COMMITTED`

---

## 1. Governing State

| Field | Value |
|-------|-------|
| GOVERNING_LOCAL_HEAD | `9b105fd31e9b4775fa688817b4790de7891c9c66` |
| GOVERNING_REMOTE_HEAD | `9b105fd31e9b4775fa688817b4790de7891c9c66` |
| CURRENT_BRANCH | `feature/ea4f-regional-hand-repair-pilot` |

## 2. Defect Description

### Original Precedence (Defective)

```
if existing_hash != canonical_hash:
    REQUEST_ID_COLLISION

if existing_receiver != request.receiver_id:
    CROSS_RECEIVER_REPLAY
```

### Problem

Because `receiver_id` contributes to canonical request material, changing the receiver from `kilo-cli-agent` to `opencode-cli-agent` necessarily changes the canonical hash. Therefore, an actual cross-receiver replay was intercepted by `REQUEST_ID_COLLISION` before `CROSS_RECEIVER_REPLAY` could be returned.

### Corrected Precedence

```
if existing_receiver != request.receiver_id:
    CROSS_RECEIVER_REPLAY

elif existing_hash != canonical_hash:
    REQUEST_ID_COLLISION

else:
    qualified duplicate/idempotency behavior
```

## 3. Security Rationale

The policy must distinguish:

- **REQUEST MUTATION**: Same receiver, different canonical material → `REQUEST_ID_COLLISION`
- **RECEIVER REBINDING**: Different receiver → `CROSS_RECEIVER_REPLAY`

Receiver rebinding is a distinct authorization-boundary violation and should not be hidden behind a generic request collision result.

## 4. Exact Changed Production Lines

**File**: `tools/hermes_core/production_issuance.py`

```python
# Gate 13: Request-ID collision check
canonical_hash = sha256_payload(request.to_canonical_dict())
if request.request_id in self._issued_requests:
    existing_receiver, existing_hash = self._issued_requests[request.request_id]
    if existing_receiver != request.receiver_id:
        return self._reject(request, "CROSS_RECEIVER_REPLAY")
    if existing_hash != canonical_hash:
        return self._reject(request, "REQUEST_ID_COLLISION")
```

**File**: `tools/hermes_core/production_issuance.py` (contract computation)

Added `replay_policy` section to `compute_ea4e17_issuance_contract_id()`:
```python
"replay_policy": {
    "cross_receiver_replay_precedence": True,
    "request_id_collision_check": True,
    "identical_duplicate_allowed": True,
},
```

## 5. Request-ID Collision Test

| Field | Value |
|-------|-------|
| SAME ID / SAME RECEIVER / DIFFERENT NONCE | REJECT / REQUEST_ID_COLLISION |
| SAME ID / SAME RECEIVER / DIFFERENT TRANSPORT | REJECT / TRANSPORT_CONTRACT_MISMATCH (earlier gate) |
| SAME ID / SAME RECEIVER / DIFFERENT MODEL | REJECT / MODEL_BINDING_MISMATCH (earlier gate) |

## 6. Cross-Receiver Replay Tests

| Field | Value |
|-------|-------|
| KILO → OPENCODE REPLAY | REJECT / CROSS_RECEIVER_REPLAY |
| OPENCODE → KILO REPLAY | REJECT / CROSS_RECEIVER_REPLAY |
| MULTI-FIELD CROSS-RECEIVER REPLAY | REJECT / CROSS_RECEIVER_REPLAY |

## 7. No-Authority / No-Activation / No-Execution Proofs

| Field | Value |
|-------|-------|
| SECOND_AUTHORITY_ISSUED_ON_COLLISION | NO |
| SECOND_ACTIVATION_ISSUED_ON_COLLISION | NO |
| EXECUTOR_CALLED_ON_COLLISION | NO |
| SECOND_AUTHORITY_ISSUED_ON_CROSS_RECEIVER_REPLAY | NO |
| SECOND_ACTIVATION_ISSUED_ON_CROSS_RECEIVER_REPLAY | NO |
| EXECUTOR_CALLED_ON_CROSS_RECEIVER_REPLAY | NO |

## 8. Determinism

| Field | Value |
|-------|-------|
| REPLAY_CLASSIFICATION_DETERMINISTIC | YES |
| REQUEST_ID_COLLISION_DETERMINISTIC | YES |
| CROSS_RECEIVER_REPLAY_DETERMINISTIC | YES |

## 9. Clock Invariants

| Field | Value |
|-------|-------|
| PRODUCTION_ISSUANCE_USES_INJECTED_CLOCK | YES |
| PRODUCTION_ISSUANCE_DIRECT_DATETIME_NOW | NO |
| QUALIFICATION_TEST_CLOCK_FIXED | YES |
| SYSTEM_CLOCK_REQUIRED_FOR_TESTS | NO |

## 10. EA-4E.17 Contract Impact

| Field | Value |
|-------|-------|
| EA4E17_ISSUANCE_CONTRACT_ID_BEFORE | `aff83b6ea62079e7ac656350f75582e46561e571593eead22dfa07feb2717084` |
| EA4E17_ISSUANCE_CONTRACT_ID_AFTER | `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78` |
| EA4E17_ISSUANCE_CONTRACT_CHANGED | YES |
| CONTRACT_CHANGE_REASON | Added replay_policy section to canonical contract material |
| EA4E17_CONTRACT_MATERIAL_INCOMPLETE | NO |

## 11. EA-4E.18 Contract Impact

| Field | Value |
|-------|-------|
| EA4E18_BINDS_EA4E17_CONTRACT_ID | YES |
| EA4E18_INTEGRATION_CONTRACT_ID_BEFORE | `27d0eb71375ea02bf524e69034c8a572b36209b257a456a71730c8612e851379` |
| EA4E18_INTEGRATION_CONTRACT_ID_AFTER | `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459` |
| EA4E18_INTEGRATION_CONTRACT_CHANGED | YES |

## 12. EA-4E.19 Live-Result Impact Analysis

| Field | Value |
|-------|-------|
| EA4E19_LIVE_RESULT_REMAINS_VALID | YES |
| EA4E19_SECOND_LIVE_RUN_REQUIRED | NO |
| LIVE_EXECUTION_BEHAVIOR_AFFECTED_BY_REPLAY_PRECEDENCE | NO |

**Rationale**: The successful live request was a first issuance and did not exercise duplicate/replay semantics. The replay-policy correction only affects duplicate/replay behavior, not first-issuance behavior.

## 13. Downstream Non-Live Regression

| Test | Result |
|------|--------|
| EA4E17A_TESTS | PASS |
| EA4E17_REGRESSION | PASS |
| EA4E18_REGRESSION | PASS |
| EA4E19_NONLIVE_TESTS | PASS |
| TEST_SINGLE_SHOT_BUDGET | PASS |
| SINGLE_SHOT_BUDGET_REASON | LIVE_INVOCATION_BUDGET_EXHAUSTED |
| TEST_REQUEST_ID_COLLISION | PASS |
| REQUEST_ID_COLLISION_RESULT | REJECT / REQUEST_ID_COLLISION |
| TEST_CROSS_RECEIVER_REPLAY | PASS |
| CROSS_RECEIVER_REPLAY_RESULT | REJECT / CROSS_RECEIVER_REPLAY |
| MULTI_FIELD_CROSS_RECEIVER_REPLAY_TEST | PASS |
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

## 14. Default State

| Field | Value |
|-------|-------|
| DEFAULT_COORDINATOR_CAN_START_REAL_RECEIVER | NO |
| DEFAULT_COORDINATOR_REAL_EXECUTOR_COUNT | 0 |
| REAL_PRODUCTION_EXECUTORS_CONFIGURED_BY_DEFAULT | NO |
| REAL_EXECUTOR_DEFAULT_PRESENT | NO |
| DEFAULT_ISSUANCE_DECISION | DENY |
| PRODUCTION_ACTIVATION_DEFAULT | DISABLED |
| PERSISTENT_PRODUCTION_EXECUTION_ENABLED | NO |
| AUTOMATIC_RECEIVER_SELECTION_ENABLED | NO |
| AUTOMATIC_RETRY_ENABLED | NO |
| FALLBACK_ENABLED | NO |
| FAILOVER_ENABLED | NO |

## 15. Live Accounting

| Field | Value |
|-------|-------|
| ADDITIONAL_KILO_TASKS | 0 |
| ADDITIONAL_OPENCODE_TASKS | 0 |
| ADDITIONAL_MODEL_INVOCATIONS | 0 |
| ADDITIONAL_RECEIVER_PROCESSES | 0 |
| ADDITIONAL_REAL_EXECUTOR_CALLS | 0 |
| ADDITIONAL_REAL_RECEIVER_ADAPTER_CALLS | 0 |

## 16. Repository State

| Field | Value |
|-------|-------|
| HEAD | `9b105fd31e9b4775fa688817b4790de7891c9c66` |
| STAGED | 0 |
| COMMIT | NO |
| PUSH | NO |

---

## GOVERNANCE

`EA-4E.17A REPLAY POLICY = CORRECTED / QUALIFIED NON-LIVE / NOT COMMITTED`

`EA-4E.18 = REQUALIFIED NON-LIVE AGAINST CORRECTED ISSUANCE POLICY`

`EA-4E.19 = LIVE RESULT PRESERVED / NON-LIVE REPLAY SEMANTICS VERIFIED / NOT COMMITTED`

`EA-4E.17A = HOLD / COMMIT REQUIRED`

No second live execution is authorized.
