# EA-4E.92GQ Capture-Only OpenCode Entry Point Contract

Status: NON-LIVE DESIGN / CONTRACT. Baseline `663fd9c47834d97fd96f6c338c6bb9c5c47b823f`.
Date: 2026-10-10 (America/Phoenix). Authorized by David's "yes" to a separate
non-live packet. No live receiver, model, network, GPU or production activation.

## Why

EA92A forbids `OpenCodeLiveBindingHarness` for the prospective capture; EA92BG
found no qualified capture-only route; one CLI task can make several internal
provider calls; the bound model `ollama/qwen3:14b` is not proven CPU-only;
receiver-generated request bytes and auxiliary calls are unproven; the capture
issuer and v2 schema were unfrozen. This contract specifies a route that
addresses the first, second and last of these in code and records the rest as
explicit, uncleared prerequisites.

## Contract

1. **Authority without activation.** The entry consumes a
   `hermes.capture-qualification-authorization/v1` artifact (EA92BN) that was
   already persisted `ISSUED` by an external issuer. It never calls
   `persist_issued`, never builds `ProductionActivation`, never imports the live
   binding harness, adapter launcher, subprocess or any network module.
2. **Default disabled.** Construction requires `enabled is True`; any other value
   (including truthy strings/ints) denies. No environment variable or app
   wiring exists. Not referenced from `app.py` or any other tool module.
3. **Trusted issuer identity.** The entry is pinned to a `trusted_issuer_id` and
   needs an injected `issuer_verifier(artifact, issue_request_hash)` returning
   exactly that identity. With no verifier it denies (`TRUSTED_ISSUER_UNBOUND`).
   The only verifier available in this tree is a test fake; the manifest records
   `issuer_verification=FAKE_VERIFIER_NONLIVE`. The real signing service design
   (EA92BR) remains unselected.
4. **Admission order.** enabled -> verifier -> issuer match -> run directory free
   -> store state is ISSUED, not cancelled/revoked -> `store.claim` (identity,
   task hash, window, atomic one-shot) -> only then create the run directory and
   call the receiver exactly once. Every earlier denial consumes nothing. After
   the claim nothing refunds credit, including receiver crash, timeout, upstream
   failure or manifest failure.
5. **Exactly one provider call.** The receiver is handed a `ProviderBoundary` it
   must route provider traffic through. The boundary frozen scope is
   `POST /v1/chat/completions`, JSON with unique keys, `model == bound request
   model`, `stream == true`, <= 64 KiB, and a message containing the task text.
   The first in-scope call durably reserves a budget marker (exclusive create)
   before any upstream byte; a second in-scope call is `SECOND_CALL`. Any other
   call is auxiliary (`AUXILIARY_ROUTE`, `AUXILIARY_NON_TASK`, `INVALID_REQUEST`).
   Every denial is journaled, is never forwarded, terminates the receiver once
   (fail-closed), and permanently marks the capture `FAILED_CLOSED` even if the
   receiver swallows the denial. A capture is `COMPLETE` only with exactly one
   forwarded call, zero denied/auxiliary calls, one observed process start,
   exit 0, no timeout, confirmed cleanup, complete streams, zero child processes.
   A failed capture raises `CaptureFailedClosed` carrying the retained evidence.
6. **Durable capture.** Under `run-<sha256(run_id)[:32]>/`, exclusive-create +
   fsync, never overwrite: `authorization.json`, `request-1.bin`,
   `response-1.bin`, `stdout.bin`, `stderr.bin`, `call-reserved.marker`, then the
   sealed `manifest.json` last. An existing run directory denies.
7. **Frozen v2 manifest** `hermes.opencode-capture-manifest/v2`: 46 fixed fields,
   fingerprint `1b72dffd0a0ce71585315b1ea40762a0479911552fb40475884f1a1f49c2947f`.
   Labels are enforced by the validator: `CAPTURE_CLASS=FRESH_CURRENT_QUALIFICATION`,
   `HISTORICAL_CAPTURE=NO`, `execution_origin=FAKE_INJECTED_NONLIVE`,
   `acceptance_eligible=NO`, `gpu_policy_status=UNRESOLVED_PREREQUISITE`,
   `cpu_only_proven=NO`, and the five unresolved prerequisites. Schema freeze is
   not target-artifact freeze. The v1 BK verifier and the historical EA4 replay
   test are untouched; nothing is reconstructed or relabeled.
8. **Model binding / GPU.** The binding is carried only as the artifact's
   `model_binding_id`; no binding, config, provider option or device policy is
   changed. The CPU-only question is an unresolved prerequisite: the code cannot
   mark it resolved, so a manifest from this code is never acceptance evidence.

## Known limits (a fake cannot prove these)

- The boundary governs only the cooperative path. A receiver that opens its own
  socket bypasses it; real enforcement needs OS/network egress containment
  (`EGRESS_CONTAINMENT_UNATTESTED`).
- Auxiliary-call classification is heuristic (route/model/stream/task-text). If
  the installed receiver issues a title or other call first, it is denied and the
  capture fails closed rather than being classified correctly.
- Receiver-generated request bytes are unknown; the boundary records, not predicts,
  them (`RECEIVER_REQUEST_BYTES_UNPROVEN`). Response SSE completeness (EA92BV)
  and offline replay of a v2 capture are not composed here.
- Process accounting (pid, exit, cleanup, children) is reported by an injected
  port; a real implementation needs independently observed Windows process/job
  accounting.
- Issuer verification, process launcher and egress/CPU containment have no real
  implementation. A later separate exact live packet is required.