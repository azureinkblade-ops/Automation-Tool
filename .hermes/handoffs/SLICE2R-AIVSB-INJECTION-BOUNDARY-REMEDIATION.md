---
status: RECORDED
recorded: true
executed: true
implementation_authorized: true
implementation_verified_at_utc: 2026-07-28T17:50:23Z
implementation_verification: "PYTHONPATH=. python -m pytest tests/aivsb -q: 28 passed"
implementation_commit: 5eed6e1823bc398084e8a46998186771a5970347
handoff_id: SLICE2R-AIVSB-INJECTION-BOUNDARY-REMEDIATION
revision: 2026-07-27
depends_on_commits: ["2100123 (Slice 1)", "65fb588 (provenance)", "c9e39c5 (Slice 2 wiring)", "da090a9 (Slice 2 handoff closure)"]
approved_by: David (repository owner) — DESIGN RECORDED; implementation authorized 2026-07-28T17:43:31Z
purpose: Move AIVSB retrieval context out of final platform outputs and into a PRIVATE pre-output composition context that actually influences composition, while preserving exact OFF-path behavior and preventing any retrieved context from appearing in the public return object.
review_gate: "RECORDED — SLICE 2R DESIGN. Implementation authorized by David at 2026-07-28T17:43:31Z. Flag remains OFF. Activation, Phase 3 execution, pushes, and production rollout remain unauthorized."
tags: [handoff, aivsb, slice-2r, injection-boundary, remediation, implementation-executed]
---

# Handoff — Slice 2R AIVSB Retrieval Injection Boundary Remediation

**handoff_id:** `SLICE2R-AIVSB-INJECTION-BOUNDARY-REMEDIATION` · **revision:** 2026-07-27
**Marked:** RECORDED AND IMPLEMENTED LOCALLY. Authorized at `2026-07-28T17:43:31Z`; verified at `2026-07-28T17:50:23Z` with `28 passed`; implementation commit `5eed6e1823bc398084e8a46998186771a5970347`. Flag activation, Phase 3 execution, pushes, and rollout remain unauthorized.

**Change signature:** move retrieval before composition; derive only the bounded
`KnowledgeChunk.domain -> caption_style` signal; preserve rotation advancement; keep
raw retrieval text and provenance out of public outputs. Must not alter CTA/release
objectives, retrieval ranking/embedding logic, feature activation, or Visual Director files.

## Why this lane exists (code-verified, revised)
Phase 3 evaluation is BLOCKED because `promo_copy.build_platform_posts` appends the
`[AIVSB RETRIEVED CONTEXT]` block into the FINAL platform outputs
(`promo_copy.py:1267–1273`). Two architectural defects make a naive "relocate the
block into a returned dict key" fix insufficient (per governance review):

1. **A returned dict key is not internal.** Adding `result["composer_prompt_or_context"]`
   keeps sensitive context in the externally observable return contract — it can still
   be serialized, persisted, displayed, copied by callers, or logged. That changes the
   leak path; it does not eliminate it.
2. **Retrieval is operationally inert where it sits.** Inspection of the call graph
   (`promo_copy.py`) shows the three post strings are fully and deterministically
   template-built at **lines 1166–1262** (via `caption_style_lines`, `focused_social_cta`,
   `compact_chapter_hook`). Retrieval is invoked only at **line 1264**, AFTER every post
   string is final. Therefore any block produced there cannot influence composition; ON
   and OFF final outputs would stay identical, making Phase 3 unable to measure
   effectiveness.

**Required architecture (code-grounded):**
```
inputs
  ↓
retrieve context  (moved EARLIER, into a PRIVATE local)
  ↓
private composition context  (NOT part of public return)
  ↓
compose final platform outputs  (helpers consume the private context)
  ↓
return CLEAN public result  (unchanged existing schema)
```
Not: compose → retrieve → attach unused field → return.

## app.py relationship (code-verified)
`app.py:3061` defines `build_platform_posts` as a **thin delegator** to
`promo_copy.build_platform_posts`; `caption_style_lines`/`social_profile` are imported
from `promo_copy` (app.py:3033, 3051). The live path runs through `promo_copy`; `app.py`
does NOT duplicate post generation. Therefore (a) fixing `promo_copy` fixes the live path,
(b) the `tests/test_promo_copy.py` characterization is a delegation-parity check, not a
duplicated-leak risk, and (c) `app.py` is correctly OUT OF SCOPE as a delegate. Slice 2R
does not modify `app.py`.

## Two contracts (explicit separation)
- **`public_result`**: the existing return dict schema only. Safe to serialize/publish.
  Unchanged in both arms. Never contains retrieval text, IDs, query, delimiter, or any
  diagnostic field.
- **`evaluation_record`**: emitted ONLY through `retrieval_eval_sink`. Never included in
  `public_result`. Sole diagnostic/provenance channel. No second query channel. The sink
  records `run_id, manifest_hash, query, returned_chunk_ids, injected_chunk_ids,
  fallback_reason, derived_signal, derived_signal_source_ids` — NOT full chunk bodies or a
  formatted block. Canary tests retain seeded canaries locally in the test harness; runtime
  provenance does not store raw formatted context.

## Structured composition context (the consumer-facing representation)
The formatted `[AIVSB RETRIEVED CONTEXT]` block is NOT a composition input. Accepted hits'
EXISTING `domain` field is mapped to an EXISTING curated `caption_style` family
(`character`->`character_moment`, `worldbuilding`/`location`->`worldbuilding`; other domains
leave the existing `rotating_caption_style` untouched). This influences ONE story-expression
decision (`caption_style_lines` `style`), never the CTA/release objective. The public return
schema is unchanged. The CTA goal (`dynamic_cta_goal`) stays owned by `focus`/`context`.

## Named transformation boundary
```
source_metadata_field:   KnowledgeChunk.domain
observed_allowed_values: character, visual_identity, video, lesson, location, worldbuilding
normalization_required:  none (stable lowercase strings from extractor)
derived_signal:          caption_style family string
composer_function:       caption_style_lines (via its `style` argument)
existing_decision_point: baseline_style = rotating_caption_style(...)  (promo_copy.py:1164, advances rotation)
existing_curated_output_choices: scene_hook, reader_question, stakes, character_moment,
                                worldbuilding, catch_up
fallback:                baseline_style (rotating_caption_style called in BOTH arms)
multi_hit_resolution:    traverse retrieve() order; select the FIRST hit whose validated domain exists in DOMAIN_TO_CAPTION_STYLE
conflict_behavior:       never mix domains; one hit selected; unmapped -> no override
release_cta_behavior:    unchanged (dynamic_cta_goal untouched)
provenance_capture:      see "Provenance semantics" below
```

## Immutable domain map (validated before use)
```
CAPTION_STYLE_VOCAB = {scene_hook, reader_question, stakes, character_moment, worldbuilding, catch_up}
DOMAIN_TO_CAPTION_STYLE = {
    "character": "character_moment",
    "worldbuilding": "worldbuilding",
    "location": "worldbuilding",   # deliberate POLICY mapping, not identity
}
# visual_identity, video, lesson -> no mapping
```
Selection: traverse `retrieve()` hits in returned order; for the first hit whose `domain`
is a key in `DOMAIN_TO_CAPTION_STYLE`, take the mapped style ONLY IF in `CAPTION_STYLE_VOCAB`;
else treat as unmapped. Unknown/missing/malformed/future domain -> no override (never raise).

## Rotation-state preservation
`rotating_caption_style` advances mutable rotation state (promo_copy.py:852,863). Both arms
compute `baseline_style = rotating_caption_style(...)` first; retrieval may override the
current returned `style` but never skips or changes the rotation call. `style = sig.caption_style
or baseline_style`.

## Provenance semantics (corrected)
Retrieval outcome and signal-consumption outcome are SEPARATE fields.
```
returned_chunk_ids:          all IDs returned by retrieval
injected_chunk_ids:          legacy field; Slice 2R value = [] (no raw chunk is "injected")
derived_signal:              selected curated caption-style value; null when no supported domain
derived_signal_source_ids:   [chunk_id of the single selected hit]; [] when none
derived_signal_source_rank:  one-based position of the SELECTED hit in the ORIGINAL
                             retrieve() order; MAY BE > 1
derived_signal_source_domain: validated KnowledgeChunk.domain of that hit; null when none
fallback_reason:             retrieval-layer fallback/failure: "no_hits" | "retrieval_error:<Cls>" | null
signal_fallback_reason:      why no structured signal was consumed: null | "no_mappable_domain" | "invalid_mapped_style"
run_id, manifest_hash, query: as before
```
Examples:
- Useful mapped hit: fallback_reason=null, derived_signal=character_moment,
  derived_signal_source_ids=["chunk-17"], derived_signal_source_rank=2,
  derived_signal_source_domain=character, signal_fallback_reason=null.
- Hits returned, no mapped domain: fallback_reason=null, returned_chunk_ids=["chunk-3","chunk-8"],
  injected_chunk_ids=[], derived_signal=null, derived_signal_source_ids=[],
  derived_signal_source_rank=null, derived_signal_source_domain=null,
  signal_fallback_reason=no_mappable_domain.
- Zero hits: fallback_reason=no_hits, returned_chunk_ids=[], injected_chunk_ids=[],
  derived_signal=null, all derived_signal_source_* = null/[], signal_fallback_reason=null.
Phase 3 must later rename "injection coverage" to "signal-consumption coverage" /
"retrieval-influence coverage" (architecture performs no text injection).

## Verbatim contract (recording-consistency)
```
multi_hit_resolution:
  Traverse hits in the exact order returned by retrieve().
  Select the first hit whose validated domain exists in
  DOMAIN_TO_CAPTION_STYLE.
derived_signal_source_rank:
  The selected hit's one-based position in the original retrieve()
  result order. It may be greater than 1.
fallback_reason:
  allowed_values:
    - null
    - no_hits
    - retrieval_error:<Class>
signal_fallback_reason:
  allowed_values:
    - null
    - no_mappable_domain
    - invalid_mapped_style
```

## Objective (scope-locked)
Move AIVSB retrieval context into a PRIVATE pre-output composition context that can
influence post construction, while:
- public return schema is byte/structure identical across arms (no new keys),
- no retrieved context/diagnostics can appear in `public_result`,
- ON-path provenance is preserved via `retrieval_eval_sink`,
- zero-hit/exception fallbacks keep finals equal to OFF,
- NO changes to query construction, ranking, embeddings, or retrieval logic.

## Flag remains OFF
`ENABLE_AIVSB_RETRIEVAL` defaults `false` throughout implementation and verification.
ON-path behavior exercised only under test mocks/seeded index.

## Authorization boundary
**Authorized now (design):** the six documents in this package.
**NOT authorized:** code changes, commits, test execution, feature activation, Phase 3
fixture freezing/execution, pushes, production rollout.

## Companion documents
`SLICE2R-IMPLEMENTATION-PLAN.md`, `SLICE2R-TEST-PLAN.md`, `SLICE2R-ACCEPTANCE-CRITERIA.md`,
`SLICE2R-ROLLBACK-PLAN.md`, `SLICE2R-EXECUTION-APPROVAL.md`
