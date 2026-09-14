# EA-4E.92J Pure Provider Binding Qualification

Parent: db50e7b02f126436c675ad7e07a4c735bcbeed3d.
Scope: tools/hermes_core/opencode_provider_binding.py,
tests/hermes_core/test_ea4e92j_provider_binding.py, this evidence.
Existing registry, runtime, credentials, stores and production integration unchanged.

## Implemented Boundary

Pure build/parse/supplied-evidence APIs for the frozen EA92I schema.
Exact recursive keys, constants and types; bounded integers; canonical literal
loopback URLs/ports; exact Windows absolute paths; lowercase SHA-256; no coercion.
JSON parsing rejects duplicate keys/nonfinite constants and invalid UTF-8/schema.
Device, dot/empty components, invalid Windows filename characters and alternate
path syntax are denied under the frozen Windows path rule. No path normalization.
Immutable return contains canonical bytes and their reproducible digest.
Supplied-evidence verification compares expected binding ID, executable/config
byte digests and exact four policy snapshots. No file discovery, clock, network,
process, authority, registry writes or enforcement capability is added.
Callers remain responsible for trusted file acquisition, expected ID ownership,
source/store identity, TOCTOU containment and actual policy enforcement.

## Acceptance Evidence

117 new tests; dedicated run 117 passed, zero process/filesystem events.
Working and independent staged predecessor ladder each 285 passed,
1 separately qualified OS node excluded, zero failures and zero guard events.
Golden digest a7bfd43b26e706c78ae43b0c8880ce80dae5d82b167e2fac666c3c49ea57ff37,
canonical length 1646; 35/35 leaf mutations change diagnostic preimage digest.
Tests cover golden/reordered roundtrip and immutable snapshot, strict schema,
type/path/URL/limit denials, parser denials and byte/policy/legacy-ID mismatch.
Hash sensitivity does not permit invalid material to become an admitted binding.

Source-only staged tree: e2644d93aadd958160957799613d21a5f8ebca23.
Retained export .ea4e92j-index-a includes tracked tools/tests/.gitattributes AND
the declared frozen fixture dependency:
.hermes/handoffs/ea4e/EA-4E.92I-VERSIONED-OPENCODE-BINDING-DESIGN.md.
That fixture is already committed at the parent; not an undeclared untracked input.
Pure API imports standard-library hashing/JSON/regex/PureWindowsPath/urlsplit
plus existing tools.hermes_core.hashing; urlsplit is parsing, not networking.

Commands: pinned stage2-v2 Python -m pytest -q -p no:cacheprovider,
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host; fresh retained basetemp; dedicated EA92J
test plus EA92F/D/C, EA56 accounting, EA32 durable authorization and EA33A
rollback test files; -k excludes only
test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent.
Independent committed ladder/full raw fake-only suite still required. Actual
results go to Obsidian without amending the source checkpoint.

## Not Claimed / Next Gates

No real binding minted from fixture data, current-ID roll, transitive reseal,
historical record migration, renewed authority or deployment approval.
No actual SDK request compatibility, persisted cancellation/revocation owner,
real egress enforcement, CPU-only execution or owned listener cleanup proven.
No receiver/model/provider calls, GPU/ComfyUI, config changes or file deletion.
EA92G provenance gap remains historical; EA92E deployment HOLD persists.
Next: exact committed dependency-impact inventory and reviewed roll closure,
after checkpoint verification and exact-SHA push approval. No bulk ID replacement.
Raw inherited broad failures remain visible, not normalized to full green.
