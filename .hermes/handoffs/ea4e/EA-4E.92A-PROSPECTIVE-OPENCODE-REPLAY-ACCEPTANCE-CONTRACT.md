# EA-4E.92A Prospective OpenCode Replay Acceptance Contract

Design-only contract, version 1. Governing parent:
d9713d00a91e9b60ffedb37226cbe935c7f0d818.
No live invocation, production activation or production/test patch authorized
by this document. The separate EA92 one-shot packet supplies conditional live
authority; all of its remaining preflight gates still apply.

## Proof obligation and prospective closure

The current proof obligation is authentic, retained, replayable request/response
evidence from the currently qualified OpenCode receiver and model binding.
A fresh EA92 capture MAY satisfy this current obligation if every condition
below passes. It does NOT satisfy recovery or replay of the historical EA4 run.
Historical FAIL_MISSING_CAPTURE remains unchanged and visible in raw reports.
This distinction supersedes only the previously unresolved prospective
sufficiency question; no prior result, assertion or missing file is rewritten.

Current-capture PASS requires all of:
- Exact qualified receiver/runtime/transport/model identity verified from
  committed source and current local bytes/config, before and after execution.
- One authorized task, at most one receiving process start, no automatic retry
  or fallback. A process start consumes authority even if model execution fails.
- Actual bounded request/response capture, exit and cleanup evidence, with
  matching task, run, authorization and attempt lineage.
- Offline replay of the retained raw stdout by the committed production parser,
  independently verified from staged and committed artifacts.
- Exact response contract, zero unauthorized repository mutation and complete
  accounting within the authorized provider/network/process scope.

## Identity and task envelope

Receiver: opencode-cli-agent.
Current registry transport: 192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f.
Current registry model binding: cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371.
Committed executable: C:/Users/David/AppData/Local/hermes/node/node_modules/opencode-ai/bin/opencode.exe.
Committed executable SHA-256: 578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35.
Committed version: 1.18.11. These values must be rederived and checked at live
preflight; a design reference is not current runtime qualification.

Historical EA4 model-binding evidence names ollama/qwen3:14b with an older
binding ID. Do not infer the current provider/model from that old record.
Resolve the current binding and isolated configuration without exposing secrets.
If the exact current provider/model cannot be established, stop before start.
No model installation, credential refresh, fallback or runtime repair.
Any required GPU activity conflicts with the no-GPU packet and must stop;
do not silently alter model execution settings to avoid that boundary.

Task ID: ea4e92-current-replay-v1.
UTF-8 task payload, no terminal newline:
`Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files.`
Hash exact payload bytes with SHA-256 before execution. Parsed response must be
type text with text exactly EA4E92_OPENCODE_CURRENT_REPLAY_OK, permitting only
outer transport whitespace normalization already provided by the parser.
Task wording is not a security boundary: established tool/config policies must
independently deny unwanted operations.

## Capture and accounting

Create a fresh EA92 namespace, never the EA4 spool filename. Retain raw stdout
and stderr separately, request bytes, UTC start/end, executable/argv identity,
qualified config identity, source commit, transport/model IDs, task hash,
authorization identity, distinct run/attempt IDs, PID, exit/timeout information,
stream truncation/reader state and cleanup result.
Hash raw capture bytes and canonical metadata; explicitly label
CAPTURE_CLASS=FRESH_CURRENT_QUALIFICATION and HISTORICAL_CAPTURE=NO.
No capture redaction may masquerade as original bytes. Scan artifacts for
secrets before staging; if unsafe, retain privately and HOLD the checkpoint.
Never commit credential values, unrelated environment values or private paths
that are not needed to bind the evidence.

Record attempted start versus actual process creation separately. Model-call
count must come from observed provider events or a qualified enforceable
one-call transport contract. A CLI task may make multiple internal model calls;
process count or adapter-call count alone cannot prove the one-model-call limit.
If the existing route cannot enforce/account for that limit, HOLD before start.
If observations after start are uncertain, consume authority and HOLD; no retry.

Do not invoke OpenCodeLiveBindingHarness: its full production activation path
conflicts with EA92. Use only an already-qualified capture-only path that
satisfies the packet. Do not bypass required invocation authority to obtain it.
If that path requires production code changes or production authorization
issuance, stop for a separate non-live design/implementation phase.

## Replay, regression and readiness reporting

Fresh replay is a new test/evidence obligation, not a path substitution inside
test_offline_replay_captured_live_jsonl. That original assertion remains intact.
Verify artifact hashes before replay. Test-only fresh fixtures, if necessary,
must reject hash tampering, wrong task/binding identity, empty/malformed stdout,
wrong response, incomplete accounting and failed cleanup.
Synthetic negative fixtures must be clearly labeled, never presented as live.
Run eight portable parser tests, fresh replay/negatives, relevant adapter/binding
and cleanup/accounting tests, the EA90 durability gate and the established
predecessor/sealed-aligned/broad gates under their exact scoped envelopes.
Keep raw inherited failures and separately qualified process cases visible.
Require zero new regressions and no untracked source dependency.

Report independently:
HISTORICAL_EA4_REPLAY=FAIL_MISSING_CAPTURE_UNCHANGED;
CURRENT_OPENCODE_CAPTURE=PASS/HOLD;
CURRENT_OPENCODE_REPLAY=PASS/HOLD;
RAW_BROAD_GATE=actual counts;
SEPARATE_BOUNDED_GATES=actual counts;
PRODUCTION_READINESS=reviewed disposition, never inferred from a text response.

Only the current replay-evidence requirement may be prospectively closed.
Reinventory production activation, receiver authority, provider/model identity,
durability, crash recovery, cleanup and invocation accounting at the exact source
commit before claiming readiness. Unknown prerequisites remain OPEN, not zero.
No production activation, Kilo, GPU, ComfyUI or general live execution follows
automatically from prospective capture PASS.

## Checkpoint boundary

This design introduces no runtime capability or test weakening. One narrow
design checkpoint may be committed; normal push requires the resulting exact
SHA approval. A later live preflight must reference the synchronized design
checkpoint and pass every EA92 packet condition. No process/model budget was
consumed while defining this contract.
