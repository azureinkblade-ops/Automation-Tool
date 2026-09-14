# EA-4E.92K Core Impact Review and Target Hold

Result: CORE HASH DISCOVERY COMPLETE / FULL ROLL CLOSURE HOLD.
Baseline: 502e284ca9acbf852bc20cbb6201afbe568d090e.
Companion JSON records 13 current derivations, exact committed export hashes,
canonical helper locations, hash edges, cached names, current IDs and ten
additional reviewed source/test snapshots. It is NOT a complete deployment,
runtime import, fixture or authorization-store dependency freeze.

## Method and Verification

Read-only Python AST discovery follows local canonical-helper calls and records
compute_ea4e* and CURRENT_EA4E* dependencies. Manually traced EA6 constructor
dataflow: default router -> ReceiverRouter._qualified -> QUALIFIED_RECEIVERS.
The initial static direct-reference flag missed that class/constructor edge;
the manifest records the manual correction and analysis limitation.
No live-capable function was called to infer routing or activation readiness.

Committed export .ea4e92k-source-a contains tools/tests/.gitattributes from the
exact baseline, not working-copy newline hashes. Source byte hashes in JSON
come from that export. Tests test_ea4e67f_kilo762_successor.py and
test_ea4e67c_successor_candidate_contract_diff.py passed 6/6, zero process and
filesystem events, using pinned stage2-v2 Python and established fake-only,
filesystem/report-host guards, cacheprovider off, fresh retained basetemp.
test_current_contracts_match_frozen_candidate recomputes all 13 identities
against the recorded committed EXPECTED_IDS, not historical Kilo predecessor IDs.
Independent manifest check must verify hashes against the same retained export.
No full pytest rerun claimed for this evidence-only inventory.

## Confirmed Impact

EA6 canonical registry includes both receivers. EA7/8/11/14/17/18/21/22/26
also include receiver material directly. EA23 binds cached EA17/21/22 IDs;
EA28 and EA29 bind downstream contract IDs. All 13 are candidates for a roll
if OpenCode's registered model binding changes. No cycle in the observed graph.
Topological order is in JSON; numeric ordering is not a substitute for edges.

Cached CURRENT_EA4E17_ISSUANCE_CONTRACT_ID,
CURRENT_EA4E21_BINDING_CONTRACT_ID and CURRENT_EA4E22_INTEGRATION_CONTRACT_ID
live in kilo_successor_binding.py and are imported into invocation authorization.
Do not alter Kilo's executable, transport or model pins to repair shared caches.
However, an OpenCode roll changes shared authority/activation/binding IDs used
by Kilo. Its current request-scoped authority cannot be presumed reusable.
Retain old durable records; require new explicitly issued authority where needed.

Runtime comparison sources include activation authorization/ceremony and app
binding. production_deployment_composition currently imports the Kilo executor;
its existence alone is not qualification of an OpenCode gate deployment.
These sources still need an exact downstream/runtime/fixture closure review.

## Hard Boundary Before Roll

No real target manifest is frozen. EA92I/J golden values are explicitly fixtures.
The target must bind exact trusted runtime/config bytes, effective model/package,
gate/upstream endpoints, and reviewed gate/egress/CPU/cleanup policy artifacts.
These references and config bytes are not supplied by a pure hashing module.
Proposed IDs in JSON deliberately read UNRESOLVED_TARGET_BINDING_NOT_FROZEN;
they are status markers, never accepted SHA-256 identities or substitute values.
No actual current contract was replaced with the fixture's golden digest.

Next narrowly scoped phase: non-live target/deployment-composition design and
policy-artifact freeze. Identify trusted artifact ownership, byte acquisition,
TOCTOU protection, enforced egress, durable revocation, CPU-only qualification,
one-call/non-streaming SDK compatibility and owned cleanup requirements.
Design may proceed without deploying. Real config/firewall/listener/provider/
receiver/model changes remain a separately governed boundary. If policies cannot
be established, preserve HOLD rather than invent an ID or infer enforcement.
Then extend this core inventory into the full affected source/fixture closure,
derive proposed IDs from real reviewed material, and qualify a minimal atomic roll.

## Safety and Checkpoint Scope

Evidence-only JSON plus this review. No production/test source or registry edits,
runtime/config/credential mutation, authority issuance, receiver/model/provider
calls, production activation, GPU/ComfyUI, downloads or deletion.
Historical missing capture and raw inherited failures remain unchanged.
This inventory does not claim source-closure PASS or production readiness.
