# EA-4E.92BK Fresh Capture Offline Replay

## Boundary

Non-live, acceptance-owned verifier from synchronized parent
`3206f930da16baab4b6919c5a3b2e4ff0a859539`. No receiver, model,
provider/network, GPU, ComfyUI, production activation, or native parser
worker was invoked. Tests construct clearly synthetic captures in temp dirs.
The missing historical EA4 raw capture remains missing; it is not replaced.

## Contract

`tools/ea4e92bk_fresh_capture_replay.py` only reads a capture directory. It
requires an independently supplied manifest SHA-256, exact current source/
binary/config/transport/model/run/attempt/authorization identities, and the
frozen EA92A task and response. It checks a canonical metadata hash, rejects
duplicate JSON keys, hashes the retained request/stdout/stderr bytes, checks
bounded lengths and completion/exit/cleanup fields, then replays raw stdout
through the committed `OpenCodeReceiverAdapter.parse_output()` parser. The
fresh capture class is explicit and historical capture is forbidden.

The manifest's process-start and provider-call counts are **claims**. This
verifier cannot observe a provider request, attest model execution, prove
CPU-only behavior, authenticate a manifest digest supplied by the same
untrusted producer, or turn synthetic data into a live qualification. The
trusted digest must come through a separately governed evidence channel.
This module writes no capture files and starts no processes.

## Verification

- Dedicated synthetic verifier: 28 passed, zero guard events after fixture
  correction and independent-digest tightening.
- Offline replay/parser plus fake capture/provider ladder: 116 passed, one
  historical EA4 capture replay explicitly deselected, zero guard events.
- Complete guarded Hermes Core: 4,572 passed / 35 raw inherited failures /
  six established OS-process tests deselected / 104 subtests passed. All 35
  failure identities exactly match EA92BJ, with no new failures. Fake-only
  process guard denied 32 helper starts; filesystem guard events were zero.
  The raw suite is not green. JUnit `.pytest-ea4e92bk-full-a/result.xml`,
  SHA-256 `75995656596ee170f0cee452d56d30148ec9aff259570f27397e78a9a0e36342`.

The first dedicated run had one fixture failure: its tamper test edited the
pre-hash dictionary instead of the saved manifest. The test fixture was
corrected; production behavior was not weakened.

## Remaining Hold

No fresh real OpenCode capture exists yet. The capture-only live path,
independent provider-call accounting and egress containment, CPU-only model
proof or separate GPU authority, durable evidence owner, exact one-shot live
authorization, and cleanup observation remain OPEN. EA92S exact mapped-byte
invariant remains REJECT/HOLD. No production readiness claim follows.
