# EA-4E.92BP Durable Capture Store

Parent: `288f700bd92e6bade389476c5c6421d1a1e3e7e3`.
Non-live implementation of the isolated EA92BN persistence boundary. No
receiver, model, provider, network, GPU, ComfyUI, production activation, or
native worker was invoked.

`tools/hermes_core/capture_qualification_store.py` persists the full canonical
EA92BN artifact in its own SQLite table, not the production invocation table.
It requires an explicitly pinned store instance ID and generation plus a
separate external anchor. Issue IDs and authorization IDs are collision
checked; identical issue replay returns the existing record. Claim changes
the one start credit irreversibly to consumed in a SQLite immediate
transaction, then publishes the next anchor generation before returning
success. Cancellation and revocation are durable flags serialized by the
same transaction boundary and never refund a consumed credit. Missing,
rolled-back, mismatched, or interrupted anchor state denies reopen. A failed
or uncertain process start cannot refund a claim, but process start is not
implemented in this checkpoint.

An initializer review found that SQLite's connection context manager does
not close the connection on Windows; the new initializer explicitly closes
it after commit or error. No existing production store was modified.

Process-free temporary-store tests cover issue replay/conflict, exact task
and identity checks, restart, stale external pins, concurrent claim,
claim-versus-revocation race, post-claim cancellation, row/anchor tamper,
database rollback, interrupted issue/claim anchor publication, and missing
anchor refusal. Focused store run: 19 passed. Combined store/artifact/fake
capture/production authorization run: 144 passed. Both process and
filesystem tripwires recorded zero events. Staged and committed-tree reruns
are required before checkpoint acceptance. This is not a broad-suite green
claim.

The exact three-file staged set had no unstaged source diff; its combined
guarded rerun passed 144/144 with zero process/filesystem tripwire events.
Committed-tree verification remains required.

The store only persists supplied material; it does not verify an externally
approved operator, issue a real authorization, or supply a trusted live
store/anchor path. Its hashes detect inconsistency inside a trusted local
filesystem, not an adversary able to rewrite both database and anchor.
Actual issuer provenance, independently maintained epoch pin, capture-only
coordinator, provider one-call accounting, CPU/egress containment, current
target identities, and cleanup ownership remain unqualified. EA92A fresh
capture, historical EA4 replay, EA92S mapped-byte proof, and production
readiness remain HOLD. No one-shot live authority follows from this store.
