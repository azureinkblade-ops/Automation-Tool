# Slice 2R — Test Plan (Design, recorded: contract-precision edits applied)

**Part of:** `SLICE2R-AIVSB-INJECTION-BOUNDARY-REMEDIATION` (RECORDED design; implementation not authorized)
**Principle:** (a) prove the `domain` -> `caption_style` signal influences ONE named
story-expression decision using RETRIEVAL ORDER; (b) prove rotation state is advanced
identically in both arms; (c) prove NO diagnostic/raw content leaks with corrected
provenance semantics. Canary tests separate legitimate derived signal from leakage.

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

## Public vs diagnostic contracts
- `public_result` = return dict of `build_platform_posts`. Existing schema only.
- `evaluation_record` = only `retrieval_eval_sink` output. Never in `public_result`.

## T1 — Public schema identity (both arms)
- `frozen_public_keys = {"caption","patreon_note","facebook_post","x_post","x_thread_links","post_focus","caption_style","tracking_campaign","_agent_source"}`
- OFF and ON: `set(result.keys()) == frozen_public_keys`. Recursively: no retrieval-only
  field (retrieved_context_block, query, chunk_ids, run_id, manifest_hash, retrieval_*,
  derived_signal, derived_signal_source_*) anywhere in `result`, incl. nested + JSON package.

## T2 — OFF arm regression
- Flag OFF: `retrieve`/`get_active_index_run` never called; `rotating_caption_style` called
  exactly ONCE with the same args as ON baseline; `style == baseline_style`; `dynamic_cta_goal`
  output unchanged vs current `main`.

## T3 — Structural leak protection (ON)
- ON, seeded index, sink capturing. Recursively assert `public_result` (all fields + nested
  + JSON package) contains NONE of: diagnostic keys, chunk IDs (real `chunk_id` strings),
  `[AIVSB RETRIEVED CONTEXT]`/`[END AIVSB RETRIEVED CONTEXT]` delimiters, serialized retrieval
  records, `derived_signal`/`derived_signal_source_*` values.

## T4 — Canary leak protection (ON, decisive)
- Seed test retrieval hits with UNIQUE private sentinels in raw block/provenance/query:
  `PRIVATE_CANON_CANARY_7F31A9`, `PRIVATE_SOURCE_PATH_CANARY_84D2`, `PRIVATE_QUERY_CANARY_19C0`.
- Assert NONE of these (nor normalized variants) appear ANYWHERE in `public_result`
  (caption, facebook_post, x_post, patreon_note, x_thread_links, nested, serialized).
- Separately assert the approved DERIVED signal (a `caption_style` family value) MAY appear
  as the `caption_style` field — distinguishing legitimate composition use from leakage.

## T5 — Retrieval-order selection (two distinct cases)
### Case A — Rank preservation
- Seed index so rank 1 = `domain == "worldbuilding"` (mapped) and rank 2 = `domain == "character"`
  with a LEXICALLY-EARLIER chunk ID (mapped).
- Assert `derived_signal == "worldbuilding"`, `derived_signal_source_rank == 1`,
  `derived_signal_source_domain == "worldbuilding"`, `result["caption_style"] == "worldbuilding"`.
- Proves no post-retrieval `chunk_id` re-sort (lexically-earlier character chunk at rank 2 is NOT chosen).

### Case B — Skip unmapped hits
- Seed index so rank 1 = `domain == "video"` (unmapped), rank 2 = `domain == "character"` (mapped).
- Assert `derived_signal == "character_moment"`, `derived_signal_source_rank == 2`,
  `derived_signal_source_domain == "character"`, `result["caption_style"] == "character_moment"`.
- Proves unmapped higher-ranked hits are skipped and the first MAPPABLE hit in retrieval order is used.

## T6 — Derived-signal influence (outcome-based)
- Controlled fixture (Case B or a clean rank-1 character): assert `result["caption_style"] ==
  "character_moment"` and the produced caption uses the character_moment template family
  (detectable via its known opener), differing from the OFF baseline style. Assert
  `dynamic_cta_goal` output UNCHANGED vs OFF. No Phase 3 quality needed.

## T7 — Unknown / malformed domain degrades cleanly
- ON, top-ranked hit `domain == "video"` (unmapped), or `domain == ""`, or missing, or a
  future value -> `derived_signal is None`, `style == baseline_style` (identical to OFF),
  no override, no exception. (Covers visual_identity/video/lesson + malformed/future.)

## T7b — Hits returned but no mappable domain (signal-consumption fallback)
- ON, ALL returned hits have unmapped domains (e.g. rank 1 video, rank 2 visual_identity).
- Assert sink: `fallback_reason == null`, `returned_chunk_ids` non-empty, `injected_chunk_ids == []`,
  `derived_signal == null`, `derived_signal_source_ids == []`, `derived_signal_source_rank == null`,
  `derived_signal_source_domain == null`, `signal_fallback_reason == "no_mappable_domain"`.
- Confirms retrieval succeeded but no structured signal was consumed (separate from `no_hits`).

## T8 — Canary + derived signal across novels/platforms
- T4/T5/T6 repeated for `en`, `ha`, `hp`, `sf` and main post fields; zero canary leaks;
  derived signal present exactly where a first MAPPABLE hit in retrieval order exists.

## T9 — Rotation-state preservation (critical)
- Spy/wrap `rotating_caption_style` (or count `rotation_next` calls) to confirm it is invoked
  EXACTLY ONCE with IDENTICAL arguments in OFF and ON arms (including when retrieval supplies
  an override). Assert rotation advancement occurs identically; subsequence of styles is
  unaffected by retrieval. (ON must NOT skip the rotation call.)

## T10 — Zero-hit keeps finals clean + equal
- ON, `retrieve` returns `[]` -> `sig is None` -> `style == baseline_style`; `result` equals
  OFF baseline; no canary; sink `injected_chunk_ids == []`, `fallback_reason == "no_hits"`,
  `signal_fallback_reason == null`.

## T11 — Retrieval exception keeps finals clean + equal
- ON, `retrieve` raises -> `sig is None`; `result` equals OFF baseline; no canary; sink
  `fallback_reason` starts `retrieval_error:`; `injected_chunk_ids == []`; `signal_fallback_reason == null`; no exception escapes.

## T12 — Provenance semantics accurate (ON)
- ON + useful hit: sink record has `run_id`, `manifest_hash`, `query`, `returned_chunk_ids`
  (all returned), `injected_chunk_ids == []` (legacy empty), `fallback_reason == null`,
  `derived_signal` (e.g. "character_moment"), `derived_signal_source_ids` == [selected chunk_id],
  `derived_signal_source_rank` == (the selected hit's one-based retrieve() position, MAY be > 1),
  `derived_signal_source_domain` == validated domain, `signal_fallback_reason == null`.
- ON + hits but no mappable domain (per T7b): `fallback_reason == null`, `returned_chunk_ids`
  non-empty, `derived_signal == null`, `signal_fallback_reason == "no_mappable_domain"`.
- Query + derived signal ONLY in sink, never `result`.

## T13 — app.py delegation parity
- `tests/test_promo_copy.py` (promo_copy <-> app.py) must PASS. Live path (app.py delegates to
  promo_copy) fixed transitively; app.py is a delegate, not a duplicated leak.

## T14 — Determinism
- Repeated ON calls same inputs -> identical `caption_style`, identical posts, identical sink
  `derived_signal_source_rank`/`derived_signal_source_ids`.

## T15 — No duplicate query / no global state / no CTA override
- Assert `_aivsb_retrieval_signal` returns `RetrievedCompositionSignal | None` (no `(block,query)`);
  no module-global `_last_aivsb_query`; `focused_social_cta` receives NO `goal_override`;
  `dynamic_cta_goal` called with unchanged args.

## Execution constraints
- Fixed stubs (deterministic `rotation_next`, ledger, release status).
- ON tests redirect `automation_db.connect` to a seeded temp DB (proven Slice-2 pattern).
- Flag via env + module reload in test isolation only. No live index, no GPU, no generation.
