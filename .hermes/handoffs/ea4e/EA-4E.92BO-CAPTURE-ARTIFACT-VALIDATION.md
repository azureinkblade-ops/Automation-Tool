# EA-4E.92BO Capture Artifact Validation

Parent: `ae6978da2e7aa882d79d6a213fdc7079e67963a9`.
Non-live implementation slice of EA92BN. No real authority was issued or
consumed; no receiver, model, provider, network, GPU, ComfyUI, or native
worker was invoked.

`tools/hermes_core/capture_qualification_authority.py` validates the exact
v1 field set, canonical UTF-8 JSON bytes, duplicate-key exclusion, field
types, distinct identities, lower-case hashes, UTC-second validity window,
one-process-start limit, and the OpenCode-only receiver. It compares current
task bytes and runtime identities without claiming that comparison is
execution admission. Direct dataclass construction also validates; malformed
objects cannot bypass the parser by using the constructor. The module has no
SQLite, process, adapter, provider, network, or production-activation import.

Guarded focused validation: 32 passed. Guarded combined validation plus
EA92BH fake capture admission and the two existing production invocation
authorization suites: 125 passed. Filesystem tripwire events: 0. Fake-only
process tripwire events: 0. The same combined gate reran against files with
no unstaged diff after exact staging: 125 passed, zero guard events. No
inherited broad-suite failure classification is updated by this narrow run.
Committed-tree verification remains required before accepting the checkpoint.

This does **not** implement the separate capture issuer, trusted operator
approval, durable issue/claim store and anchor, cancellation/revocation,
coordinator, provider-call accounting, or live target binding. The next
non-live slice is isolated durable issue/consume with temporary stores and
fault/concurrency tests. EA92A prospective capture and EA92S exact mapped-byte
proof remain HOLD; historical EA4 capture remains missing. No live packet is
authorized by this implementation.
