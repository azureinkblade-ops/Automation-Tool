# EA-4E.92P Static Binary Inspection Qualification

Baseline: f258b8eec3efae825afe04705acdddf0bc8defbb.
Status: STAGED QUALIFIED / FINAL COMMITTED GATE REQUIRED / SDK COMPATIBILITY HOLD.
Qualification-owned read-only tooling, not production acquisition or authority.

## Three-File Scope

- tools/ea4e92p_static_binary_inspection.py
- tests/hermes_core/test_ea4e92p_static_binary_inspection.py
- This evidence file.

Inspector accepts a caller-owned fresh binary stream and independently expected
lowercase SHA-256. It reads at most 200,000,000 bytes plus one size-denial byte,
using chunks no larger than 1,048,576 bytes. It hashes the whole observed stream
before returning an immutable receipt. Retention is bounded to first offsets of
four fixed markers with cross-chunk overlap; no arbitrary searches or embedded
content dumps. Non-byte/oversized read responses, invalid bounds and identity
mismatch deny receipt; stream read errors propagate. Caller owns stream lifetime.
No filesystem discovery, writes, network, process execution or SDK import.

This tool is not a PE/Bun parser, source extractor, signature verifier or runtime
admission path. A receipt proves observed stream identity and marker locations,
not package attribution, trusted ownership, file immutability or effective calls.
Hashing an observed stream does not independently close TOCTOU containment.

## Actual Read-Only Binary Evidence

Path: C:\Users\David\AppData\Local\Hermes\node\node_modules\opencode-ai\bin\opencode.exe.
Observed complete length: 174182280 bytes.
Full observed SHA-256: 578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35.
One read-only file handle supplied to inspector; no receiver was launched.

First fixed-marker offsets (zero based):
- B:/~BUN/root: 61561238
- @ai-sdk/openai-compatible: 100494073
- openai-compatible-chat-language-model: absent exact marker
- stream_options: 99318809

Initial limited rg scan stopped after its first matching line and only showed
the Bun marker. It was not a complete absence test. Full bounded inspector
corrects that limitation and finds the SDK/stream option markers.

Separate read-only human inspection of 768 bytes starting at offset 99318681
found a compiled doStream routine constructing a transformed request body with
stream:!0 and optional include_usage, then a /chat/completions path. It includes
stream response handling. Window SHA-256:
c35e19065b197e038d343d85c7692419c33493c8bd3567be59f3dd6f66d41ab7.
No raw window is stored by the inspector. Interpretation: !0 is true in this
embedded JavaScript routine. The frozen v1 non-streaming restriction therefore
has a concrete embedded implementation risk, not only a source-snapshot hint.

The bounded window does not establish owning module/package, source-map lineage,
or selection of this routine by the effective governed receiver configuration.
No request was executed/captured. SDK provenance and runtime compatibility remain
HOLD; do not claim package version or effective behavior from marker adjacency.

## Verification

18 new tests cover cross-chunk markers, first occurrence/order, absent/empty
streams, exact/over size limits, strict bounds/expected hash, invalid responses
and read failure. Working inspector/binding/composition set: 153 passed, 0 failed,
zero process/filesystem tripwire events.

Staged source tree: 72c82c8f48ff991858573c7642e1ffd4b45d6a94.
Retained .ea4e92p-index-a export includes tools/tests and declared EA92I fixture
design dependencies. Inspector plus EA92M/J/C/D/F ladder: 205 passed, 0 failed,
zero process/filesystem tripwire events.

Interpreter: pinned .venv-stage2-v2 Python. pytest: -q -p no:cacheprovider,
fake-only/filesystem/report-host plugins; fresh retained basetemp for each run.
Final complete Hermes Core gate must use clean committed Git-backed checkout,
preserving the six separately governed OS-node exclusions and raw inherited
failure reporting. Do not use an archive for the .git/HEAD-dependent test.
No full-green or final full-gate result is asserted by this precommit artifact.

## Next Boundary

Tie the embedded routine to the qualified effective provider path through trusted
module/source/build mapping or a separately reviewed inert extraction harness.
Do not import receiver startup, run installers/builds or spend a live model call
to discover identity. If effective streaming is required, separately design a
bounded streaming contract or proven compatible non-streaming path; no automatic
schema relaxation, stream flag stripping or fabricated SSE adapter is authorized.

No production code/registry/authority changes, runtime config mutation, receiver/
model/provider invocation, listener, GPU/ComfyUI, downloads or deletion. Real
target/policy freeze and production readiness remain HOLD. Historical lineage
and Kilo runtime pins unchanged. Original live budget unconsumed.
