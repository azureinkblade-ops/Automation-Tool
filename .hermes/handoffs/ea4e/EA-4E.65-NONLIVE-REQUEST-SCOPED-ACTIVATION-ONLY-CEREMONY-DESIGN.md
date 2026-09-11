# EA-4E.65 Non-Live Request-Scoped Activation-Only Ceremony Design

## Objective

Qualify one explicit application entrypoint that proves the request-scoped
production-activation transition without dispatching a receiver or invoking a
model. This phase is non-live and uses fake executors only.

## Frozen Boundary

```text
explicit activation-only request
-> normal admission and recovery checks
-> structural credential preflight
-> exact existing binding lookup
-> execution-authority and activation validation
-> exact activation-authorization claim
-> durable request-scoped activation entry and consume
-> skip governed action dispatch
-> activation and binding teardown
-> ceremony completion audit
-> return
```

The activation-only entrypoint must never call the governed action. The normal
submit entrypoint must retain its existing behavior. Invalid, stale, expired,
mismatched, replayed, or incomplete inputs fail closed through the existing
validators and durable store.

## Required Proof

- activation authorization progresses from `ISSUED` to `CLAIMED` to `CONSUMED`;
- production activation entered and exited events are durable;
- ceremony reaches `COMPLETED`;
- the exact binding is torn down;
- recovery state is clean;
- fake executor call count remains zero;
- the existing normal submit path still invokes its fake executor once;
- no process, model, network, browser, GPU, or ComfyUI capability is used.

## Governance

```ini
PHASE=EA-4E.65
MODE=NONLIVE_FAKE_ONLY
REAL_ACTIVATION_AUTHORIZATION_USE=NO
REAL_RECEIVER_EXECUTION=NO
MODEL_INVOCATION=NO
COMMIT=NO
PUSH=NO
```
