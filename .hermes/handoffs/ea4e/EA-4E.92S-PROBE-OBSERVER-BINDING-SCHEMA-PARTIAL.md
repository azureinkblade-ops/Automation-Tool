# EA-4E.92S Probe Observer-Binding Schema Partial

Date: 2026-09-21
Synchronized baseline: `0c1c8be8d7889e0b2575e63ac31223f138eac33e`
Status: IMPLEMENTED / WORKING-TREE QUALIFIED / UNSTAGED / UNCOMMITTED

## Scope

This non-live slice rolls the durable probe-evidence store from schema v1 to
v2 so NQ-12 can persist the previously qualified observer-resource binding.
The production change is limited to
`tools/ea4e92s_probe_evidence_store.py`; focused coverage is isolated in
`tests/hermes_core/test_ea4e92s_probe_observer_binding_store.py`.

Schema v2 stores canonical observer-binding JSON and its SHA256 beside the
probe start. The store validates the exact watcher UUID, three distinct opaque
resource-token hashes, PID/TID, process/thread creation identities, and binding
time against the durable probe window. Raw native handles are not stored.
Only a started NQ-12 record may acquire a binding. Exact replay is idempotent;
different replay conflicts; malformed, mismatched, out-of-window, missing, or
tampered bindings fail closed.

Opening an exact schema-v1 store performs one transactional migration that
adds nullable observer-binding columns and advances the metadata identity to
v2. Existing v1 records remain readable with no binding and therefore remain
ineligible for future native NQ-12 observation. Unknown/future schemas and
incomplete v2 layouts remain rejected.

## Review Corrections

The first focused run exposed a Windows rename failure caused by the new test
fixture using SQLite's transaction context manager without closing the
connection. The fixture now uses `contextlib.closing`, commits explicitly, and
the production connection-lifecycle contract was unchanged. Source review then
added fail-closed nullable-column parity checks so removing either binding JSON
or its checksum is detected. A hash-consistent but structurally malformed
binding is also rejected.

## Verification

- Focused store, migration, reconciliation and identity tests: 88 passed / 0
  failed; process tripwire 0; filesystem tripwire 0.
- Complete bounded EA-4E.92S suite: 630 passed / 0 failed; process tripwire 0;
  filesystem tripwire 0.
- Complete guarded Hermes Core: 4,243 passed / 35 inherited failures / 6
  deselected / 104 subtests passed. Exact comparison with the committed
  observer-identity baseline found 35 unchanged failure identities, 0 added
  and 0 missing. All 32 process attempts were denied; filesystem events were
  0. JUnit SHA256:
  `ab95e2a4d186935fc416a3a9f8c90aead9005d8e73dd61cb4cdf497f3811110c`.
- Production-source capability scan found no subprocess, shell, native DLL,
  process launch/resume, network, browser, receiver/model, GPU or ComfyUI
  capability.

The raw broad gate is not green because the 35 existing process-dependent
failures remain visible. This slice adds no failure identity and no live
capability.

## Boundary

No native watcher/provider is implemented or invoked. No process, receiver,
model, network, GPU or ComfyUI activity occurred. This checkpoint does not
qualify NQ-12 or native containment. The next boundary is exact three-file
staged-export qualification. Native provider implementation and every live
probe remain separately governed and unauthorized.

## Staged-Export Qualification

Exactly the production module, focused test module and this evidence file were
staged. The first frozen Git tree was
`77c18a0d45cb9a0e0ff99c005f0b58bae82e0ad2`; immutable archive
`.ea4e92s-binding-schema-index-a.zip` has SHA256
`95ec2c77623ac062d76a874322131165c94fb9cd90cbcb83c679006baaaf5cec`.
The exported tree passed the complete bounded EA-4E.92S suite: 630 passed / 0
failed, with process and filesystem tripwire counts both zero.

After evidence normalization, the frozen staged export again passed the same
630-test bounded suite with both tripwire counts zero.

State: OBSERVER-BINDING SCHEMA EXACT THREE-FILE CHECKPOINT STAGED / FINAL
STAGED-EXPORT QUALIFICATION PASS / NOT COMMITTED / NOT PUSHED / NATIVE
EXECUTION HOLD. Next boundary: local commit review. A native provider and every
live probe remain unauthorized.
