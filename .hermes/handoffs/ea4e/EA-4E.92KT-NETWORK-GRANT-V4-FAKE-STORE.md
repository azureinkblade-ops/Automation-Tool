# EA-4E.92KT network-grant v4 fake-store qualification

Status: NON-LIVE / FAKE-ONLY IMPLEMENTATION QUALIFIED. Not an issuer or
production activation authorization.

Baseline: `62bc5c7d051b61b473bc2ec61687e63afd94b0ed`.

## Implemented boundary

- New v4 SQLite schema, store identity/epoch, generation journal, and
  append-only per-generation anchors. V3 is neither migrated nor accepted.
- Each grant row persists only ID, exact canonical v2 artifact text, and
  current state. Row/table digest binds every persisted byte and state.
- Open and every transition validate exact table definitions, reject added
  triggers/views/DDL, verify the journal and every anchor, parse all artifacts,
  match embedded row/store identity, and reject duplicate nonce,
  attempt/action, and network target.
- Fake issue requires the existing v2 byte verifier plus caller-provided
  expectations. The artifact is cloned before validation and persistence.
- Fake claim consumes ISSUED exactly once before any hypothetical mutation;
  revoke applies only before claim; CLAIMED can become UNCERTAIN. Expiry is
  checked at fake claim using a caller-supplied test clock.
- A database commit without its matching anchor fails closed on reopen.
  There is no automatic repair or replay. No Docker or agent execution path
  exists in these files.

## Qualification

- Focused v4/v2/identity suite: 48 passed, 0 failed.
- Adjacent EA-4E.92I/J/K and HJ/HV/HY fake-only suite: 539 passed, 0 failed.
- Tested fresh-process reopen, issue/claim/revoke/uncertain replay denial,
  duplicate identities, external expectation mismatch, expiration, stale
  handle, real v3 cross-open denial, byte/state/schema/anchor tamper, missing
  anchor, database rollback, and injected post-commit anchor gap.
- Source capability scan found no subprocess, receiver/model, Docker API,
  network, GPU, MCP, or ComfyUI invocation in the new store.

## Still open

The store is fake-only and its caller-supplied expectations and clock are not
trusted production inputs. The protected independent issuer, UAC/operator
witness, installed binary identity and ACL/reparse closure, protected anchor
placement, cancellation/current-authority source, real Docker mutation owner,
and separately bounded Kilo/OpenCode receiver/model qualification remain
unimplemented or unqualified. Fake tests do not establish production readiness.

No UAC, Docker mutation, Kilo/OpenCode/model call, GPU, ComfyUI, or production
activation occurred. Production remains HOLD.
