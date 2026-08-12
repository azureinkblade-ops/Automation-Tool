---
title: "Hermes Ledger and Artifact Registry"
document_id: "ARCH-HERMES-LEDGER-REGISTRY"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Ledger and Artifact Registry

## Purpose

The Hermes ledger and artifact registry provide the first local persistence layer for the deterministic governance core.

They support Phase 1 of the architecture roadmap by giving validated state changes and evidence artifacts stable identities before any reviewer framework, worker, or external projection is introduced.

## Implementation

Code:

- `tools/hermes_core/hashing.py`
- `tools/hermes_core/ledger.py`
- `tools/hermes_core/registry.py`

Tests:

- `tests/hermes_core/test_ledger_registry.py`

## Event ledger

The event ledger is JSONL-backed and append-only through the public API.

Each entry records:

- sequence number
- event type
- task id
- occurred-at timestamp
- payload
- payload SHA-256
- previous entry SHA-256
- entry SHA-256

The ledger verifies:

1. sequence numbers are deterministic;
2. each entry points to the previous entry hash;
3. payload hashes match current payload content;
4. entry hashes match the complete entry envelope without the entry hash field.

Tampering with payload content, chain links, or entry hashes causes verification to fail.

## Artifact registry

The artifact registry records local file artifacts and their immutable identity.

Each artifact record includes:

- artifact id
- artifact path
- schema name
- file SHA-256
- registration timestamp
- metadata
- record SHA-256

The registry verifies:

1. the registry record has not been altered;
2. the referenced file still exists;
3. the current file hash matches the registered hash.

Missing or modified files cause verification to fail.

## Deterministic hashing

Payload and record hashes use canonical JSON with sorted keys and compact separators.

File hashes use SHA-256 over bytes read in chunks.

## Deliberate limits

This implementation does not create an event bus, run workers, publish content, call browser automation, write to Anytype, or update Obsidian.

It is local-only and exists to make later governance phases auditable.

## Verification

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 17 tests
OK
```
