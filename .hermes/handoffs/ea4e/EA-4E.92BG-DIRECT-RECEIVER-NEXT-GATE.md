# EA-4E.92BG Direct Receiver Next-Gate Review

## Scope And Baseline

Non-live review at synchronized source commit
`5223ddeae14ca822811aeb58898e01b68b00cfc0`. No receiver, model,
provider request, GPU, ComfyUI, production activation, or native parser worker
was started. This review does not spend any prior one-shot authority.

## Current Path

EA-4E.92BF corrected false-success result classification in the Kilo and
OpenCode adapters. The direct adapter code can start a receiver process;
`kilo_live_binding.py` and `opencode_live_binding.py` each validate production
activation before execution. The inspected source does not itself establish a
qualified, capture-only governed route for a fresh receiver proof.

EA-4E.92A explicitly forbids using `OpenCodeLiveBindingHarness` for the
prospective raw-capture replay because it exercises the full production
activation path. It requires exact current source/binary/config/model identity,
one task, at most one process start, no retry/fallback, durable raw stream and
lineage capture, observed or enforceable model-call accounting, cleanup, and
offline replay. The historical EA4 missing capture remains missing.

EA-4E.92BE confirmed current installed binary hashes against source pins, but
the OpenCode config inspection did not establish CPU-only model behavior.
Kilo uses a cloud model, so a real call would also cross a provider/network
boundary. Neither fact grants a model-call budget.

## Disposition

`CURRENT_LIVE_RECEIVER_QUALIFICATION=HOLD`

`PRODUCTION_ACTIVATION=NOT_AUTHORIZED`

`EA92S_EXACT_MAPPED_BYTE_INVARIANT=REJECT_ON_AVAILABLE_EVIDENCE`

The smallest next **non-live engineering** slice is to specify and qualify a
capture-only entry point that still requires real invocation authority but
cannot perform production activation. Its fake-only tests must prove denial of
missing/wrong authority, wrong receiver or source identity, duplicate starts,
retry/fallback, over-budget calls, incomplete stream capture, and uncertain
cleanup. The entry point must not synthesize a historical EA4 capture.

Only after that path and its source closure are committed and requalified may
a separate exact live packet bind the receiver, executable bytes, source
commit, model/provider, task bytes/hash, process and model-call limits,
network/GPU policy, audit/capture destination, cancellation, cleanup, and
one-shot accounting. A general continuation request is not that packet.
