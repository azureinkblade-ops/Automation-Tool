---
title: "AUTH-2026-08-11 Hermes Finding Normalizer"
document_id: "AUTH-2026-08-11-HERMES-FINDING-NORMALIZER"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-11"
---

# AUTH-2026-08-11 Hermes Finding Normalizer

This authorization permits a tightly scoped finding normalizer implementation as Phase 6 milestone 6A.

## Authorized scope

1. Add a local, deterministic finding normalizer under `tools/hermes_core/**`.
2. Add a focused unit test file under `tests/hermes_core/**`.
3. Document the finding normalizer contract under `docs/architecture/**`.
4. Export the new types from the `tools/hermes_core` package and list the new document in the architecture index.
5. Require validated review reports bound to a single frozen evidence package as the only accepted input.

## Explicit prohibitions

- No `app.py` changes.
- No posting workflow changes.
- No browser automation.
- No external services.
- No new schema file. The normalized finding set stays an internal deterministic object in this milestone.
- No ledger append, no state transition, no acceptance artifact generation.
- No consensus, agreement, disagreement, or disposition logic. Those are milestones 6B and 6C.
- No authority to authorize execution, modify state, or execute reviewer models.
