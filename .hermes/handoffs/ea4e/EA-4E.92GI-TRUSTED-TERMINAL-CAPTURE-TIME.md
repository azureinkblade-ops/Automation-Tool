# EA-4E.92GI Trusted Terminal Capture Time

Status: NON-LIVE STORE HARDENING / ADAPTER HOST HOLD
Baseline: `f2087f41b9b9b3057fd66e47a3abea72f6440af0`
Date: 2026-10-09 (America/Phoenix)

The 92GH capture had no durable observation time, leaving a future host to
invent a terminal completion timestamp after restart. A new Kilo/OpenCode
capture now reads an aware UTC clock inside its authority-database write
transaction, requires time at or after the durable STARTED record and before
lease expiry, and stores `captured_at` under the capture checksum. Recovered
captures expose that original time. An exact capture replay after expiry
returns the original bytes and time; it neither changes the row nor sends
the receiver again. A divergent outcome still conflicts.

Fake-only tests use isolated real SQLite stores and fixed clocks, including
pre-start and expiry denials and exact post-expiry capture replay. The
focused capture suite passed 10 tests; the bounded cross-agent/start/result
ladder passed 245 tests and 26 subtests with zero failures.

The adapter host is not yet wired to write this capture after a real
terminal return. A crash before capture remains UNKNOWN. The result
transaction still separately checks lease time before any new SUCCEEDED
delivery. This is not a live agent connection or production activation.

`TEXT_CAPTURE_TRUSTED_TIME=PASS_FAKE_ONLY`
`TEXT_CAPTURE_EXACT_REPLAY=PASS_FAKE_ONLY`
`PRODUCTION_ADAPTER_HOST_WIRED=NO`
`PRODUCTION_READY=NO`
