---
status: DRAFT
schema_version: phase3-fixture-v2-slice2r
fixture_freeze_authorized: false
subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
---

# Phase 3 Fixture Schema

## Frozen allocation

Exactly 24 fixtures:

| novel_id | count | required focuses |
|---|---:|---|
| en | 6 | royal_road_live, patreon_early, youtube_release, weekly_general_promo, catch_up_archive, generic |
| ha | 6 | same six |
| hp | 6 | same six |
| sf | 6 | same six |

Each fixture is one production-shaped `build_platform_posts()` input and one
complete public result bundle per arm. Fixtures must be selected without
observing ON retrieval or ON output.

## Required object

```yaml
fixture_id: FX-EN-001
novel_id: en
chapter_id: "..."
requested_focus: royal_road_live
composer_inputs:
  abbr: en
  novel: Eternal Nexus
  chapter: "..."
  title: "..."
  phrases: ["..."]
  characters: ["..."]
rotation_stub:
  version: phase3-rotation-stub-v1
  return_index: 0
ledger_state: {...}
release_status: {...}
canon_reference:
  source_files: [style_guides/en.yaml]
  source_hashes: [sha256]
  relevant_facts: [product-reviewed fact]
  prohibited_claims: [product-reviewed prohibited claim]
expected_contract:
  public_keys: [caption, patreon_note, facebook_post, x_post, x_thread_links, post_focus, caption_style, tracking_campaign, _agent_source]
  scored_text_fields: [caption, patreon_note, facebook_post, x_post]
  leak_checked_fields: ALL_RECURSIVE
qualification:
  product_reviewed: true
  selected_without_observing_on_output: true
  status: qualified
```

## Freeze blockers

The validator fails on count/allocation/focus mismatch, duplicate IDs, missing
composer inputs/stubs, missing or malformed source hashes, unresolved product
review, pre-observed ON output, or public-contract mismatch.

Canon facts and prohibited claims come from approved source files and David's
product review. Retrieval results cannot label their own relevance or truth.

## Current state

No fixture inventory exists or is frozen under this authorization. Running the
validator on a future candidate file is allowed only after candidate material is
separately authorized. The present harness tests use disposable synthetic data.
