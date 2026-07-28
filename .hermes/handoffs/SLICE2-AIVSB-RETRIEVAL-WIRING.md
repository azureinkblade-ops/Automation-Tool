---
status: RECORDED
recorded: true
executed: true
handoff_id: SLICE2-AIVSB-RETRIEVAL-WIRING
revision: 2026-07-27
depends_on_commits: ["2100123 (Slice 1 retrieval index)", "65fb588 (run-level provenance)"]
approved_by: David (repository owner) — authorization granted for consumer wiring only
commit: c9e39c5
purpose: Wire the existing retrieval service into the prompt/composer pipeline behind an OFF feature flag.
review_gate: "Recorded. Implementation authorized within the scoped boundaries below. Flag stays OFF throughout this lane. Implemented and committed as c9e39c5 (flag OFF)."
tags: [handoff, aivsb, slice-2, retrieval, composer, feature-flag]
---

# Handoff - Slice 2 AIVSB retrieval consumer wiring (flag OFF)

**handoff_id:** `SLICE2-AIVSB-RETRIEVAL-WIRING` · **revision:** 2026-07-27
**depends_on:** `2100123` (Slice 1 retrieval index) + `65fb588` (run-level provenance).
Prerequisite (satisfied): provenance lane complete, so index-run records exist and can
be read to identify the index state used by a retrieval call.

## Verified finding (read-only inspection, 2026-07-27)

`retrieve()` returns `list[RetrievalHit]`. Each `RetrievalHit.provenance` dict contains
ONLY `{source_file, chunk_path, version, content_hash}` — **it does NOT carry `run_id`
or `manifest_hash`**. The provenance lane (`65fb588`) wrote `retrieval_index_runs` but
explicitly excluded consumer wiring, so run-level provenance was never attached to hits.
Therefore Slice 2 must add a **minimal read-only accessor** (not duplicate per-hit
fields): `get_active_index_run(root) -> IndexRunProvenance | None` reading the latest
`COMPLETED` run. This is within consumer-wiring scope (identifying the index used) and
must not alter ranking, filtering, embeddings, indexing, or provenance writes.

## Authorization scope (EXPLICITLY granted)

Consumer wiring only:
1. Integrate retrieval into the composer (`promo_copy.py`, entry `build_platform_posts`).
2. Wire behind the existing feature-flag pattern; new flag defaults **OFF**.
3. Preserve OFF-path behavior exactly (see OFF-path verification below).
4. Add retrieval/evaluation logging sufficient for later OFF-vs-ON evaluation.
5. Keep the feature flag **OFF**. No activation.

## Explicitly NOT authorized

Enabling by default; removing the flag; production rollout; Visual Director; retrieval
algorithm/embedding/ranking changes; prompt-quality claims; further architecture changes;
unrelated refactor; any `app.py` behavioral change.

## Feature-flag convention

`ENABLE_AIVSB_RETRIEVAL = os.environ.get("ENABLE_AIVSB_RETRIEVAL", "false").strip().lower()
in ("1","true","yes","on")` — **defaults OFF** (precedent: `ENABLE_POST_AUDIO`).
`promo_copy.py` defines its own flag locally (cannot import `app`), mirroring
`ENABLE_NOVEL_VOICE_VARIANTS`. OFF-path: no retrieval import side effects, no DB reads,
no logging, no retrieval invocation.

## OFF-path verification (controlled differential, not a brittle golden snapshot)

Flag OFF must introduce no observable change:
- Capture baseline output from the PRE-wiring implementation under fixed inputs +
  fully controlled dependencies (mocks/seed/env).
- Apply Slice 2 wiring; run identical inputs/mocks/env/seed with flag OFF.
- Assert EXACT equality of the complete returned structure AND any canonical serialized
  output where serialization is part of the contract.
- Assert `retrieve` was NEVER called.
- Assert NO provenance-log writes and NO retrieval DB reads occurred.
A golden fixture may be retained ONLY where output is provably deterministic; the
critical contract is: flag OFF → no retrieval import side effects → no invocation →
no logging → identical composer result. For Python objects assert deep structural
equality; compare canonical serialized output separately where appropriate.

## Integration design

- Query construction (minimal, no semantic-query redesign): assemble from already
  available composer inputs — novel identifier, platform, content purpose, characters
  explicitly present, scene/post intent already supplied. No new intent classifier,
  query expansion, reranker, or gap-targeting in this slice.
- Context formatting: insert retrieved chunks inside a clearly delimited section:
  `[AIVSB RETRIEVED CONTEXT] ... [END AIVSB RETRIEVED CONTEXT]`. Formatter enforces:
  max hit count, max character/token budget, deterministic ordering, duplicate
  suppression, novel isolation, omission of empty context.
- Failure behavior: contain try/except AROUND the retrieval call + context formatting
  ONLY. On exception or no useful hits → `context = None` → original prompt unchanged.
  Do NOT over-broaden exception catching such that programming defects outside the
  retrieval boundary are hidden.
- Logging boundary: do NOT write to durable provenance tables (those describe index
  construction). Use a separate evaluation/diagnostic structure with fields:
  `retrieval_enabled, retrieval_attempted, retrieval_used, run_id, manifest_hash, query,
  returned_chunk_ids, injected_chunk_ids, fallback_reason`. Do not log full sensitive
  prompt bodies.

## Required tests before commit

- Flag OFF → identical result AND `retrieve` never called AND no retrieval-log write.
- Flag ON with useful hits → injects bounded context exactly once.
- Flag ON → records active `run_id` and `manifest_hash`.
- Zero hits → original prompt preserved.
- Retrieval exception → original prompt preserved.
- Cross-novel hits cannot enter injected context.
- Context ordering + truncation deterministic.
- Existing `promo_copy` tests still pass.
- No `app.py` / Visual Director / activation / retrieval-algorithm changes in staged diff.

## Committed files (isolated)

- `scripts/aivsb/retrieval/retriever.py` (add `get_active_index_run` read-only accessor)
- `scripts/aivsb/retrieval/__init__.py` (export accessor)
- `promo_copy.py` (flag + guarded retrieval injection + evaluation logging)
- `tests/aivsb/test_slice2_wiring.py`
- `.hermes/handoffs/SLICE2-AIVSB-RETRIEVAL-WIRING.md`

No `app.py`, Visual Director, ranking/embedding, or unrelated files. No push without
explicit authorization. Flag OFF throughout.
