# Stock-Source Exclusion Policy (Handoff)

**Owner session:** 20260715_060146_c55923 (active app.py lane owner per AGENTS.md).
**Commits:**
- `85cac61` — Add stock-source exclusion policy to image quality gate (score 0 + excluded flag)
- `694f77a` — Remove dead pixabay stock-scoring branch from image quality gate
**Affected file:** `app.py` only (`image_quality_gate_for_metadata`, lines ~924-1071).

## Intent

Now that the diffusion (Diffusers/LoRA) pipeline is the source of generated art,
stock/third-party photo services must NEVER be used or re-used in the author/studio
pipeline. Any image whose own recorded source is a stock/third-party service is
force-excluded with the lowest possible score (0) and an explicit `excluded: True`
flag on its item dict, so downstream selectors (regeneration loop, post build) drop
it outright and a future "is this stock?" query is O(1) rather than a substring rescan.

## Locked product decisions (David, 2026-07-25)

1. **Stock is ALWAYS excluded**, including human-approved stock images. The exclusion
   block fires BEFORE the `manually_approved` check (line ~984), so `approved_images`
   cannot rescue a stock image. Decision: "stock images should always be excluded now
   that we have the diffusion pipeline; those can be removed and never re-used."
2. **Canva is blocked for author/studio purposes.** Added `"canva"` to the token list
   so Canva-sourced images are excluded from the studio pipeline the same as other
   stock. Decision: "Canva images shouldn't be used for author purposes only studio."
3. **Dead pixabay score branch removed** (was `elif "pixabay": score -= 12`). The new
   policy block fires first and `continue`s, making that branch unreachable. Removed in
   `694f77a` as a separate cleanup commit.

## What changed (two insertions, both inside image_quality_gate_for_metadata)

**Region A** — after `source_entries = ...` (~line 957), define the policy constant:

```python
    # Stock/third-party photo exclusion policy (2026-07-25): images whose OWN recorded
    # source is a stock/third-party photo service are excluded with the lowest possible
    # score (0) and flagged excluded=True so downstream selectors drop them outright.
    STOCK_SOURCE_TOKENS = (
        "pixabay", "pexels", "unsplash", "shutterstock", "gettyimages",
        "getty images", "adobe stock", "stock.adobe.com", "freepik", "depositphotos",
        "canva",
    )
```

**Region B** — after `source_searchable = ...` (~line 983), INSIDE the per-image loop,
BEFORE the `manually_approved` check (~line 984):

```python
        # Per-image stock check uses THIS image's own recorded source only, never the
        # whole-pack source, so a mixed pack does not mislabel Diffusers images.
        per_image_source = source_entries[index] if index < len(source_entries) else ""
        is_stock_source = any(tok in per_image_source.lower() for tok in STOCK_SOURCE_TOKENS)
        if is_stock_source:
            score = 0
            reasons.append("excluded: stock/third-party photo source (policy)")
            items.append({
                "image": str(image),
                "score": score,
                "reasons": reasons,
                "source": source_for_image,
                "excluded": True,
            })
            errors.append(
                f"Image quality is weak ({score}/100): {image.name}. "
                f"Stock source excluded by policy; regenerate or manually approve."
            )
            continue
```

## CRITICAL correction vs. the original draft plan (do not regress)

The first draft used a WHOLE-PACK source string (`source_for_exclusion =
source_text + " ".join(source_entries)`) for the stock check. That is WRONG: in a
mixed pack (one Pexels image + one Diffusers image) the whole-pack string contains
"pexels" from the first image, so EVERY image in the pack would be flagged stock —
including the Diffusers one. The verification gate (below) would FAIL its assertion
that the Diffusers item carries no `excluded` key.

The committed code uses `per_image_source = source_entries[index]` (this image's OWN
source only). Keep it that way. A mixed pack must flag only the stock image.

## Signature (what it must / must not alter)

MUST:
- force `score = 0` + `excluded: True` for any image whose own recorded source matches
  a STOCK_SOURCE_TOKEN.
- fire before manual-approval so approved stock is still excluded.
- skip the rest of the scoring for that image (`continue`) so it cannot earn points back.

MUST NOT:
- alter Diffusers / OpenAI / Google / banked / animated-composer / promo-card scoring.
- change the `max(0, min(100, score))` clamp or item schema for non-stock images.
- touch any generation, publishing, or app.py code outside this function.
- reintroduce the whole-pack-source stock check (mixed-pack mislabel bug).

## Verification gate (passed)

Built a temp folder with `image` (pexels source) + `images[]` (diffusers, with
`*.local-sd.json` sidecar). Called `image_quality_gate_for_metadata(folder, metadata)`.
Asserted: pexels item `score == 0` and `item["excluded"] is True`; diffusers item score
normal (~80) and NO `excluded` key. Result: GATE PASS. Also grep-confirmed the dead
pixabay branch is gone (`stock fallback source` count = 0) and `STOCK_SOURCE_TOKENS`
present (2 references: def + check).

## Activation

Always-on (no flag). Any stock-sourced image in any pack is now excluded at the quality
gate and triggers the existing `score < 45` regenerate/reject error path. The
`ALLOW_EXTERNAL_IMAGE_FALLBACK` switch (app.py ~109-123) still governs whether the
pipeline even attempts Pexels/Pixabay substitution upstream; with this gate, even if a
stock image reaches the gate it is excluded.

## Notes for the receiving session

- `excluded` is an additive item key; existing consumers ignore unknown keys, so no
  schema migration.
- Token matching is lowercase substring. To cover more/other services, edit
  `STOCK_SOURCE_TOKENS` only.
- Downstream consumers that should DROP excluded images (regeneration, post build) read
  `item["excluded"]` — verify those consumers honor the flag if/when wiring them.
- Status: committed locally (`85cac61`, `694f77a`); not pushed (deferred-cleanup rule).
