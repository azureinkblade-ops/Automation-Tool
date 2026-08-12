---
title: "Hermes Review Outcome Record"
document_id: "ARCH-REVIEW-OUTCOME"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-02"
---

# Hermes Review Outcome Record

The Hermes review outcome record is a local, non-authoritative record that binds one or more validated review reports to a frozen evidence package and captures the local disposition for that task.

## Scope

The record is used only to make a review outcome explicit and auditable. It does not modify governance state, authorize execution, or execute any model or worker.

## Required invariants

- A review outcome must bind to the same `task_id` and `evidence_package_id` as the frozen evidence package.
- Every referenced `review_id` must resolve to a validated review report for the same evidence package.
- The record must remain read-only and non-authoritative.
- The outcome must be stored as a local deterministic artifact, not as a runtime configuration change.

## Implementation

- `tools/hermes_core/review_outcome.py`
- `tests/hermes_core/test_review_outcome.py`

## Validated path

1. freeze the evidence package
2. validate the review report against that frozen evidence
3. build the review outcome record with the matching `review_ids`
4. validate the outcome using the evidence package and review report chain
