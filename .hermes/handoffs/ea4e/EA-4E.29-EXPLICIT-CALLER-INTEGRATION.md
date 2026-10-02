# EA-4E.29 Explicit Caller Integration

Date: 2026-09-06

## Purpose

Close the non-live composition gap between an explicit caller, EA-4E.22 binding resolution, EA-4E.28 authorization issuance, and EA-4E.26 runtime consumption.

## Qualified Path

```text
explicit caller envelope
-> explicit receiver and execution-request identity checks
-> pre-existing EA-4E.22 binding resolution
-> external EA-4E.28 issuance
-> EA-4E.26 consume-only runtime
-> routing / issuance / authority / activation
-> binding and resolution revalidation
-> EA-4E.23 atomic claim
-> ProductionExecutionBoundary
-> injected fake executor
```

The caller denies missing issue instructions, pre-populated authorization, execution-request or receiver disagreement, unresolved bindings, and issuer rejection. It does not select a receiver, create a binding, retry, fall back, or fail over. Identical replay reaches the runtime with the same immutable authorization and is denied as consumed without a second executor call.

## Contract

```text
EA4E29_CALLER_CONTRACT_ID=aa9b2e1a6bb2307e814bb66913f7fdb8134a3fbb0273bfb8be000da6e480ee9a
CONTRACT_DETERMINISTIC=YES
EA4E14_TO_EA4E23_CONTRACTS_UNCHANGED=YES
EA4E26_CONTRACT_UNCHANGED=YES
EA4E28_CONTRACT_UNCHANGED=YES
```

## Verification

```text
EA4E29_FOCUSED_TESTS=11 passed
FINAL_SAFE_NONLIVE_TEST_TOTAL=464 passed
FINAL_SAFE_NONLIVE_FAILURES=0
KILO_FULL_FAKE_PATH=PASS
OPENCODE_FULL_FAKE_PATH=PASS
REAL_EXECUTOR_TRIPWIRE_HITS=0
REAL_ADAPTER_TRIPWIRE_HITS=0
PROCESS_START_TRIPWIRE_HITS=0
```

## No-Live Boundary

```text
REAL_RECEIVER_EXECUTION=0
MODEL_INVOCATIONS=0
RECEIVER_PROCESSES=0
LIVE_BINDINGS=0
LIVE_INVOCATION_AUTHS=0
LIVE_DISPATCH=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Files

```text
tools/hermes_core/governed_production_caller.py
tests/hermes_core/test_governed_production_caller.py
.hermes/handoffs/ea4e/EA-4E.29-EXPLICIT-CALLER-INTEGRATION.md
```

## Forward Boundary

No further composition gap remains between an explicit caller request and fake execution. Static review did identify that EA-4E.28 issuance replay and EA-4E.23 consumption state are process-local. Making that state restart-durable would require a separately authorized EA-4E.23 contract-impact phase; earlier-contract rolls are outside this continuation authorization. Live receiver qualification remains later still.

```text
NEXT_NONLIVE_ARCHITECTURE_GAP_FOUND=YES
NEXT_NONLIVE_ARCHITECTURE_GAP=restart-durable issuance replay and atomic-consumption state
EVIDENCE_FOR_NEXT_GAP=EA-4E.28 uses process-local _issued and EA-4E.23 uses process-local _consumed_authorizations/_authorization_identities
NEXT_PHASE_REQUIRES_LIVE_AUTHORIZATION=NO
NEXT_PHASE_REQUIRES_SEPARATE_CONTRACT_AUTHORIZATION=YES
NEXT_PHASE_DESCRIPTION=design durable invocation-authorization issuance and consumption without weakening atomic single-use semantics
EA-4E.29=QUALIFIED NON-LIVE / NOT COMMITTED
```
