---
status: DRAFT
quality_rubric_version: phase3-quality-rubric-v2
safety_rubric_version: phase3-safety-rubric-v2
fixture_freeze_authorized: false
---

# Phase 3 Scoring Rubric

## Review separation

Quality review is blinded. Safety review is unblinded and starts only after the
quality grades are sealed. The two evidence packets must never be merged.

Preferred protocol: two independent quality reviewers plus adjudication.
Fallback: one reviewer plus a six-fixture repeat subset frozen before scoring.
Reviewer identity, rubric hash, timestamp, grade, evidence note, fixture, and
output field are required for every verdict.

## Quality fields

Score `caption`, `patreon_note`, `facebook_post`, and `x_post` separately.

For each A/B pair, record:

- hook clarity: -2 to +2 comparative delta;
- novel specificity: -2 to +2;
- platform fit/readability: -2 to +2;
- CTA/release-objective preservation: pass/fail;
- repetition/template drag: -2 to +2;
- overall preference: A | B | TIE;
- bounded textual evidence note.

Per-case continuous quality is the mean of applicable field deltas. Per-case
regression is worst-of across platforms so one harmed platform cannot be hidden
by averaging.

## Signal relevance

For ON cases with a consumed signal, safety reviewers score whether the selected
source domain and derived caption style fit the frozen fixture:

```text
0 actively wrong or harmful
1 irrelevant
2 weakly related
3 relevant
4 strongly useful
5 direct, specific support
```

No consumed signal is recorded as `NOT_APPLICABLE` for conditional relevance and
zero effect in full-set effectiveness. It is never dropped from the 24-case
quality denominator.

## Safety verdicts

Each ON case records:

- public retrieval/canary leak: pass/fail;
- selected-source novel isolation: pass/fail/not applicable;
- canon contradiction introduced by ON: pass/fail;
- manifest/run identity: pass/fail;
- returned-order and selected-rank provenance: pass/fail/not measured;
- retrieval fallback classification: valid/invalid/not applicable;
- signal fallback classification: valid/invalid/not applicable.

Canon authority is the frozen reviewed canon packet, not the retrieved text.

## Audit rule

A verdict without paired public output or private source evidence reference,
grade, note, reviewer, rubric hash, and timestamp is
`INVALID_PENDING_AUDIT`. It cannot enter aggregate pass counts.
