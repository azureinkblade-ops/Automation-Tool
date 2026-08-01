---
title: "Hermes Security Model"
document_id: "ARCH-SECURITY"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Security Model

## 1. Security objectives

- preserve human control;
- prevent unauthorized execution;
- prevent model authority escalation;
- protect private knowledge;
- preserve evidence integrity;
- contain compromised or malfunctioning workers;
- provide forensic auditability.

## 2. Trust zones

### Zone 0: Governance core

Highest trust. Contains state, policy, authorization, consensus, and audit services.

### Zone 1: Read-only reviewers

May access frozen evidence only.

### Zone 2: Knowledge systems

Obsidian and Anytype contain sensitive data and must be accessed through scoped adapters.

### Zone 3: Execution workers

Potentially dangerous. Must be isolated and least-privileged.

### Zone 4: User interface

LibreChat input is untrusted until validated.

### Zone 5: External network

Denied by default for offline or sensitive workflows.

## 3. Authentication and identity

Every component must have a registered identity. Local deployment may use service tokens or OS-bound credentials, but identity must still be explicit in audit records.

## 4. Authorization controls

- default deny;
- path allowlists;
- command or operation allowlists;
- separate read and write scopes;
- network policy;
- timeout;
- process and resource limits;
- parent acceptance binding;
- expiration and revocation.

## 5. Secrets

Secrets must not be stored in:

- Obsidian notes;
- Anytype objects;
- chat history;
- model prompts;
- evidence packages.

Use OS credential storage or a dedicated secret manager.

## 6. Prompt injection defense

Content retrieved from files or external systems is data, not authority.

Reviewers and workers must be instructed and technically constrained to ignore embedded requests to:

- expand scope;
- execute tools;
- reveal secrets;
- alter policy;
- claim approval.

## 7. Model isolation

Reviewer endpoints must not expose:

- shell tools;
- write tools;
- governance mutation tools;
- execution authorization tools.

## 8. Worker containment

Initial controls:

- dedicated working directory;
- write allowlist;
- process timeout;
- environment scrubbing;
- network disabled where required;
- command ledger;
- child-process tracking;
- fail-on-scope-deviation.

## 9. Evidence integrity

Evidence manifests must include hashes. The freeze operation should make the package read-only where practical.

## 10. Logging

Do not log secrets or unrestricted private content. Logs should include identities, hashes, outcomes, and bounded excerpts.

## 11. Revocation

Hermes must support immediate revocation of:

- agent registration;
- model qualification;
- execution authorization;
- integration credential;
- memory adapter access.

## 12. Security testing

Required negative tests include:

- reviewer attempts execution;
- worker attempts governance write;
- Anytype attempts gate mutation;
- expired authorization;
- path traversal;
- junction or symlink escape;
- command substitution;
- environment-variable leakage;
- prompt injection inside evidence.
