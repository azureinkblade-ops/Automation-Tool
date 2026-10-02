# EA-4D.4F-R12E-R7 Successor Live Validation Complete

Date: 2026-08-31

## Final State

**EA-4D.4F-R12E-R7: FAIL / TERMINAL**

- R11 design: UNCHANGED / FROZEN.
- R6: FAIL / TERMINAL (unchanged).
- R6F: PASS / COMMITTED.
- R7: FAIL / TERMINAL.
- Live Codex starts during R7: 1.
- Push: NO.

## R7 Live Authority

- **Authorized definitive starts**: 1
- **Actual definitive starts**: 1
- **Remaining**: 0

## R7 Live Result

- **PID**: 44124
- **Exit code**: 1
- **Failure boundary**: Codex usage limit (infrastructure)
- **Stdout**: `{"type":"error","message":"You've hit your usage limit..."}`
- **Process controller worked exactly as designed**: start, poll, capture, terminate
- **No model execution reached** (blocked by usage limit)
- **No retry authorized**

## R7 Identities (Fresh)

- **Proof run**: `ea4d4f-r12e-r7`
- **Runtime namespace**: `proof-adb795668b3266a8d95572cc`
- **Delegation ID**: `delegation-7395cae0c86e3c136c262caf11ad8d903ee7de999d6183d962a5c3f62daa1a9e`
- **Lease window policy**: `hermes-live-proof-lease-window/v1`
- **Lease policy ID**: `63ab96fe12a3206d7ff7f5281b6c0765c9630e394f7c6b3743bce49409a2bc31`
- **Lease issued_at**: `2026-08-31T16:37:37Z`
- **Lease expires_at**: `2026-08-31T16:42:37Z`

## Binary / CLI

- **Path**: `C:\Users\David\AppData\Local\OpenAI\Codex\bin\b99306303521e97e\codex.exe`
- **Version**: `codex-cli 0.151.0-alpha.7.2`
- **SHA-256**: `bfd4c3b971477a559eadaeae8b1e41382ccb7656bd0104970cf5c6c581f2da7d`
- **CLI contract ID**: `98cc8fd6a6ffc1bb0bb4a675d5988cc8f4c31960ada4357003980b5d8befec5b`
- **Approval policy**: `never`
- **Sandbox policy**: `read-only`

## Start Store

- **Schema version**: 3
- **Physical v3 shape**: VERIFIED (all 5 runtime/evidence fields present)
- **runtime_binding_id**: PRESENT

## Post-Live Regression

| Gate | Count |
|---|---|
| R6F focused | 10 passed |
| Concurrency | 53 passed |
| Migration | 11 passed |
| **Total** | **74 passed** |

## Capability Audit

- LIVE_CODEX_TASK_STARTS=1
- MODEL_INVOCATIONS=0 (blocked by usage limit)
- R6_RETRY=NO
- HISTORICAL_R6_DB_MUTATION=NO
- R6_LIVE_BUDGET_RESTORED=NO
- SCHEMA_VERSION_REDEFINITION=NO
- DESTRUCTIVE_DB_RESET=NO
- AUTHORITY_EXPANSION=NO
- EXECUTING_SEMANTICS_CHANGE=NO
- RESULT_SEMANTICS_CHANGE=NO
- GENERIC_SHELL=NO
- NETWORK=NO
- BROWSER=NO
- MCP=NO
- SCHEDULER=NO
- KILO=NO
- GPU=NO
- COMFYUI=NO
- STUDIO_BIBLE_IMAGE_PIPELINE=NO
- RHR=NO

## Live Accounting (Permanent)

**Original R12E**:
- `AUTHORIZED=1`
- `DEFINITIVE_STARTS=1`
- `REMAINING=0`

**R7**:
- `AUTHORIZED=1`
- `DEFINITIVE_STARTS=1`
- `REMAINING=0`

## Governance Disposition

```
EA-4D.4F-R12E-R7: FAIL / TERMINAL
FAILURE: CODEX USAGE LIMIT (INFRASTRUCTURE)
PROCESS CONTROLLER: PASS
STARTRESULT PERSISTENCE: NOT REACHED
R6 TERMINAL STATUS: UNCHANGED
R6 RETRY: NOT AUTHORIZED
SECOND R7 START: NOT AUTHORIZED
LIVE CODEX STARTS DURING R7: 1
PUSH: NO
```

## Next Authority After R7

The consumed R7 attempt cannot be retried. A future live proof requires:
1. New explicit authorization
2. Available Codex usage budget
3. Fresh identities

**NEXT LIVE VALIDATION: REQUIRES NEW EXPLICIT AUTHORIZATION**
