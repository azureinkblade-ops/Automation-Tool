# EA-4E.92MN app local-host inspection boundary

Status: NON-LIVE CANDIDATE / PRODUCTION HOLD.
Parent: `e72260023764376c6676b56325f1d933b5808874`.
Dependencies: accepted 92MK local trust decision, 92ML context gate, 92MM
read-only account and durable-store observers.

`app.py` now exposes explicit `configure_local_container_app_host` and
`inspect_local_container_app_host` functions. The context is absent and
disabled by default. Configuration without `enabled=True` still denies.
Inspection calls only the read-only 92MM observer adapter and returns a
context decision. The application main path does not call either function.
No receiver, issuer, activation, or Docker action is reachable from this
inspection boundary.

Affected app, token, durable-context, and three-agent fake-chain regression:
52 passed, 0 failed.

Dedicated and adjacent focused tests: 30 passed, 0 failed, one inherited
`app.py` invalid-escape SyntaxWarning. The tests use a fake account reader
and fake store, and explicitly check disabled-by-default, no startup hook,
one enabled read, and stale-request denial. This is not real app-host or
model qualification. The configured governing commit is still an expected
value, not an independent loaded-byte measurement. Strict 92AT remains
REJECT/HOLD. Protected issuer installation and action-specific live agent
qualification remain open; production activation is not authorized.
