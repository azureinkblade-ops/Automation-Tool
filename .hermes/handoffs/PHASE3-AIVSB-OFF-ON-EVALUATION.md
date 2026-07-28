---
status: DRAFT
executed: false
fixture_candidate_preparation_authorized: true
fixture_freeze_authorized: true
phase3_execution_authorized: false
feature_enabled: false
subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
harness_commit: a263b31a34f1013a2dbc78a90743bd08c6e0b079
fixture_freeze_approval_record: PHASE3-FIXTURE-FREEZE-APPROVAL.md
fixture_freeze_authorized_at_utc: 2026-07-28T19:06:08Z
revision: 2026-07-28-slice2r-v2
---

# Phase 3 AIVSB OFF/ON Evaluation Protocol

## Purpose

Measure whether the Slice 2R retrieval-derived caption-style signal is safe,
reliable, and effective. Implementation tests prove contract correctness only.
Phase 3 does not authorize feature activation.

## Subject

The production subject is exactly
`5eed6e1823bc398084e8a46998186771a5970347`. OFF and ON use the same subject
code. The only Study A variable is `ENABLE_AIVSB_RETRIEVAL`.

Slice 2R performs no text injection. Phase 3 measures:

- `retrieval_return_coverage`: ON cases with returned IDs / 24;
- `signal_consumption_rate`: ON cases with nonnull `derived_signal` / 24;
- `retrieval_influence_rate`: cases where ON `caption_style` differs from OFF / 24.

`injected_chunk_ids` is a legacy compatibility field and must always equal `[]`.

## Three studies

### Study C: deterministic reliability

Run first, after execution authorization. Freeze cases for zero hits, retrieval
exception, no mappable domain, cross-novel-only hits, missing active manifest,
manifest mismatch, and provenance lookup setup failure. If a frozen expectation
fails, stop before Study A. Do not change runtime behavior inside the study.

### Study A: paired effectiveness

Run 24 frozen fixtures, 6 per novel. Each arm runs in a fresh subprocess with
identical fixture, index, stubs, source, model, and environment. OFF uses
`false`; ON uses `true` only inside its subprocess. Capture complete public
results and sink provenance. Continue all ordinary failures so denominators
remain complete.

### Study B: safety

Derive from the 24 Study A ON attempts. Do not make a second retrieval call.
Resolve returned/selected chunk metadata from the frozen index into a private
safety packet. Check public leakage, cross-novel selection, canon contradiction,
manifest identity, and fallback classification.

## Blinding

Quality reviewers receive only arm-neutral A/B public prose fields:
`caption`, `patreon_note`, `facebook_post`, and `x_post`. They do not receive
caption-style metadata, provenance, queries, IDs, or arm labels. Seal quality
grades before unblinding and safety review.

## Denominators

- effectiveness: 24 paired fixtures;
- retrieval/signal/safety: 24 ON attempts;
- OFF identity: 24 OFF attempts;
- reliability: every frozen Study C case;
- end-to-end eligibility: every attempted case, including failures.

Missing evidence is `NOT_MEASURED`, never omitted or passed.

## Hard boundaries

- normal runtime default remains OFF;
- no live Automation Tool database;
- no dirty source checkout;
- no ranking, embedding, query, mapping, composition, CTA, fallback, or schema
  changes during evaluation;
- no fixture freeze without its separate approval;
- no evaluation execution without manifest-bound approval;
- no activation, push, deployment, publication, or production writes.

## Current harness boundary

`scripts/aivsb/phase3_eval.py` is validation-only. It exposes
`capabilities`, `validate-candidates`, `freeze-preflight`, and
`execution-preflight`. It does not import `promo_copy`, build an index, freeze
fixtures, or execute a case. Action-capable freeze and run code require a later,
separately authorized implementation step.
