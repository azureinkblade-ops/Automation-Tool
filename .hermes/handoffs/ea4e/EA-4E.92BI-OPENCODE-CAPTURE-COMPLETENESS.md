# EA-4E.92BI OpenCode Capture Completeness

## Boundary

Non-live correction from synchronized parent
`f0977f9f9f2f78757b9ecc4559166554096c0fd8`. Only the OpenCode adapter,
its tests, and this evidence changed. No receiver, model, provider endpoint,
GPU, ComfyUI, production activation, or native parser worker was invoked.

## Defect And Correction

`OpenCodeLiveProcess.poll()` retains at most 1 MiB of stdout and 128 KiB of
stderr, but previously passed only the first 256 KiB of stdout to the final
JSONL parser. `OpenCodeReceiverAdapter.execute()` also dropped the process
result's truncation and total-byte fields while reconstructing the result.
Consequently a text event from an incomplete stream could be marked valid.

The process controller now passes the full retained stdout to the parser.
The adapter preserves both streams' truncation and total-byte metadata and
requires neither stream to be truncated before a text result can be verified.
An injected fake process proves >256 KiB, below the 1 MiB retention limit,
reaches `final_output` without any subprocess. Fake adapter results prove
stdout or stderr truncation cannot verify successfully.

This does not imply the spool files are durable, immutable, complete when a
reader fails, or suitable as an authenticated replay artifact. A separate
capture owner, raw-byte hashes, lineage manifest, cleanup evidence, and
independent replay are still required before any live qualification claim.

## Verification

Pinned stage2-v2 Python with fake-only process, filesystem, and non-live report
host guards, using fresh basetemps:

- Three new process-free tests failed before the correction, with zero guard
  events.
- Process-free OpenCode adapter: 74 passed, 15 separately governed helper
  process cases deselected, zero guard events.
- Downstream OpenCode governance plus EA92BH/F fake capture/provider tests:
  282 passed, 15 separately governed helper cases deselected, zero guard events.
- Canonical full fake-only Hermes Core: 4,542 passed, 35 raw inherited
  failures, six established OS-process tests deselected, 104 subtests passed.
  All 35 failure identities match the 92BH report exactly. The fake-only guard
  denied 32 attempted helper starts; filesystem events were zero. The raw
  suite is not green. JUnit report `.pytest-ea4e92bi-full-a/result.xml`,
  SHA-256 `a21506f5e9b17babd2ffe6188706e9c7e954fee4656ec628334d28c8956bd2f8`.

Staged and committed-tree focused verification and checkpoint identity are
recorded in the paired Obsidian continuation note.

## Remaining Hold

EA92BH is acceptance-owned and fake-only. This correction does not create
a production capture-only entry point, qualify real provider-call containment,
establish CPU-only execution, recover the historical EA4 OpenCode capture, or
authorize a live receiver/model call. EA92S exact mapped-byte HOLD remains
separate and unchanged.
