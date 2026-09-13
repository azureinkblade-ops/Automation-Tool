# EA-4E.67X Bounded Process Qualification Design

Baseline: c91c3828bb742eb77cea8edb058d665d6e1d1442.
Design-only boundary: no executable launch, guard change or production change.
The existing durability envelope is not expanded or reused implicitly.

## Two independent envelopes

Worker envelope: existing deterministic local_worker_stub.py, coordinator and
local worker tests. Allow only exact interpreter/helper paths and hashes,
explicit fresh temporary SQLite registry paths, enumerated fault flags and
canonical single-line request input. Missing-executable tests need a distinct
non-launch denial path preserving ProcessSpawnError semantics, not an arbitrary
path exception. Select exact node IDs, not whole modules or class names.

Pipe envelope: replace test Python -c snippets with a dedicated frozen helper
whose enumerated modes reproduce stdout/stderr, overflow, delay, malformed
output, reader finalization and cancellation behavior. No arbitrary -c, -m,
shell, model or installed receiver launch permission. Do not claim fake pipe
tests prove genuine OS stream handling.

## Admission and containment requirements

- Revalidate interpreter/helper bytes before every launch, fail closed on drift.
- Exact node set, per-node argv/options and process budget must be frozen from
  collection and source review before any admitted launch. Budget is NOT YET SET;
  29 blocked nodes does not imply 29 processes or exhaustive OS inventory.
- Explicit resolved basetemp; helper writes only admitted temporary state.
  Reject traversal, URI escape, symlink/reparse escape and live AppData paths.
- Credential-free environment allowlist; no ambient PATH/site/plugin/provider
  configuration. Helpers must install child process/network/filesystem denial
  before importing work-capable code. Parent Python guard alone is insufficient.
- Preserve production shell=False, UTF-8 I/O, timeout, creation options and
  synchronous process ownership semantics; do not alter production behavior to
  match a simplified admission wrapper.
- Track only owned child handles; bounded terminate/kill/wait and close readers
  on timeout, cancellation, exception and pytest shutdown. Verify no child alive.
- Record admitted/denied attempts, per-node command identity, exit/timeout,
  output hashes and cleanup. Any unexpected admission or denial fails the gate.
- Frozen helper LF bytes via targeted attributes if needed. The observed hashes
  below are current checkout bytes, not export-portable authority by themselves.
- Negative prelaunch tests must cover wrong executable/helper hash, extra argv,
  unsafe cwd/state, inherited credential, unauthorized node, exhausted budget.
  Separate real helper qualification from strict fake broad tests and report
  both raw results. An exclusion is never a pass or an expected failure.

## Observed identities / dependencies

Python SHA256: 0a864203aee170314ece97beaad6e50e226e76f0a3d73380a93ec472ed74f040.
local_worker_stub.py: 7cd30f1eefdd9d43e2d9934e32a09a8e93cf2ebc08af2be440ed6b3f72a12d14.
local_worker_process_control.py: 252c312661392cd5128fe51e099b98c3b24272abeacef5dfa61d8378afb8e0ed.
Worker process test module: 68ced0626a70192aec9e1868eaa97828328510eba28b96292e2895d619fdf62e.
Coordinator probe test module: d00a180b2472838d431c3291f12c151125c4413bdd56604899a1f104a8cea036.
OpenCode adapter test module: ec0d28da59b44d91deb29e69fe51b1e93e172d48434c1a442b95cf6db3b4c55b.

## Missing replay evidence: OPEN

The exact run-d1eca109.stdout.jsonl capture is absent at its required path;
no repository JSONL fixture was found. Historical EA-4E.4 notes contain only
normalized result text. Do not manufacture that as captured live JSONL.
Recover original evidence with provenance, sanitize/review and freeze exact
fixture bytes, or explicitly retain this historical proof as unavailable.
Synthetic parser tests already exist and do not replace captured-live proof.
No replay test or historical evidence was removed, skipped or rewritten.

## Progression

Next non-live checkpoint: implement one worker envelope and its negative tests,
freeze exact node/launch inventory and budget, prove clean-export reproducibility.
Only then execute bounded non-model helper qualification under the reviewed
envelope. Pipe envelope is a subsequent isolated checkpoint. Missing installed
binary qualification remains separate. Do not activate production or invoke
receivers/models as part of helper qualification.

PRODUCTION_READY=NO
BROAD_SUCCESSOR_GATE=HOLD
PROCESS_ENVELOPE_IMPLEMENTED=NO
PROCESS_LAUNCH_AUTHORITY_FROM_THIS_DESIGN=NO
LIVE_RECEIVER_MODEL_AUTHORITY=NO
