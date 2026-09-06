# EA-4E.26 / EA-4E.26A — Dual-Receiver Governed Production Runtime Integration

## Summary

EA-4E.26 establishes one permanent governed production-runtime entrypoint
(`GovernedProductionRuntime`) that consumes either explicitly selected
qualified receiver while preserving every existing governance boundary.

EA-4E.26A closes the three qualification gaps identified in the initial
EA-4E.26 HOLD: exact fake outputs, cross-receiver auth isolation, and
the complete 30-case fail-closed matrix.

## Architecture

```
explicit receiver
  → router
  → issuance
  → authority validation
  → activation validation
  → EA-4E.21 pre-existing binding check
  → EA-4E.22 bound-executor resolution
  → EA-4E.23 invocation authorization
  → atomic single-use claim
  → production execution boundary
  → executor
```

## Key Invariants

1. **Explicit receiver only** — `receiver_id` is required; no inference.
2. **No default receiver** — missing/unknown receiver = DENY.
3. **No auto-bind** — binding must pre-exist (EA-4E.21).
4. **EA-4E.22 resolution required** — no direct registry execution.
5. **EA-4E.23 invocation authorization required** — binding alone ≠ authorization.
6. **Atomic single-use claim** — `claim_for_execution()` before boundary.
7. **Receiver isolation** — cross-receiver replay denied.
8. **No fallback/failover/retry** — strict fail-closed.
9. **Default-off** — runtime is inert by default.
10. **Fake executors only** for qualification — no real receiver processes.

## Implementation Files

- `tools/hermes_core/governed_production_runtime.py` — Runtime coordinator
- `tests/hermes_core/test_governed_production_runtime.py` — 64 tests, all pass

## Contract

- Schema: `hermes.dual-receiver-governed-production-runtime/v1`
- Version: `ea4e.26`
- Artifact: `1`
- Contract ID: `c49556e63645fefc31a3f03df726d99447620b7ae6ae4a2c78b96ae0feeb8393`

## EA-4E.26A Gap Closure

### Gap A: Exact Positive Kilo Fake Output
- **Before**: `EA4E26_KILO-CLI-AGENT_GOVERNED_RUNTIME_OK`
- **After**: `EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK`
- **Status**: CLOSED

### Gap B: Exact Positive OpenCode Fake Output
- **Before**: `EA4E26_OPENCODE-CLI-AGENT_GOVERNED_RUNTIME_OK`
- **After**: `EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK`
- **Status**: CLOSED

### Gap C: Cross-Receiver Authorization Isolation
- **KILO_AUTH_CANNOT_EXECUTE_OPENCODE**: YES (binding mismatch → NO_ACTIVE_EXECUTOR_BINDING)
- **OPENCODE_AUTH_CANNOT_EXECUTE_KILO**: YES (binding mismatch → NO_ACTIVE_EXECUTOR_BINDING)
- **Status**: CLOSED

### Gap D: Complete Fail-Closed Matrix
- **Before**: 8 cases
- **After**: 30 cases (all pass, 0 failures)
- **Status**: CLOSED

## Qualification Result

```
EA-4E.26 = QUALIFIED NON-LIVE / DUAL-RECEIVER GOVERNED PRODUCTION RUNTIME /
           EXPLICIT RECEIVER ONLY / NO DEFAULT RECEIVER / NO AUTO-BIND /
           PRE-EXISTING BINDING REQUIRED / EA-4E.22 RESOLUTION REQUIRED /
           EA-4E.23 INVOCATION AUTHORIZATION REQUIRED /
           ATOMIC SINGLE-USE CLAIM REQUIRED / KILO AND OPENCODE ISOLATED /
           NO RETRY / NO FALLBACK / NO FAILOVER / DEFAULT-OFF /
           NO PERSISTENT EXECUTION / ALL DIRECTLY RELEVANT NON-LIVE TESTS PASS /
           NO NEW LIVE EXECUTION / NOT COMMITTED
```

## Regression

- Directly relevant non-live suites: **all pass** (524 tests across EA-4E.26, 25, 25A, 25R-A, 25R-B, 24, 23, 22, 21, 18, 17, 14).
- EA-4E.26 tests: **64/64 pass**.
- Broader regression: **2219 pass, 5 fail** — the 5 failures are the known
  inherited environmental failures (3 Codex binary-dependent, 1 OpenCode spool-dependent,
  1 OpenCode live path with real model invocation).
- No NEW failures introduced by EA-4E.26/26A.

## Frozen Receivers

- `opencode-cli-agent` — `RealOpenCodeProductionExecutor`
- `kilo-cli-agent` — `RealKiloProductionExecutor`

## Frozen Contracts (unchanged)

- EA4E23_INVOCATION_CONTRACT_ID: `1d34f4c19b6f7e05cd42e6e43dc656e8d2fe8cb53a6187b20ce65983c70243d8`
- EA4E22_INTEGRATION_CONTRACT_ID: `e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a`
- EA4E21_BINDING_CONTRACT_ID: `99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7`
- EA4E18_INTEGRATION_CONTRACT_ID: `d03fa98111e8ac6d356de093e7259854a0b2ae0c986e263b65f798343451b459`
- EA4E17_ISSUANCE_CONTRACT_ID: `26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78`
- EA4E14_EXECUTION_CONTRACT_ID: `89f25b6c4a50a4c78ccf399af5391a4666d594085d17d38e2cf89d33bd8719b6`
- EA4E26_CONTRACT_ID: `c49556e63645fefc31a3f03df726d99447620b7ae6ae4a2c78b96ae0feeb8393`
