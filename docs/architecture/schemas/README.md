# Hermes Governance Schemas

These schema files define the first stable object contracts for the Hermes agent-to-agent pipeline.

They are architecture contracts, not runtime implementation code. Runtime validators should be generated or written against these contracts later.

## Required separation

- A review is not an approval.
- Consensus is not authorization.
- Acceptance is not execution.
- Execution success is not acceptance.
- Memory is not governance authority.

## Schema set

- `task.schema.yaml`
- `review.schema.yaml`
- `consensus.schema.yaml`
- `acceptance.schema.yaml`
- `authorization.schema.yaml`
- `execution.schema.yaml`
- `evidence.schema.yaml`
- `agent.schema.yaml`
- `event.schema.yaml`

## Current status

Status: architecture foundation

The first four ADRs are accepted. These contracts are the next foundation layer before any autonomous workflow or publishing integration.
