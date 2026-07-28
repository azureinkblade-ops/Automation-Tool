# Slice 2R — Acceptance Criteria (Design, recorded: contract-precision edits applied)

**Part of:** `SLICE2R-AIVSB-INJECTION-BOUNDARY-REMEDIATION` (RECORDED design; implementation not authorized)

All criteria must be met before the lane is declared complete and handed off.

## Verbatim contract (recording-consistency; matches implementation plan)
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

## AC-1 — No leak into public return object (blocking, structural + canary)
Across every fixture, both arms, all public fields (caption, facebook_post, x_post,
patreon_note, x_thread_links, nested metadata, JSON-serialized package): NONE of
diagnostic keys, chunk IDs, run IDs, manifest hashes, delimiters, serialized retrieval
records, `derived_signal`/`derived_signal_source_*` values, or private canaries
(`PRIVATE_CANON_CANARY_7F31A9`, `PRIVATE_SOURCE_PATH_CANARY_84D2`, `PRIVATE_QUERY_CANARY_19C0`)
may appear. Verified T1/T3/T4/T8. No exception.

## AC-2 — Outcome-based: repository-grounded signal drives ONE story-expression decision
When ON and a rank-1 mappable hit exists, the consumer derives `caption_style` and supplies
it to `caption_style_lines` (the existing `style` decision, promo_copy.py:1164/1166+). A
controlled fixture (T5/T6) proves this decision changes as specified, while canaries/
diagnostics/raw content/identifiers stay absent from the unchanged public schema. No Phase 3
quality conclusions required.

## AC-3 — CTA / release objective NOT overridden
`dynamic_cta_goal` and `focused_social_cta` goal logic unchanged; `focused_social_cta` receives
NO `goal_override`. CTA objective remains owned by `focus`/`context`. Verified T2/T6/T15.

## AC-4 — Retrieval order preserved (NEW)
The selected source is the FIRST MAPPABLE hit in the exact order returned by `retrieve()`
(its `derived_signal_source_rank` MAY BE > 1), not a post-retrieval `chunk_id` re-sort.
Verified T5 Case A (rank-1 worldbuilding chosen over a lexically-earlier character chunk at
rank 2) and Case B (rank-1 video unmapped skipped; rank-2 character selected). No
post-retrieval chunk_id sorting.

## AC-5 — Rotation side effects preserved (NEW)
`rotating_caption_style` is invoked EXACTLY ONCE with IDENTICAL arguments in both arms,
including when retrieval supplies an override. Retrieval may override the current returned
`style` but must NOT alter rotation advancement, ledger writes, or subsequent style sequence.
Verified T2/T9 (rotation stub call count + args compared across arms).

## AC-6 — Provenance semantics accurate (NEW)
Retrieval outcome and signal-consumption outcome are SEPARATE. No raw chunk is classified as
injected. `injected_chunk_ids` remains `[]` (legacy field, retained for schema compatibility).
The selected signal and its source are recorded separately:
`derived_signal`, `derived_signal_source_ids` (single selected chunk id), `derived_signal_source_rank`
(one-based position of the SELECTED hit in the ORIGINAL retrieve() order; MAY BE > 1),
`derived_signal_source_domain` (validated `KnowledgeChunk.domain`). `fallback_reason` records
retrieval-layer outcome (`no_hits` / `retrieval_error:<Cls>` / null); `signal_fallback_reason`
records signal-consumption outcome (null / `no_mappable_domain` / `invalid_mapped_style`).
Verified T10/T11/T12 (incl. T7b: hits returned, no mappable domain -> `fallback_reason=null`,
`signal_fallback_reason=no_mappable_domain`, `derived_signal=null`).

## AC-7 — Unknown domains degrade cleanly (NEW)
Missing, malformed, unsupported, or newly introduced `domain` values produce NO style override
and preserve the baseline `rotating_caption_style` result (no exception, no guessed mapping).
Verified T7.

## AC-8 — Public schema identity preserved
`set(ON_result.keys()) == set(OFF_result.keys()) == frozen_public_keys`. No new key either arm.
Recursively no retrieval-only field anywhere in `result`.

## AC-9 — OFF-path identity preserved
Flag OFF: output byte/structure identical to current `main`; `retrieve` never called;
`style == baseline_style`; `rotating_caption_style` called once. Verified T2 + T13
(promo_copy<->app.py characterization passes).

## AC-10 — Provenance preserved (sink only)
ON captures run_id, manifest_hash, query, returned_chunk_ids, injected_chunk_ids([]),
fallback_reason, derived_signal, derived_signal_source_ids, derived_signal_source_rank,
derived_signal_source_domain via `retrieval_eval_sink`. Query and derived signal exist ONLY in
the sink, never `result`. No duplicate query channel; no module-global `_last_aivsb_query`.
Verified T12/T15.

## AC-11 — No raw block as composition input (explicit)
The formatted `[AIVSB RETRIEVED CONTEXT]` block (or any delimiter-bearing text) is NOT passed
into any template helper. The composer receives only `RetrievedCompositionSignal.caption_style`.
The formatted block, if retained, is sink-only and only if the sink already logs it. Verified T3/T4 + code review.

## AC-12 — Narrow scope
One shared story-expression signal (`caption_style`) affects one existing decision
(`caption_style_lines` `style`). No per-platform raw-block fan-out; no broad template redesign;
no release/CTA/distribution change. Verified by staged-diff + T5/T6/T7.

## AC-13 — No scope creep
No change to `dynamic_cta_goal`, `focused_social_cta` goal logic, `retrieve()`, `provenance.py`,
`chunk_extractor.py`, embeddings, or any `scripts/aivsb/retrieval/*` logic. Only `promo_copy.py`
(signal type + DOMAIN_TO_CAPTION_STYLE + helper refactor + baseline_style + style selection +
delete 1263–1273) + new test.

## AC-14 — Isolated commit
Commit = `promo_copy.py` + `tests/aivsb/test_slice2r_injection_boundary.py` + handoff docs.
No `app.py`, no Visual Director, no retrieval-logic changes. `git diff --cached --check` clean.

## AC-15 — Flag OFF in main
`ENABLE_AIVSB_RETRIEVAL` still defaults `false` in `promo_copy.py`. Never enabled in `main`/production.

## AC-16 — Tests pass
Full aivsb suite + `tests/test_promo_copy.py` pass after the change.

## Non-acceptance (explicitly NOT required)
- Activation of the feature flag.
- Phase 3 fixture freezing or execution.
- Any retrieval/embedding/ranking change, CTA-goal override, or new taxonomy/classifier.
- Production rollout or push.
- A broad prompt/template redesign or per-platform raw-block consumption.
