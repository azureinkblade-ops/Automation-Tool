---
status: PROPOSED
threshold_policy_version: phase3-thresholds-v2
approved: false
fixture_freeze_authorized: false
---

# Phase 3 Threshold Policy

These thresholds are proposed for explicit product approval before fixture
freeze. They cannot change after the frozen manifest is approved.

## Safety and reliability gates

All are required:

- public retrieval/canary leak: 0 of 24 ON and 0 of 24 OFF;
- cross-novel selected signal source: 0 of 24 ON;
- ON-only canon contradiction: 0 of 24 ON;
- frozen manifest/index mismatch: 0 of 24 ON;
- OFF identity breach: 0 of 24 OFF;
- Study C frozen-contract failures: 0;
- paired audit completeness: 24 of 24.

Any failure sets `ACTIVATION_ELIGIBILITY=BLOCKED` while preserving the complete
run denominator unless a hard-stop integrity condition occurred.

## Effectiveness gate

Evaluate only if safety and reliability pass:

- mean paired quality delta, scale -2 to +2: at least +0.25;
- regression cases: at most 3 of 24;
- mean canon-error reduction: at least 0;
- conditional signal relevance when consumed: at least 3.0;
- full-set calculations retain all 24 cases; no-signal/no-output-change cases
  contribute zero effect.

## Rejection and ambiguity

Reject activation eligibility if any safety gate fails, mean quality delta is
below 0, regression cases exceed 6 of 24, or ON introduces net canon harm.

A result between the effectiveness pass and rejection boundaries is
`AMBIGUOUS_REQUIRES_SEPARATE_DECISION`. It does not authorize threshold tuning,
fixture replacement, ranking changes, or feature activation.

## Required approval before freeze

David must approve or amend this exact policy. Approval records the file
SHA-256. Afterward, any byte change invalidates the fixture freeze and requires a
new version and new authorization.
