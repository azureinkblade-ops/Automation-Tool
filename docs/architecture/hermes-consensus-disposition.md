---
title: "Hermes Consensus Disposition"
document_id: "ARCH-CONSENSUS-DISPOSITION"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-11"
---

# Hermes Consensus Disposition

Architecture contract for the Phase 6C terminal consensus disposition. This is the third deterministic consensus primitive. It consumes the Phase 6B agreement/disagreement classification and the normalized finding set behind it, and maps them to a terminal governance disposition under the frozen ADR-0003 policy.

It is deterministic, evidence-bound, auditable, read-only, and non-authoritative with respect to execution. It must not generate acceptance artifacts (6D), mutate Hermes state or append ledger events (6E), or authorize execution. Acceptance disposition is not execution authorization.

## Inputs

- A valid Phase 6B `ConsensusEvaluation` (the `evaluation_sha256` must re-derive).
- The `NormalizedFindingSet` the evaluation references. Its `task_id`, `evidence_package_id`, and `finding_set_sha256` must match the evaluation and the set's own contents must re-derive.
- An optional `expected_review_count` carried from 6B, used only for a consistency check (it must match the evaluation's recorded value). 6C never invents a quorum.

## Canonical disposition vocabulary

The repository already owns the terminal disposition vocabulary; 6C does not invent parallel names.

- `consensus.schema.yaml` (line 35): `enum: [ACCEPTED, REJECTED, ESCALATED, BLOCKED, INCONCLUSIVE]`. UPPERCASE is the canonical serialization used by code and ADR-0003.
- `review_outcome.schema.yaml` (line 35) uses lowercase for the per-report recommendation; that is the review-outcome artifact, not the consensus disposition. 6C follows the consensus/ADR UPPERCASE form.
- ADR-0003 "Terminal outcomes" defines `ACCEPTED`, `ESCALATED`, `BLOCKED`, `INCONCLUSIVE`. `REJECTED` is present in the schema enum and is the disposition for a unanimous `reject` recommendation.

## Disposition rules

| 6B agreement class | Condition | Disposition | Reason codes |
| --- | --- | --- | --- |
| `deterministic_failure` | always | `BLOCKED` | `deterministic_failure` + the 6B reason codes preserved |
| `material_disagreement` | always | `ESCALATED` | `material_disagreement` + the 6B reason codes preserved (coverage + recommendation conflicts); no winning reviewer chosen |
| `unanimous_clean` | every required review reports the same recommendation `r` | `map(r)` | `unanimous_clean` + `unanimous_recommendation` |
| `unanimous_finding` | any finding is `critical` | `BLOCKED` | `critical_finding_present` (+ `unanimous_finding`) |
| `unanimous_finding` | no critical, any finding is `high` | `BLOCKED` | `high_finding_present` (+ `unanimous_finding`) |
| `unanimous_finding` | only `medium`/`low`/`info` findings, unanimous recommendation `r` | `map(r)` | `unanimous_finding` + `lower_severity_policy_resolved` |

where `map(r)`:

- `accept` -> `ACCEPTED`
- `reject` -> `REJECTED`
- `escalate` -> `ESCALATED`
- `inconclusive` -> `INCONCLUSIVE`

## Policy decisions (please review)

These are the two interpretive calls 6C had to make. They are documented here and in the plan notes because they could be contested; they follow the literal frozen policy and the non-invention rule.

1. **Blocking set is exactly {critical, high}.** ADR-0003 acceptance criteria enumerate only "no unresolved critical findings; no unresolved high findings." `medium`, `low`, and `info` are not listed as blocking. By the non-invention rule, they do NOT block. Therefore a `unanimous_finding` with only medium/low/info findings follows the unanimous-recommendation mapping. It is neither auto-`BLOCKED` nor auto-`ESCALATED`. The lower-severity path is recorded as `lower_severity_policy_resolved` so the decision is explicit and auditable. If a future separately authorized policy changes this, the mapping is a one-line edit in `_disposition_for_recommendation` / `_classify_unanimous_finding`; historical 6C semantics (critical/high blocking) are unaffected.

2. **Unanimous recommendation gates ACCEPTED.** ADR-0003 requires "unanimous acceptable recommendations." 6C maps the unanimous recommendation value rather than always emitting `ACCEPTED`. A unanimous `reject` yields `REJECTED`; a unanimous `escalate` yields `ESCALATED`; a unanimous `inconclusive` yields `INCONCLUSIVE`. 6B already freezes `recommendations` as a sorted tuple of distinct values, so when it reports `unanimous_clean`/`unanimous_finding` that tuple has exactly one element — the unanimous value — which 6C reads directly.

## Confidence handling

Confidence remains audit metadata in 6C. No numeric threshold exists in the repository (`review-model.md` section 8 requires one but none is defined), so 6C:

- preserves confidence for auditability (carried through from the normalized finding sources and review reports);
- performs no numeric threshold comparison;
- never silently excludes a low-confidence reviewer;
- never lets confidence change the terminal disposition;
- records a `confidence_threshold_not_defined` governance dependency.

A `confidence_policy` marker is included in the disposition document (`{enforced: false, reason: "numeric_threshold_not_defined"}`) for explicit audit visibility, consistent with the 6B/6C architecture contracts. No persisted schema addition is required; this is computed metadata.

## Required invariants

- Input is a valid Phase 6B `ConsensusEvaluation`.
- The normalized finding set must match the evaluation: `task_id`, `evidence_package_id`, and `finding_set_sha256`.
- The evaluation hash must re-derive.
- The finding-set hash must re-derive.
- Task identity and evidence-package identity must match across evaluation and finding set.
- Disposition is deterministic and order-independent (finding order, review order, reason-code order cannot change it).
- No model call, no reviewer adjudication, no majority-vote policy, no invented numeric confidence threshold.
- Critical/high severity policy is enforced exactly as documented.
- No acceptance artifact is generated; no ledger append; no state transition; no execution authority; no governance-authority grant to reviewers.

## Result contract

`ConsensusDisposition` (frozen dataclass):

- `task_id`, `evidence_package_id`
- `finding_set_sha256`, `evaluation_sha256`
- `agreement_class`
- `disposition` (one of the canonical UPPERCASE values)
- `reason_codes` (sorted tuple)
- `relevant_finding_keys` (all finding keys from the set)
- `blocking_finding_keys` (subset with critical/high severity)
- `blocking_severities` (sorted tuple of distinct severities among blocking findings)
- `confidence_policy_marker` (the deferred-policy marker)
- `disposition_sha256`

Helpers: `as_document()`, `is_blocked()`, `is_escalated()`, `is_accepted()`, `is_rejected()`, `is_inconclusive()`.

## Deterministic hashing

The disposition hash binds at minimum: the Phase 6B `evaluation_sha256`, the Phase 6A `finding_set_sha256`, the terminal `disposition`, the sorted `reason_codes`, and the blocking finding references. It reuses `hashing.sha256_payload` over a single canonical document helper so the public document and hashed document cannot drift. The hash field is excluded from its own input; all collections are sorted. At least one hash value is pinned in tests and independently re-derived in an ad-hoc probe.

## Out of scope

Acceptance artifact generation (6D), state transition to `CONSENSUS_CALCULATED`/`ACCEPTED` (6E), ledger recording (6E), execution authorization, reviewer adjudication, majority-vote consensus, confidence calibration, model calls, Kilo/Codex/Copilot routing, Ollama integration, Obsidian memory promotion, Anytype projection, application or posting workflow changes, browser automation.
