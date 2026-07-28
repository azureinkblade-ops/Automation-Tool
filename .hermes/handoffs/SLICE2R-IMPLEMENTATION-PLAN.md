# Slice 2R — Implementation Plan (Design, recorded: contract-precision edits applied)

**Part of:** `SLICE2R-AIVSB-INJECTION-BOUNDARY-REMEDIATION` (RECORDED design; implementation not authorized)

## Exact defect location (verified)
`promo_copy.py` `build_platform_posts`:
- `style = rotating_caption_style(...)` computed at **line 1164**; passed to the three
  `caption_style_lines` calls (1166/1168/1170). `rotating_caption_style` calls
  `rotation_next` (promo_copy.py:852,863) — it ADVANCES mutable rotation state.
- Posts template-built at **lines 1166–1262**.
- Retrieval invoked only at **line 1264** (after posts final). Lines **1267–1273** append
  the `[AIVSB RETRIEVED CONTEXT]` block into FINAL post strings (the leak + inertness).

## Repository-grounded signal (inspected, not invented)
- `KnowledgeChunk.domain` (chunk_extractor.py:57) is an EXISTING field with a FIXED
  vocabulary from `_domain_for` (chunk_extractor.py:77): `character, visual_identity,
  video, lesson, location, worldbuilding`.
- `caption_style` (the `style` arg to `caption_style_lines`) is an EXISTING curated
  story-expression decision: `scene_hook, reader_question, stakes, character_moment,
  worldbuilding, catch_up` (promo_copy.py:854–861, 890+).
- `dynamic_cta_goal` (release/distribution objective) is NOT touched.

## The named transformation boundary (required structure)
```
source_metadata_field:   KnowledgeChunk.domain
observed_allowed_values: character, visual_identity, video, lesson, location, worldbuilding
normalization_required:  none (stable lowercase strings from extractor)
derived_signal:          caption_style family string
composer_function:       caption_style_lines (via its `style` argument)
existing_decision_point: style = rotating_caption_style(...)  (promo_copy.py:1164)
existing_curated_output_choices: scene_hook, reader_question, stakes, character_moment,
                                worldbuilding, catch_up
fallback:                current rotating_caption_style(...) result (advance rotation once)
release_cta_behavior:    unchanged (dynamic_cta_goal untouched)
multi_hit_resolution:    traverse retrieve() order; select the FIRST hit whose validated domain exists in DOMAIN_TO_CAPTION_STYLE
conflict_behavior:       never mix domains; one hit selected; unmapped -> no override
provenance_capture:      see "Provenance semantics" below
```

## Immutable explicit domain map (validated before use)
```
CAPTION_STYLE_VOCAB = {"scene_hook","reader_question","stakes","character_moment","worldbuilding","catch_up"}
DOMAIN_TO_CAPTION_STYLE = {
    "character": "character_moment",
    "worldbuilding": "worldbuilding",
    "location": "worldbuilding",   # deliberate POLICY mapping, not identity
}
# visual_identity, video, lesson -> no mapping (None)
```
Selection: traverse `retrieve()` hits in returned order; for the first hit whose
`domain` is a key in `DOMAIN_TO_CAPTION_STYLE`, take the mapped style ONLY IF it is in
`CAPTION_STYLE_VOCAB`; otherwise treat as unmapped. Unknown/missing/malformed/future
domain values -> no override (never raise, never guess).

## Rotation-state preservation (critical)
`rotating_caption_style` advances mutable rotation state. ON must NOT skip that call.
```
baseline_style = rotating_caption_style(story, f"campaign_{chapter_id or slugify(title)}_{focus}", rotation_next=rotation_next)
sig = _aivsb_retrieval_signal(...) if ENABLE_AIVSB_RETRIEVAL else None   # may call retrieve()
style = sig.caption_style if (sig and sig.caption_style in CAPTION_STYLE_VOCAB) else baseline_style
```
Both arms call `rotating_caption_style` exactly once with identical arguments. Retrieval
may override the *current returned style* but never alters rotation advancement, ledger
writes, or the subsequent style sequence.

## Smallest permitted code change (revised)
1. Add the bounded signal type (only what is consumed):
   ```
   @dataclass(frozen=True)
   class RetrievedCompositionSignal:
       caption_style: str | None
   ```
2. Refactor the retrieval helper to return the structured signal (NOT a formatted block),
   traversing `retrieve()` order and recording provenance via the sink:
   ```
   def _aivsb_retrieval_signal(...) -> RetrievedCompositionSignal | None:
       # retrieve(); traverse hits in returned order; pick first mappable domain;
       # on zero-hits/exception/provenance-failure -> return None (contained)
       # emit sink record with derived_signal_* fields; injected_chunk_ids = []
   ```
3. Compute `baseline_style` BEFORE any retrieval call (line ~1164 region), so rotation
   advances in both arms. Move retrieval earlier, flag-gated, but AFTER `baseline_style`.
4. DELETE lines 1263–1273 (post-composition block concatenation).
5. Return dict (1274–1284) UNCHANGED in both arms.
6. NO `goal_override` on `focused_social_cta`. `dynamic_cta_goal` unchanged.

## Provenance semantics (corrected)
Retrieval outcome and signal-consumption outcome are SEPARATE fields. The sink record:
```
returned_chunk_ids:   all IDs returned by retrieval
injected_chunk_ids:   legacy field retained for schema compatibility; Slice 2R value = []
derived_signal:       selected curated caption-style value; null when no supported domain
derived_signal_source_ids:   [chunk_id of the single selected hit]; [] when none
derived_signal_source_rank:  one-based position of the SELECTED hit in the ORIGINAL
                             retrieve() order; MAY BE > 1
derived_signal_source_domain: validated KnowledgeChunk.domain; null when none
fallback_reason:      retrieval-layer fallback/failure: "no_hits" | "retrieval_error:<Cls>" | null
signal_fallback_reason:  why no structured signal was consumed: null | "no_mappable_domain" | "invalid_mapped_style"
run_id, manifest_hash, query: as before
```
No raw chunk is classified as "injected". The Phase 3 design must later rename
"injection coverage" to "signal-consumption coverage" / "retrieval-influence coverage".

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

## How finals are proven clean
- `caption_style_lines` emits curated template text keyed by an enumerated style; no raw
  chunk body, excerpt, chunk ID, query, delimiter, or sink key enters `public_result`.
- Leak tests (canary + structural) assert absence across all public fields.

## OFF-path identity
- Flag OFF -> `sig is None` -> `style == baseline_style` (identical to today, rotation
  advanced once). `tests/test_promo_copy.py` (promo_copy <-> app.py delegation) must pass.

## ON-path provenance preservation
- Sink captures run_id, manifest_hash, query, returned_chunk_ids, injected_chunk_ids(=[]),
  fallback_reason, derived_signal, derived_signal_source_ids, derived_signal_source_rank,
  derived_signal_source_domain. Unchanged otherwise.

## Zero-hit / exception fallback
- `_aivsb_retrieval_signal` returns `None` on zero hits / exception / provenance failure.
  `style == baseline_style`; finals equal OFF baseline; no leak; fallback_reason recorded;
  no exception escapes `build_platform_posts`.

## No CTA / release / query / ranking / embedding / retrieval changes
- `dynamic_cta_goal`, `focused_social_cta` goal logic, `retrieve()`, `provenance.py`,
  `chunk_extractor.py`, embedding workers UNTOUCHED.
- Only `promo_copy.py` (signal type + helper refactor + `baseline_style` + `style` select +
  delete 1263–1273) + new test.

## Files in scope (isolated commit)
- `promo_copy.py` (add `RetrievedCompositionSignal`, `DOMAIN_TO_CAPTION_STYLE`,
  `CAPTION_STYLE_VOCAB`; `_aivsb_retrieval_signal`; `baseline_style`; select `style`; delete
  1263–1273).
- `tests/aivsb/test_slice2r_injection_boundary.py` (new).
- `.hermes/handoffs/SLICE2R-*.md`.
No `app.py`, no `scripts/aivsb/retrieval/*` logic, no Visual Director.
