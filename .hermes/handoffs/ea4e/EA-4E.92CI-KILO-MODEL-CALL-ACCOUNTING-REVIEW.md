# EA-4E.92CI Kilo model-call accounting review

Status: NON-LIVE REVIEW / LIVE ONE-MODEL-CALL CLAIM HOLD

Governing source: `63d8151b79914679f42f505b3342cb35f1b95637`.
No Kilo receiver, provider, model, GPU, or ComfyUI call was made in this review.

## Finding

`kilo_invocation_authorized_live.py` describes one adapter call as one model
invocation. Its result accounting assigns `model_invocation_count` from
`kilo_adapter_live_call_count` (or from the real executor call count). Those
are Hermes-side invocation counts, not independently observed upstream model
requests. The historical EA-4E.50A pilot reports one model invocation but
does not provide an independent provider-request counter. It does prove one
governed Kilo process, one adapter invocation, no Hermes retry, and a terminal
marker response under the then-pinned executable.

The current Kilo transport fixes one executable, model, agent profile, and
task message. It limits process runtime and, as of 92CH, captured stdout and
stderr bytes. `KiloOutputParser` extracts terminal text/error events; it
neither counts model requests nor stops the child before a second request.
The pinned executable is packaged as an opaque `kilo.exe` in the installed
extension. This review found no qualified argv, config, or Hermes-side
mechanism that enforces one upstream model request inside that process.

Therefore `one Kilo process` and `one adapter call` must not be presented as
proof of `one provider/model request`. A successful marker is not proof of
that count either.

## Live boundary

An exact one-provider-request pilot remains HOLD. Before such a pilot, choose
and qualify a mechanism that either prevents request #2 or independently
records the upstream request count. Candidate mechanisms require their own
review, including credential, transport, and sealed-contract impact:

1. A pinned, source-validated Kilo per-run step/request limit, if the
   installed version actually exposes one and its semantics cover provider
   retries. Fake transport tests must demonstrate the second request is
   denied before network activity.
2. A governed local provider gateway that allows at most one upstream
   request for the authorized attempt, records each attempted request, and
   refuses subsequent requests. Its credential and network authority must be
   separately qualified; it cannot be inserted silently into the current
   Kilo transport contract.

Post-hoc JSONL event counting alone is not an enforcement mechanism. A
one-process/60-second/4-MiB-stdout/128-KiB-stderr pilot could be proposed
only under a different, explicit authorization that accepts an *unknown*
internal model-call count. The prior consumed live authorization cannot be
reused or silently broadened.

The EA-4E.92S exact mapped-byte invariant remains REJECT and trusted native
creation remains HOLD. This Kilo review does not change either decision or
authorize production activation.
