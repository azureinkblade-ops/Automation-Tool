# EA-4E.92I Dependency-Aware Binding Roll Plan

Status: DESIGN REVIEWED / PLAN FROZEN / NO ROLL OR RESEAL AUTHORIZED.
Baseline: e74c1518cf38d045824fee89df16cd088dce146c.
Companion: EA-4E.92I-VERSIONED-OPENCODE-BINDING-DESIGN.md.

## Discovered Surface, Not a Frozen Closure

Direct ID owners: receiver_router.QUALIFIED_RECEIVERS,
production_executor_binding.QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
production_credential_preflight.OPENCODE_MODEL_BINDING_ID.
Historical qualification documents and literal-ID tests reference the old ID.
Do not bulk-replace them; distinguish current acceptance from historical evidence.

Observed computed edges include receiver router -> authority/coordinator,
production issuance -> router/authority/activation/execution,
production invocation authorization -> execution/issuance/binding/integration,
governed production runtime -> execution/integration/binding/invocation and
qualified receiver identities. Activation authorization and ceremony compare
the selected model-binding ID with the registry and carry it in artifacts.
These are inspected edges, not the claim of a complete topology or file count.

Use the existing EA26R downstream rebind/reseal inventory as a discovery aid,
not authority to reuse its historical set unchanged. Inspect current compute_*
and payload functions, imported frozen IDs and committed fixtures transitively.
Pure computation/imports must run under the established non-live guards; any
collection demanding a real process/model path stops and is separately scoped.

## Sequential Gates

1. Review/freeze the schema, serializer, strict policy and golden fixture.
   Contract freeze does not qualify actual SDK compatibility. Resolve whether
   SDK requests meet non-streaming one-call scope before deployment admission;
   otherwise HOLD or separately review a schema change. Pure implementation
   can proceed without live SDK activity. No real ID is minted from fixtures.
2. Implement a pure contract module and isolated acceptance tests. No runtime
   discovery, issuance, registry modification, listener or network capability.
   Verify source-only staged and committed exports before calling it qualified.
3. Build an explicit transitive dependency manifest at an exact committed baseline.
   Each entry: path, ownership, preimage/compute function, dependencies, old ID,
   expected new ID, affected schema/fixture, exact file SHA and test command.
   Classify historical records, current sealed contracts and dynamically minted
   request artifacts separately. Undeclared imports or hash edges block closure.
4. Review a minimal atomic integration/roll patch. Only current contracts roll.
   Where semantics change, version the schema, not just its displayed hash.
   Topologically compute upstream IDs before downstream reseal. Reject cycles.
   Include registry owners and every changed current consumer in one reproducible
   source closure; do not bless a mixed old/new chain or broad string replacement.
5. Run dedicated pure-contract and affected predecessor suites, EA92C-F ladders,
   stale-ID negative tests, and the full raw fake-only Hermes Core gate.
   Compare actual failed node identities against the last committed baseline.
   Keep 35 inherited failures visible and six separately qualified OS exclusions.
   Fix only demonstrated scoped regressions; no skip/xfail normalization.
6. Independent staged and committed verification must reproduce exact IDs and
   tests without untracked dependencies. Check parent, allowlisted paths/hunks,
   clean tracked state and unchanged unrelated WIP. Preserve retained exports.
   Only then review a narrow commit and request exact-SHA normal push approval.
7. Separately freeze actual deployment manifests, config bytes, runtime/policy
   hashes, listener ownership, egress enforcement, CPU-only guarantee, trusted
   revocation owner, request lineage, real accounting and owned cleanup.
   Do not infer enforcement from offline policy labels or simulated ledger events.
8. Only a fresh explicit one-shot live packet can authorize runtime/config changes,
   real listener/provider/receiver/model activity or production activation.

## Historical and Durable-State Safety

Retain original IDs, signed/hash-bound records, source commits, cancellations,
revocations, consumed counters and failed/partial captures. No retroactive edits
or rewritten IDs in durable authorization stores; that would break lineage.
Historical readers may validate old artifacts under their historical contract;
new admission must reject stale bindings. No implicit migration or reissuance.
New authority needs a separately authorized issuance ceremony against current
source/store ID/epoch and the newly qualified registry. No automatic replay.

Rollback restores only a separately reviewed source/composition version. It
must never roll back a consumed ledger/store/anchor to resurrect a slot.
Do not remove evidence or temporary directories to obtain a clean report.
No app.py edits until a distinct thin-wiring ownership handoff is established.
Kilo/image pipeline/Studio Bible/Regional Hand Repair remain independent.

## Exit Language

EA92I contract/plan are FROZEN; not implementation PASS or production ready.
EA92G hash-provenance gap remains historical even if a new contract is qualified.
EA92E deployment HOLD remains until its separate enforced composition is proven.
No existing live authorization budget is consumed or expanded by this design.
