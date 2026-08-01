---
title: "Hermes Review Model"
document_id: "ARCH-REVIEW"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Review Model

## 1. Objective

Automate evidence assessment without granting models approval authority.

## 2. Layered review

```text
Deterministic validation
        |
        v
Independent reviewer models
        |
        v
Report schema validation
        |
        v
Finding normalization
        |
        v
Deterministic consensus
```

## 3. Reviewer roles

### Technical reviewer

Focuses on dependencies, model loading, environment identity, reproducibility, and implementation correctness.

### Governance reviewer

Focuses on authorization scope, required artifacts, procedures, and state-transition compliance.

### Adversarial reviewer

Searches for unsupported claims, hidden fallbacks, omitted evidence, scope expansion, and contradictions.

## 4. Independence requirements

- same evidence root;
- no access to other reports;
- isolated sessions;
- distinct review role;
- model identity recorded;
- preferably diverse model families.

## 5. Report requirements

Every report includes:

- report ID;
- model identity;
- reviewer role;
- evidence root;
- policy hash;
- contract hash;
- recommendation;
- confidence;
- findings;
- exact evidence pointers;
- uncertainties;
- completeness declaration.

## 6. Dispositions

Reviewer recommendation:

- `ACCEPTABLE`
- `ESCALATE`
- `BLOCK`
- `INCONCLUSIVE`

These are recommendations only.

## 7. Finding structure

```yaml
finding_id: "F-001"
rule_id: "G3B-ENV-004"
category: "environment_isolation"
subject: "stage2-v2-runtime"
severity: "high"
claim: "Hermes site-packages were inherited."
evidence:
  - artifact: "environment-report.json"
    sha256: "..."
    pointer: "$.python.path"
confidence: 0.97
recommended_disposition: "BLOCK"
```

## 8. Consensus policy

Initial conservative policy:

- three valid reports required;
- deterministic status must pass;
- all reviewers must recommend acceptable;
- no critical or high findings;
- no material disagreement;
- each confidence above threshold;
- all evidence roots identical.

## 9. Material disagreement

Disagreement includes:

- conflicting severity;
- conflicting finding existence;
- conflicting interpretation of a required rule;
- different evidence identity;
- one reviewer reporting an unresolved high-risk uncertainty.

## 10. Adjudication

A separate adjudicator may assess normalized disagreement. It remains review-only. High-risk unresolved disagreement escalates to the human operator.

## 11. Calibration metrics

Track:

- false-clear rate;
- false-block rate;
- escalation rate;
- schema failure rate;
- citation validity;
- agreement by category;
- performance by model revision.

## 12. Model change policy

A changed model tag, digest, quantization, system prompt, review contract, or context strategy creates a new reviewer configuration requiring qualification.
