---
title: "Hermes Finding Normalizer"
document_id: "ARCH-FINDING-NORMALIZER"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-11"
---

# Hermes Finding Normalizer

The finding normalizer is the first deterministic consensus primitive. It converts findings carried by validated review reports into a canonical normalized finding set that a later agreement/disagreement evaluator can consume.

It is deterministic, read-only, evidence-bound, and non-authoritative.

## Scope

The normalizer answers one question: which distinct findings exist across the validated reviews for a single frozen evidence package, and which reviewers reported each one.

It does not decide agreement, disposition, acceptance, or escalation. Those belong to later milestones.

## Required invariants

- Input must come from validated review reports. The normalizer re-runs `ReviewReportValidator` against the frozen evidence package and rejects any report that does not validate.
- All input reports must bind to the same `task_id` and `evidence_package_id`.
- Normalization is deterministic. Equivalent input sets produce byte-identical output regardless of report ordering, finding ordering, or reviewer ordering.
- Normalization is read-only. No file writes, no ledger append, no task-state mutation.
- Normalization grants no governance authority and no execution authority.
- Source reviewer and source report references remain traceable for every normalized finding.
- Evidence artifact references remain traceable for every normalized finding.

## Canonical fields taken from the existing contract

The `hermes.review` schema defines each finding with `finding_id`, `severity`, `summary`, `evidence_refs`, and `confidence`. `recommendation` and `reviewer` are review-level fields, not finding-level fields.

Consequences for identity:

- **Severity is the canonical classifier.** The current finding contract has no `category` or `type` field. The normalizer does not invent one. If a category field is later added to `hermes.review`, it becomes part of the identity tuple at that time.
- **`finding_id` is reviewer-local and is not part of identity.** Two reviewers describing the same problem will use different ids. Source ids are preserved per source instead.
- **`recommendation` is review-level and is not part of finding identity.** Coalescing the same finding across reviewers who disagree on the recommendation is exactly the input the 6B evaluator needs to detect material disagreement. Recommendation is preserved per source.
- **`confidence` is a per-source signal, not identity.** Preserved per source.

## Deterministic identity

The normalized finding key is `finding-<first 16 hex of sha256>` over the canonical JSON of the identity tuple:

```json
{"evidence_refs": ["<sorted artifact ids>"], "severity": "<severity>", "summary": "<canonical summary>"}
```

Canonicalization rules:

- `summary` is stripped, internal whitespace is collapsed to single spaces, and the identity form is casefolded. When reviewers word the same finding with different casing or spacing, the lexicographically smallest stripped variant is chosen as the display summary, so the representative text does not depend on report ordering.
- `evidence_refs` are deduplicated and sorted.
- Serialization uses the existing `canonical_json` helper (sorted keys, compact separators, ASCII) and the existing `sha256_payload` helper, matching the `review-session-<hash16>` convention already used by the review session envelope.
- No timestamp and no runtime object identity participate in the key.

Two findings therefore coalesce only when severity, canonical summary, and evidence target set all match. Any material difference in those three keeps them distinct.

## Output ordering

Normalized findings are sorted by severity rank (`critical`, `high`, `medium`, `low`, `info`) and then by finding key. Sources within a finding are sorted by `(review_id, finding_id)`. Review ids on the set are sorted. The result is a frozen dataclass holding tuples, so the returned object cannot be mutated in place.

## Set hash

`finding_set_sha256` is `sha256_payload` over the normalized set document. It gives 6B and 6D a stable reference to the exact normalized input without persisting a new artifact.

## Rejection cases

`FindingNormalizationError` is raised for:

- no reports supplied
- a report that is not a JSON object or not valid JSON
- a report that fails review-report validation, including malformed reports, missing required finding fields, unknown evidence references, and prohibited authority claims
- reports that disagree on `task_id` or `evidence_package_id`

## Non-authority

The normalizer produces a plain data structure. It has no ledger handle, writes nothing, and emits no acceptance artifact, disposition, or authorization field. A normalized finding set is not a review outcome, not a consensus record, and not an acceptance artifact.

## Implementation

- `tools/hermes_core/finding_normalizer.py`
- `tests/hermes_core/test_finding_normalizer.py`

## Validated path

1. freeze the evidence package
2. validate each review report against that frozen evidence
3. normalize the validated reports into a canonical normalized finding set
4. hand the normalized set to the 6B agreement/disagreement evaluator
