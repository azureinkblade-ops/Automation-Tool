# EA-4E.28 External Invocation-Authorization Issuer

Date: 2026-09-06

## Purpose

Provide the missing owner for deterministic EA-4E.23 artifact issuance while preserving `RUNTIME != INVOCATION_AUTHORIZATION_ISSUER`.

## Boundary

The issuer requires an explicit issue request and a successful EA-4E.22 resolution. It binds authorization to the exact execution request, receiver, binding, enablement, attempt, runtime scope, delegation class, nonce, and TTL. Authorization cannot outlive the resolved binding.

Identical replay revalidates the current resolution before returning the existing immutable artifact. Reusing an issue-request ID with changed canonical material denies. Authorization identity includes the issuance window. Unsupported receivers and incomplete resolved objects deny. The component cannot route, bind, execute, access an adapter, start a process, invoke a model, or perform I/O.

```text
RUNTIME_IS_ISSUER=NO
EXPLICIT_ISSUE_REQUEST_REQUIRED=YES
RESOLVED_BINDING_REQUIRED=YES
REQUEST_IDENTITY_BOUND=YES
RECEIVER_BINDING_ENABLEMENT_BOUND=YES
AUTHORIZATION_OUTLIVES_BINDING=DENY
IDENTICAL_REPLAY=RETURN_EXISTING
SAME_ID_CONFLICT=DENY
DEFAULT_DECISION=DENY
```

## Contract

```text
EA4E28_ISSUER_CONTRACT_ID=cbf86c71356366d489920b226dfb181c3fcafc581ec567d19433a94159a6c5da
CONTRACT_DETERMINISTIC=YES
EA4E14_TO_EA4E23_CONTRACTS_UNCHANGED=YES
EA4E26_CONTRACT_UNCHANGED=YES
```

## Verification

```text
EA4E28_FOCUSED_TESTS=27 passed
EA4E28_REGRESSION_TOTAL=453 passed
EA4E28_REGRESSION_FAILURES=0
REAL_EXECUTOR_CALLS=0
REAL_ADAPTER_CALLS=0
PROCESS_STARTS=0
MODEL_INVOCATIONS=0
GPU_GENERATIONS=0
COMFYUI_CALLS=0
```

## Files

```text
tools/hermes_core/production_invocation_authorization_issuer.py
tests/hermes_core/test_production_invocation_authorization_issuer.py
.hermes/handoffs/ea4e/EA-4E.28-EXTERNAL-INVOCATION-AUTH-ISSUER.md
```

## Disposition

```text
EA-4E.28=QUALIFIED NON-LIVE / NOT COMMITTED
NEXT_GAP=NON-LIVE CALLER COMPOSITION OF RESOLUTION, ISSUANCE, AND RUNTIME CONSUMPTION (closed by EA-4E.29)
```
