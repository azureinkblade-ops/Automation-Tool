# Phase C Handoff — Wire AIVSB Reasoning into the chapter image path

**From:** reasoning/strategy session
**To:** editing/implementation session `20260715_060146_c55923` (owner of `app.py`)
**Status:** READY — hand off now.
**Handoff commit (reasoning boundary + tests, pushed):** `8b24397` on `origin/main`.

---

## Task

Connect `compose_aivsb_scene_prompt()` to `make_chapter_image_prompts()`.

Phase C targets **only the chapter/story-image path**. Do **not** broaden it to
every image generator in the same change.

## Why this is ready

- The reasoning package is isolated (`Inkblade Author Studio/scripts/aivsb/reasoning/`).
- The Prompt Composer tests pass (13/13).
- The application boundary is dormant (`compose_aivsb_scene_prompt`, app.py line ~7273).
- The working tree is clean; the boundary is committed and pushed (`8b24397`).
- Ownership of the live call site is clear (editing lane owns `app.py`).
- The chapter-to-beat splitter does **not** block Phase C: the first integration
  can consume explicit or existing beat context (e.g. `visual_sentences` output
  already computed inside `make_chapter_image_prompts`) and retain legacy
  fallback until automatic beat extraction is ready.

## Real call sites (verified 2026-07-22, HEAD 8b24397)

- `make_chapter_image_prompts` **def**: `app.py:30258`
  Signature: `make_chapter_image_prompts(title: str, chapter: str, phrases: list[str], novel: str = "") -> list[str]`
  It already derives beats via `visual_sentences(chapter, 3, novel or title)` at line 30259.
- Callers (the chapter/story-image path):
  - `app.py:3264`
  - `app.py:14807`
  - `app.py:14814`
  - `app.py:31656`
  - `app.py:31668`
- Dormant boundary to call: `compose_aivsb_scene_prompt(...)` at `app.py:7273`.

## Constraints (acceptance contract — every item must hold)

- `AIVSB_REASONING_ENABLED` remains **disabled by default**.
- Legacy behavior is **unchanged when disabled** (byte-equivalent output).
- Failure falls back to the **legacy prompt path** (never raises to the caller).
- **No global LoRA behavior changes.**
- **No removal of legacy prompt logic.**
- **No automatic server restart.**
- **No interaction with `_LOCAL_SD_GPU_LOCK` before render.**
- Record **reasoning status** and **fallback reason** (structured log line,
  e.g. `[aivsb-reasoning] enabled|skipped|failed reason=...`).
- Preserve **rule IDs, Bible version, LoRA source, and warnings** where available
  (these come back on the `ComposedScenePrompt` from the composer).

## Recommended integration shape

1. Inside (or at the callers of) `make_chapter_image_prompts`, when
   `AIVSB_REASONING_ENABLED=1`, build a `SceneRequest` from the available
   chapter context (novel, title, existing beat/`visual_sentences` output,
   platform/asset_type = chapter still) and call `compose_aivsb_scene_prompt(...)`.
2. If it returns a `ComposedScenePrompt`, use `.prompt` / `.negative_prompt`
   and carry `.applied_rule_ids`, `.bible_version`, `.lora_track`/lora_source,
   `.warnings` into the artifact metadata for auditability.
3. If it returns `None` (disabled, missing package/Bible, or `ComposerError`),
   fall through to the existing legacy prompt string unchanged.

## Composer contract (for reference)

`ComposedScenePrompt` fields: `prompt`, `negative_prompt`, `lora_track`,
`orientation`, `width`, `height`, `bible_version`, `scene_decision_version`,
`applied_rule_ids` (tuple), `warnings` (tuple). It has `.to_dict()` for logging.

`SceneRequest` fields: `novel_id`, `chapter_id`, `source_text`,
`selected_beat_id`, `character_ids` (tuple), `platform`, `asset_type`,
`orientation`, `spoiler_level`.

## Verification the editing session should run

- Flag OFF: chapter-image prompts are byte-identical to pre-change output.
- Flag ON (isolated test): a chapter still returns a composed prompt with
  populated `applied_rule_ids` + `bible_version`; per-novel negatives present.
- Flag ON, Bible/package missing: falls back to legacy, logs `failed reason=...`,
  does not raise.
- No LoRA default change; no server restart; `_LOCAL_SD_GPU_LOCK` untouched
  before render.
- Regression harness: no NEW failures vs the 2 known-broken env checks.

## Out of scope for Phase C

- Broadening to non-chapter image generators.
- Chapter-to-beat automatic splitter (Phase 1 remainder).
- Any GPU-gated comic LoRA training.
- Removing or refactoring legacy prompt logic.
