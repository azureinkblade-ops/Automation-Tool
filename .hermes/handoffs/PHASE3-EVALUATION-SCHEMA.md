---
status: DRAFT
attempt_schema_version: phase3-attempt-v2-slice2r
executed: false
phase3_execution_authorized: false
---

# Phase 3 Evaluation Schema

## Raw attempt record

```yaml
attempt_id: FX-EN-001__ON
fixture_id: FX-EN-001
arm: OFF | ON
subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
harness_commit: <sha>
frozen_manifest_sha256: <sha256>
started_at_utc: <timestamp>
completed_at_utc: <timestamp>
status: success | backend_failure | setup_failure | quarantined
public_result: <complete unchanged return object or null>
public_result_sha256: <sha256 or null>
evaluation_record: <sink object for ON; null for OFF>
error:
  class: <normalized class or null>
  message: <bounded message or null>
checks:
  public_schema_match: true | false | null
  recursive_leak_free: true | false | null
  off_identity_match: true | false | null
```

Raw attempts are authoritative and append-only.

## ON sink record

```yaml
retrieval_enabled: true
retrieval_attempted: true
retrieval_used: true | false
run_id: <id or null>
manifest_hash: <hash or null>
query: <private query>
returned_chunk_ids: [<ordered IDs>]
injected_chunk_ids: []
fallback_reason: null | no_hits | retrieval_error:<Class>
derived_signal: null | scene_hook | reader_question | stakes | character_moment | worldbuilding | catch_up
derived_signal_source_ids: [] | [<single selected ID>]
derived_signal_source_rank: null | <one-based rank>
derived_signal_source_domain: null | character | worldbuilding | location
signal_fallback_reason: null | no_mappable_domain | invalid_mapped_style
```

The query and IDs are private evidence. They never enter public output or blinded
quality packets.

## Derived metrics

- retrieval return: `returned_chunk_ids` nonempty;
- signal consumption: `derived_signal` nonnull;
- actual influence: ON `caption_style` differs from paired OFF;
- public leak: recursive value/key scan for private canaries, query, IDs,
  provenance keys, or retired delimiters;
- cross-novel violation: selected source novel differs from fixture novel;
- OFF identity: OFF public result matches the frozen subject's deterministic OFF
  contract for the fixture.

## Result states

```text
SAFETY: PASS | FAIL | NOT_MEASURED
RELIABILITY: PASS | FAIL | NOT_MEASURED
EFFECTIVENESS: PASS | FAIL | AMBIGUOUS | NOT_MEASURED
AUDIT_COMPLETENESS: PASS | FAIL
ACTIVATION_ELIGIBILITY: ELIGIBLE_FOR_SEPARATE_DECISION | BLOCKED | NOT_MEASURED
```

Every metric includes numerator, denominator, excluded count, and explicit
reason for each exclusion. Failures are not silently excluded.
