# Hermes Architecture

## Overview

The Hermes evidence package system is designed to manage and validate evidence packages. It consists of several key components, each responsible for a specific aspect of the system's functionality.

## Components

### Transition Recorder

The **Transition Recorder** (`tools/hermes_core/transition_recorder.py`) is responsible for managing transitions within the system. It ensures that all transitions are validated before being recorded in the ledger. The transition recorder performs the following tasks:

- **Artifact Validation**: Verifies that all artifacts associated with a transition are valid.
- **Transition Validation**: Ensures that the transition itself meets the required criteria.
- **Ledger Recording**: Writes valid transitions to the local ledger, ensuring an append-only record of system changes.
- **State Replay**: Reconstructs the latest task state from accepted transition events.

### Evidence Package Builder

The **Evidence Package Builder** (`tools/hermes_core/evidence_package_builder.py`) is responsible for creating frozen evidence packages. It hashes every artifact and the full package, validates against the `hermes.evidence` schema, and detects missing files, changed artifacts, and tampered package documents.

### Evidence Ledger Recorder

The **Evidence Ledger Recorder** (`tools/hermes_core/evidence_ledger_recorder.py`) verifies evidence packages before recording them in the ledger. It writes exactly one `evidence.frozen` ledger event for valid evidence and no event for invalid or tampered evidence. The recorder also supports replaying the latest frozen evidence by task ID.

### Evidence Staleness Checker

The **Evidence Staleness Checker** (`tools/hermes_core/evidence_staleness_checker.py`) reports whether frozen evidence is still review-eligible. It detects package hash mismatches, changed artifacts, and missing artifacts.

## Integration

These components work together to ensure that the Hermes evidence package system operates efficiently and securely. The transition recorder acts as a gatekeeper for all transitions, ensuring that only valid changes are recorded in the ledger.