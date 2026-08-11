---
title: "Hermes Consensus Evaluator"
document_id: "ARCH-CONSENSUS-EVALUATOR"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-11"
---

# Hermes Consensus Evaluator

The consensus evaluator is the second deterministic consensus primitive. It consumes the normalized finding set produced by the finding normalizer and classifies what the validated reviewer inputs represent: agreement, material disagreement, or deterministic failure.

It is deterministic, read-only, evidence-bound, auditable, and non-authoritative.

## Scope

The evaluator answers exactly one question:

> Given a valid, normalized, evidence-bound set of reviewer inputs, what deterministic agreement/disagreement class do they represent?

It does not map that class to a terminal governance disposition, generate acceptance artifacts, mutate task state, append ledger events, authorize execution, or adjudicate between reviewers. Terminal disposition is milestone 6C. Acceptance artifacts are 6D. Ledger/state integration is 6E.

## Terminology: what already exists versus what this document introduces

The repository already owns most of the consensus vocabulary. This evaluator reuses it and does not create parallel names.

Already defined, and therefore **not** redefined here:

| Term | Defined by | Meaning in that contract |
|---|---|---|
| `ACCEPTED`, `ESCALATED`, `BLOCKED`, `INCONCLUSIVE` | ADR-0003, `consensus.schema.yaml`, `state-machine.md` | Terminal consensus results. These are **6C disposition** names, not 6B agreement classes. |
| `accept`, `reject`, `inconclusive`, `escalate` | `review.schema.yaml` `recommendation` enum | A single reviewer's review-level recommendation. |
| `accepted`, `rejected`, `inconclusive`, `escalated`, `blocked` | `review_outcome.schema.yaml` `status` enum | Local review-outcome disposition. |
| material disagreement | ADR-0003, `review-model.md` section 9 | Disagreement beyond the top-level recommendation: conflicting severity, conflicting finding existence, different evidence identity, conflicting rule interpretation. |
| reviewer quorum | ADR-0003 ("three required independent review reports"), `review_assignment.py` (`minimum_reviewers=3`), `reviewer_registry.require_active_count()` | The required number of independent reviews. |

Introduced by this document, because these names exist nowhere in the repository:

| Term | Meaning |
|---|---|
| `unanimous_clean` | Every required review is valid and no normalized findings exist. |
| `unanimous_finding` | Every required review is valid, all required reviewers reported the same normalized findings, and recommendations do not materially conflict. |
| `material_disagreement` | Required reviewers differ in a way that could affect governance disposition. |
| `deterministic_failure` | A structural or governance contract violation, not reviewer disagreement. |

These four are **agreement classes**, deliberately distinct from the terminal disposition vocabulary. Keeping them separate is what prevents 6B from silently pre-empting 6C: an agreement class describes the shape of the reviewer inputs, while a disposition describes what governance decides to do about it.

### Recorded contract divergence

`review-model.md` section 6 lists reviewer recommendations as `ACCEPTABLE`, `ESCALATE`, `BLOCK`, `INCONCLUSIVE`. The implemented `review.schema.yaml` enum is `accept`, `reject`, `inconclusive`, `escalate`. The implemented schema is authoritative for code, so the evaluator reasons over the schema enum. This divergence is recorded rather than silently resolved; reconciling the prose document is a separate documentation concern.

## Required invariants

- Input is a deterministic normalized finding set produced by the finding normalizer.
- Input review reports must already be valid and evidence-bound; the evaluator re-validates them against the frozen evidence package rather than trusting the caller.
- All evaluated reviews must bind to the same `task_id` and the same `evidence_package_id`.
- The normalized set must correspond to the supplied reviews: its `task_id`, `evidence_package_id`, and `review_ids` must match, and its `finding_set_sha256` must re-derive from its own contents.
- Evaluation is deterministic. Report ordering, reviewer ordering, and finding ordering cannot change the result.
- Evaluation is read-only: no file writes, no ledger append, no state transition.
- No acceptance artifact is generated.
- No execution authority and no governance authority is produced or granted.
- No model call occurs. Classification is pure comparison over validated data.
- No adjudication occurs. The evaluator never decides which reviewer is correct.
- Material disagreement remains explicit and is never silently resolved into agreement.

## Expected review population

The evaluator does not invent a quorum. `expected_review_count` must be supplied by the caller from existing policy or assignment data (ADR-0003's three required reviews, or `ReviewAssignmentPlan`). When it is supplied and fewer valid reviews are present, the result is `deterministic_failure` with reason code `missing_required_review`.

When `expected_review_count` is omitted, the evaluator classifies only the reviews it was given and records `expected_review_count: null`. It does **not** silently assume three. Omitting the expectation is therefore a caller decision to evaluate an unbounded review set, not an implicit policy.

### Governance dependency (unresolved upstream)

ADR-0003 requires "no unresolved critical findings" and "no unresolved high findings" for acceptance, and `review-model.md` section 8 additionally requires "each confidence above threshold". No numeric confidence threshold is defined anywhere in the repository. The evaluator therefore does **not** apply a confidence threshold, and does not treat critical/high severity as blocking — both are acceptance-policy concerns that belong to 6C disposition, where the severity policy is applied to an already-classified agreement result. This is recorded as a governance dependency rather than resolved by invention.

## Agreement classes and precedence

Classification is evaluated in a fixed precedence order so the result is unambiguous:

1. **`deterministic_failure`** — any structural violation. Checked first, because a structurally broken input set cannot meaningfully be said to agree.
2. **`material_disagreement`** — reviewers differ materially.
3. **`unanimous_finding`** — all required reviewers reported the same normalized findings.
4. **`unanimous_clean`** — all required reviewers valid and no findings exist.

### Material disagreement causes

Each cause emits a deterministic reason code:

| Reason code | Condition |
|---|---|
| `finding_coverage_conflict` | A normalized finding was reported by at least one review but not by every review in the evaluated set. This single rule covers the plan's "one clean review plus one finding-bearing review", "different normalized finding sets", "partial overlap", "different severity kept distinct by 6A", and "different evidence targets" — because 6A already encodes severity and evidence target into finding identity, so any of those differences surfaces here as unequal coverage. |
| `recommendation_conflict` | Reviews carry more than one distinct review-level recommendation. |

`recommendation_conflict` is evaluated independently of findings, so two reviews that agree perfectly on findings but split `accept` versus `reject` are still material disagreement — which is precisely why 6A preserves recommendation per source.

### Deterministic failure causes

| Reason code | Condition |
|---|---|
| `missing_required_review` | Fewer valid reviews than `expected_review_count`. |
| `duplicate_review_id` | The same `review_id` appears more than once. |
| `duplicate_reviewer_identity` | The same reviewer `agent_id` submitted more than one review, violating the independence requirement. |
| `task_id_mismatch` | Reviews or the normalized set disagree on `task_id`. |
| `evidence_package_mismatch` | Reviews or the normalized set disagree on `evidence_package_id`. |
| `review_id_mismatch` | The normalized set's `review_ids` do not match the evaluated reviews. |
| `finding_set_hash_mismatch` | `finding_set_sha256` does not re-derive from the normalized set contents. |
| `invalid_review_report` | A review fails `ReviewReportValidator` against the frozen evidence, including prohibited authority claims. |

Structural problems that make the input fundamentally unusable — a missing normalized set, a wrong type, or an unreadable report — raise `ConsensusEvaluationError` instead of returning a classification, matching the 6A convention where malformed input is an error rather than a result.

### Handling of `inconclusive` and `escalate`

These are permitted recommendation values in the implemented schema and are **not** silently converted into pass or fail. They participate in exactly one rule: distinctness. Every permitted combination of the four recommendation values is enumerated as:

- all reviews share one recommendation value (any of `accept`, `reject`, `inconclusive`, `escalate`) → no recommendation conflict
- reviews carry two or more distinct values → `recommendation_conflict` → `material_disagreement`

A unanimous `inconclusive` therefore yields `unanimous_clean` or `unanimous_finding` at 6B, carrying the unanimous recommendation forward for 6C to map to a disposition (very likely `INCONCLUSIVE`). 6B does not make that mapping, and unanimity of an inconclusive recommendation is explicitly not treated as acceptability.

## Agreement matrix

| Situation | 6B result |
|---|---|
| All required reviewers valid, no findings, one shared recommendation | `unanimous_clean` |
| All required reviewers report the same normalized findings, one shared recommendation | `unanimous_finding` |
| Same normalized finding, conflicting recommendations | `material_disagreement` (`recommendation_conflict`) |
| Different normalized finding sets | `material_disagreement` (`finding_coverage_conflict`) |
| One clean review, one finding-bearing review | `material_disagreement` (`finding_coverage_conflict`) |
| Partial finding overlap | `material_disagreement` (`finding_coverage_conflict`) |
| Different severity for otherwise identical finding | `material_disagreement` (`finding_coverage_conflict`) |
| Different evidence target for otherwise identical finding | `material_disagreement` (`finding_coverage_conflict`) |
| All reviews unanimously `inconclusive` or `escalate`, no findings | `unanimous_clean` (recommendation carried forward, not interpreted) |
| Fewer valid reviews than `expected_review_count` | `deterministic_failure` (`missing_required_review`) |
| Duplicate review id or duplicate reviewer identity | `deterministic_failure` |
| Task or evidence package mismatch | `deterministic_failure` |
| Normalized set review ids or hash inconsistent | `deterministic_failure` |
| Invalid review report or prohibited authority claim | `deterministic_failure` (`invalid_review_report`) |

## Result contract

`ConsensusEvaluation` is a frozen dataclass holding tuples:

- `task_id`, `evidence_package_id`, `finding_set_sha256`
- `agreement_class`
- `review_ids` (sorted), `reviewer_agent_ids` (sorted)
- `expected_review_count` (or `None`)
- `finding_agreements`: per normalized finding, the finding key, severity, the sorted reviews that reported it, the sorted reviews that did not, and whether coverage is unanimous
- `recommendations`: sorted distinct review-level recommendation values
- `recommendation_conflict`: bool
- `reason_codes`: sorted deterministic codes
- `evaluation_sha256`

Explicitly absent: any acceptance artifact, disposition, authority field, execution authorization, model-generated rationale, adjudicated override, or mutable runtime state.

## Evaluation hash

A hash is included because 6D must bind an acceptance artifact to the exact consensus decision that justified it, and 6E must reject tampered consensus. `evaluation_sha256` is `sha256_payload` over the evaluation document excluding the hash field itself, using the same shared helper that builds the public document so the two shapes cannot drift. All ids and collections are sorted; no timestamp and no runtime identity participate.

## Implementation

- `tools/hermes_core/consensus_evaluator.py`
- `tests/hermes_core/test_consensus_evaluator.py`

## Validated path

1. freeze the evidence package
2. validate each review report against that frozen evidence
3. normalize the validated reports into a canonical normalized finding set
4. evaluate agreement/disagreement over the normalized set and validated reviews
5. hand the evaluation to the 6C terminal disposition mapper
