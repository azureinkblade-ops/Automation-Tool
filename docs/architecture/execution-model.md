---
title: "Hermes Execution Model"
document_id: "ARCH-EXECUTION"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Execution Model

## 1. Principle

Execution is a privileged operation that occurs only after acceptance and a separate bounded authorization.

## 2. Execution envelope

```yaml
schema_version: "1.0"
task_id: "TASK-0042"
authorization_sha256: "<digest>"
parent_acceptance_sha256: "<digest>"
worker_id: "open-interpreter-01"
allowed_operations:
  - read_repository
  - run_existing_tests
  - calculate_sha256
allowed_paths:
  read:
    - "C:/Users/David/Documents/Automation tool/**"
  write:
    - "C:/Users/David/Documents/Automation tool/.hermes/TASK-0042/evidence/**"
network:
  mode: "deny"
fixtures:
  mode: "deny"
timeout_seconds: 300
expected_outputs:
  - ".hermes/TASK-0042/evidence/result.json"
prohibited:
  - dependency_install
  - governance_edit
  - git_push
  - deployment
```

## 3. Validation order

1. Parse schema.
2. Verify authorization hash.
3. Verify parent acceptance.
4. Verify current state.
5. Verify worker registration.
6. Normalize paths.
7. validate no path escapes;
8. apply environment restrictions;
9. launch worker;
10. record every command;
11. freeze outputs.

## 4. Worker behavior

The worker must stop when:

- a command is outside scope;
- a path is outside allowlist;
- network is attempted while denied;
- timeout is reached;
- required dependency is missing and install is not allowed;
- an expected precondition fails.

## 5. Command ledger

Each command record contains:

- sequence;
- normalized command;
- command hash;
- working directory;
- environment hash;
- start and end timestamps;
- exit code;
- stdout and stderr artifact references;
- child process information.

## 6. Write controls

Write access should be limited to:

- task-specific working directory;
- explicitly authorized source files;
- evidence output directory.

Governance, ADRs, accepted evidence, and frozen fixtures should be read-only unless separately authorized.

## 7. Rollback

Rollback strategy depends on operation:

- source edits: Git worktree or patch reversal;
- database changes: transaction or snapshot restore;
- generated artifacts: remove task-scoped outputs;
- environment changes: isolated disposable environment.

Rollback does not erase audit history.

## 8. Open Interpreter integration

Open Interpreter is a worker implementation, not the enforcement boundary. A wrapper must enforce the envelope independently of model compliance.

## 9. Post-execution

Execution results must be:

- inventoried;
- hashed;
- frozen;
- deterministically validated;
- independently reviewed when required;
- separated from acceptance of the prior phase.
