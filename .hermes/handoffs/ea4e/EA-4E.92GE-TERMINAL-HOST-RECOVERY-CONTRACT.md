# EA-4E.92GE Terminal Host Recovery Contract

Status: NON-LIVE DESIGN / PRODUCTION HOST NOT AUTHORIZED
Baseline: `7481b36aed620145472ea0b03e3daaf8327548f0`
Date: 2026-10-09 (America/Phoenix)

## Source finding

Codex, Kilo, and OpenCode now have fake-only no-output ping composition.
`app.py` has no production call to `load_bound_agent_start()`, either terminal
composer, or `record_verified_result_and_delivery()`. The latter's existing
call sites are tests and historical live-proof scripts. Its atomic SQLite
transaction protects cancellation/revocation and result/mailbox uniqueness,
but `delivered_at` is supplied by the caller and no trusted clock checks
`lease.not_before <= now < lease.expires_at` at new-success commit time.
The read-only STARTED witness and authority/result transaction span two
separate SQLite stores; the adapter's terminal record is separate again.

## Narrow host contract for the no-output ping

1. Select the exact already-delivered task/lease/receipt and read the durable
   STARTED witness. Missing, UNKNOWN, FAILED, or divergent start denies;
   never send a replacement invocation during recovery.
2. Read the named adapter's durable terminal record, not an in-memory return
   value alone. Match one-send key, runtime, launch, delegation, process start,
   terminal outcome, and the accepted receipt. Treat its body as a candidate.
3. Select only committed `hermes.agent_ping_result/v1`; use the matching
   composer and independently validate the canonical ping in the result
   store. No generic or file-producing success is eligible by this path.
4. The trusted result store obtains UTC time inside the same write transaction
   that rechecks cancellation/revocation and persists a new SUCCEEDED result.
   New success requires `lease.not_before <= now < lease.expires_at` and a
   bounded, nonfuture completed time. Caller-supplied `delivered_at` cannot
   prove lease validity. The store should use an injectable trusted clock for
   isolated tests; production binding owns that clock and fails closed if it
   cannot read it. Existing exact result+delivery replay is read-only and
   may return after expiry without another send or mailbox message.
5. Result and originator mailbox message stay in the existing single SQLite
   transaction. After a crash, first read result by attempt: exact result
   returns its existing delivery, divergent result conflicts. If absent,
   re-read immutable start and durable adapter terminal records and repeat
   steps 2-4. Never infer success from a RECORDED launch or unpersisted
   adapter outcome. Originator claim/ACK is a separate resumable step.

## Required fake-only gate before app wiring

Use isolated real SQLite stores and a fixed injected clock. Test just-before,
equal-to, and after lease expiry; not-before; cancellation/revocation between
witness and transaction; missing/UNKNOWN/FAILED start; absent/divergent
adapter terminal; exact and conflicting result replay after restart; one
result, one mailbox message, and originator ACK after restart. Verify zero
new writes on every denial. Only then add a narrowly scoped production host
entrypoint with no automatic receiver invocation.

This contract does not authorize any real Codex/Kilo/OpenCode call, Docker
mutation, model, GPU, ComfyUI, or production activation. It is not a generic
file-output verification contract. Local Docker provenance remains a weaker,
explicitly named claim under the previously accepted trusted-admin model.

`THREE_AGENT_PING_COMPOSITION=PASS_FAKE_ONLY`
`TRUSTED_TERMINAL_TIME_GUARD=NOT_IMPLEMENTED`
`PRODUCTION_RESULT_HOST_WIRED=NO`
`LIVE_AGENT_CONNECTION=NO`
`PRODUCTION_READY=NO`
