# EA-4E.92FU Synthetic Agent Ping Delivery

Status: FAKE-ONLY END-TO-END MAILBOX REGRESSION / LIVE HANDOFF HOLD
Baseline: `7867c5e533c95d8ff3b84530700afe2e728b0ad8`
Date: 2026-10-09 (America/Phoenix)

The new test covers each of Codex, Kilo, and OpenCode using synthetic
canonical tasks, leases, ACCEPTED receipts, and ping candidates. It first
passes the committed `hermes.agent_ping_result/v1` instance check, then
constructs a canonical terminal result and records the result plus originator
mailbox delivery through the existing SQLite store. A fresh store instance
retrieves the result; an exact replay returns the same result/delivery/message
identities; the originator claims and acknowledges the message after restart.
A forged ping fails validation before a result write.

This is a test-only composition. It constructs the result itself and does not
exercise a production call site, durable launch/start/cancellation recheck,
actual Kilo/OpenCode output, transport, or model. It does not establish that
the three agents are live-connected. The bounded fake-only ladder passed
312 tests and 29 subtests with no receiver, network, Docker, GPU, ComfyUI, or
production activation.

Next source work must place trusted schema/evidence validation behind a
production host boundary that re-reads durable authority and launch state,
then prove failure/recovery without duplicate sends. A real receiver call is
still separately authorized and cannot be inferred from this simulation.

`SYNTHETIC_ORIGINATOR_DELIVERY=PASS`
`PRODUCTION_RESULT_HOST_WIRED=NO`
`LIVE_KILO_OR_OPENCODE_HANDOFF=NO`
`PRODUCTION_READY=NO`
