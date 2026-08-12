---
title: "Hermes Repository Layout"
document_id: "ARCH-REPO"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Repository Layout

## Recommended structure

```text
hermes-core/
├── pyproject.toml
├── README.md
├── docs/
│   └── architecture/
├── src/
│   └── hermes/
│       ├── api/
│       ├── authorization/
│       ├── consensus/
│       ├── evidence/
│       ├── events/
│       ├── governance/
│       ├── integrations/
│       ├── memory/
│       ├── registry/
│       ├── review/
│       ├── state/
│       └── execution/
├── schemas/
│   ├── events/
│   ├── reviews/
│   ├── evidence/
│   ├── authorization/
│   └── execution/
├── policies/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── fixtures/
├── scripts/
├── examples/
└── .hermes/
    ├── state/
    ├── evidence/
    ├── audit/
    ├── reviews/
    └── projections/
```

## Source code boundaries

Modules should communicate through interfaces, not imports into internal implementation details.

## Generated artifacts

Generated evidence and state must not be mixed with source code.

Recommended rules:

- source: tracked;
- schemas and policies: tracked;
- accepted ADRs: tracked;
- runtime state: ignored or stored separately;
- test fixtures: tracked and explicitly classified;
- secrets: never tracked.

## Naming

- Python modules: `snake_case`
- schema files: `<domain>-v<major>.schema.json`
- events: `<domain>.<past_tense_action>`
- ADR files: `ADR-NNNN-short-title.md`
- evidence packages: `<task-id>/<phase>/<timestamp-or-run-id>/`

## Task workspace

```text
.hermes/tasks/TASK-0042/
├── request.json
├── authorization/
├── working/
├── evidence/
├── reviews/
├── consensus/
└── execution/
```

## Documentation storage

The authoritative handbook belongs under:

```text
docs/architecture/
```

Obsidian mirrors should link back to repository paths and hashes.
