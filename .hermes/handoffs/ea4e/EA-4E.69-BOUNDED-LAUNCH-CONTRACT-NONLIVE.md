# EA-4E.69 - Bounded Launch Contract

Baseline: 69d2524023a8a265ca9dc774e5683a49c378e32f.

Scope: three new test-owned files: launcher, dedicated tests, this evidence. No existing production code, guards, fixture or protected WIP changes.

The supplied factory has no default real process implementation. Admission validates canonical original worker argv, executable/helper identity, environment, state and budgets. Bootstrap source hashes pin canonical LF source, deliberately tolerating Git CRLF checkout conversion; these are not raw-byte transport hashes. The original worker helper/interpreter retain admission's exact-byte pins.

Command wraps the canonical argv through the dedicated entrypoint with -B. Validation and source checks precede attempt accounting; the attempt is consumed before factory creation and never refunded for failure/ambiguity. Returned handles are immediately registered under the owned cleanup policy. Cleanup remains explicit and must be called by the future qualification harness in finally.

Seven dedicated tests plus the previous 69-test gate qualify source identities/tamper, ordering, copied environment, argv, budgets, creation failure and cleanup delegation with fake factories. No actual child is launched; no process exemption is enabled. Aggregate counters are in-memory per launcher and are not durable production authorization.

Next: freeze the complete test-owned launcher dependency closure and explicit process qualification envelope; prove real child guard installation, network/write denial and owned cleanup. Neither this helper nor its tests establish real process containment, full successor green or production readiness.
