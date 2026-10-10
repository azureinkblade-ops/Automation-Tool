# EA-4E.92GO Production Result Host Boundary

Status: NON-LIVE SOURCE AUDIT / DESIGN ONLY
Baseline: `a14dc839d4260363d8f95bbf306521d3f874ebde`
Date: 2026-10-09 (America/Phoenix)

## Source Finding

The current `app.py` composition creates `ProductionAppRequestLifecycleOwner`
through `ProductionAppFactory`. That lifecycle owns one explicitly activated
`receiver-dispatch` request and its binding teardown. It does not own a
delegated task's terminal capture, result, or originator mailbox. Source
search found no production call site for `SQLiteAgentTerminalCaptureStore.capture`,
`return_captured_text_ping`, `return_codex_ping`, or
`return_bound_agent_ping`. The new three-agent ping path is therefore
qualified as a store-only fake path, not an app-connected agent pipeline.

## Required Host Contract

1. Name a separate delegated-result host and explicit trigger. Import,
   startup, unrelated app requests, and scheduled background scans must not
   invoke it implicitly. It receives an existing attempt ID, not a new task
   or authority-issue request.
2. Inject established authority, start, terminal-capture, Codex registry,
   and result stores. Refuse missing or mismatched dependencies. Do not
   bootstrap production stores as a side effect of recovery.
3. For Kilo/OpenCode, a trusted adapter owner must persist the terminal text
   capture immediately after a qualified process outcome and before claiming
   result completion. A process that ended without durable capture remains
   UNKNOWN after restart; no fabricated result.
4. For Codex, consume only the immutable, reverified registry terminal
   artifact with a valid observation time. The missing historical pin must
   not be substituted with an installed successor without exact separate
   binary and parser-contract qualification.
5. Recovery reads an existing result first, then the accepted receipt and
   durable STARTED witness. A new result must pass the live authority and
   lease checks in the same result/mailbox transaction. Exact replay must
   return the prior result and message even after later cancellation/expiry.
6. The host must expose explicit status: no terminal evidence, recovered
   terminal evidence, result committed, message available, and denied.
   Failure must not launch or retry an agent.

## Qualification Before Live Use

Fake-only host tests must cover all three agents, restart at every durable
boundary, cancellation and expiry races, duplicate triggers, divergent
terminal evidence, and one-message replay. Then separately qualify the
actual Codex successor binary and Kilo/OpenCode runtime bindings, process
and model invocation accounting, credentials, local-container provenance
profile, and one exact bounded live probe. The prior exact image-section
byte proof must not be claimed by the weaker local-container profile.

No production activation, real receiver/model invocation, Docker mutation,
GPU, or ComfyUI operation was performed in this audit.

`AGENT_STORE_PATHS=PASS_FAKE_ONLY`
`PRODUCTION_RESULT_HOST=NOT_IMPLEMENTED`
`LIVE_AGENT_HANDOFF=NOT_QUALIFIED`
`PRODUCTION_READY=NO`
