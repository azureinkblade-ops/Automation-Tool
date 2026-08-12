# VERSION.md

## Hermes Architecture Handbook

**Architecture Version:** 1.0.0  
**Status:** Draft – Under Review  
**Last Reviewed:** 2026-07-31

## Purpose

This document identifies the current architectural baseline for the Hermes platform. It tracks the version of the architecture itself—not the application.

## Current Phase

**Phase 0 – Architecture Foundation**

Current focus:

- Establish architectural principles
- Define governance boundaries
- Freeze core architectural decisions
- Create Architecture Decision Records (ADRs)
- Define implementation order

## Accepted Architecture Scope

The architecture currently defines:

- Governance model
- Authority model
- Memory architecture
- Review architecture
- Execution architecture
- Integration architecture
- Security architecture
- Event architecture

## Active Components

- Hermes Core (planned)
- LibreChat (interaction layer)
- Ollama (local inference)
- Obsidian (canonical knowledge)
- Anytype (operational projection)
- Open Interpreter (restricted execution)

## ADR Compatibility

The architecture is intended to be reviewed alongside:

- ADR-0001 through ADR-0012

## Documentation Versioning Policy

Patch versions:
- Documentation corrections
- Typos
- Clarifications

Minor versions:
- New architectural capabilities
- Additional documents
- New integration specifications

Major versions:
- Governance changes
- Authority changes
- Memory architecture redesign
- Event contract redesign
- Execution model redesign

## Change Control

No accepted architectural document should be materially changed without:

1. Review
2. Updated ADR (or amendment)
3. Version increment
4. Changelog entry

## Next Milestone

Complete review and acceptance of the Phase 0 architecture foundation before beginning Hermes Core implementation.
