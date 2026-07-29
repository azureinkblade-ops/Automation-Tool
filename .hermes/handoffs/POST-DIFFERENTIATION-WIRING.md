# Post-Differentiation Agent Wiring (Handoff)

**Owner session:** 20260715_060146_c55923 (this session — confirmed it is the
active app.py lane owner per AGENTS.md; tree was clean before edit).
**Commit:** `7e4af50` on `main` (Automation Tool repo).
**Affected file:** `app.py` only (42 insertions, 2 deletions).

## Intent

The `post-differentiation-agent` skill (Hermes) generates correct per-novel,
research-aware social post copy as JSON. `tools/agent_post_writer.generate_post_copy()`
shells out to that skill and returns the dict. `promo_copy.build_platform_posts`
already has a consumer ("Agent override" at promo_copy.py ~1106) that splices
`agent_copy["caption"]/["cta"]/["hashtags"]` into IG/FB/Patreon/X.

The bug: the PRIMARY daily post builders called `build_platform_posts` WITHOUT
`agent_copy`, so the agent output never reached the posts (template fallback).
The integration existed only at the resurface/reuse path (~31919), not the
daily chapter + resurfacing builders.

## What changed

Replicated the existing `ENABLE_AGENT_POSTS` wiring (already proven at ~31919)
at two daily call sites:
- chapter post builder (~3354)
- resurfacing post builder (~9341)

Each now: if `ENABLE_AGENT_POSTS` is on and `abbr` present, calls
`generate_post_copy(abbr, title, chapter, hook, material)` and passes the
result as `agent_copy=` to `build_platform_posts`. Fail-soft: any exception or
missing output -> `agent_copy=None` -> template engine.

## Signature (what it must / must not alter)

MUST:
- leave default behavior unchanged when `ENABLE_AGENT_POSTS` is off (verified).
- apply agent copy only when the env flag is on.
- never block a post build on agent failure.

MUST NOT:
- change the resolver, telemetry, AIVSB, or any other subsystem.
- alter the promo_copy override logic (only the call-site wire was missing).
- run broad formatting/cleanup.

## Verification

- `promo_copy.build_platform_posts(title, ch, mat)` (no agent_copy) -> template
  copy, unchanged.
- `promo_copy.build_platform_posts(..., agent_copy=<SF agent JSON>)` -> IG/FB/X
  captions contain the agent caption + CTA + `#SoulforgeEra`/`#AzureInkblade`;
  `_agent_source` = `hermes_agent`.

## Activation

Not active by default. To collect differentiated posts, set in the app.py
runtime environment:

    ENABLE_AGENT_POSTS=1

(plus RESEARCH_BRIEF_PATH if the per-novel brief folder differs from the default
`~/Documents/Hermes Vault/Hermes/Research Briefs`).

## Note on scope

This closes the "post differentiation did not apply to the posts" gap for the
daily builders. It does NOT change the video/reel voice-variant flags
(ENABLE_NOVEL_VOICE_VARIANTS is a separate, video-scoped subsystem with no
consumer) nor the story-hook Hermes->app video bridge (separate issue). Those
remain distinct work items.
