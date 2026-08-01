# ADR-0008 Ollama Provides the Initial Local Model Runtime

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Local inference
* **Related:** ADR-0002

## Context

The system needs local models for planning, technical review, adversarial review, coding assistance, and evidence analysis.

The user prefers local and low-cost operation and has an NVIDIA RTX 4080 with approximately 16 GB of VRAM.

## Decision

Ollama will provide the initial local model-serving layer.

Initial model roles:

* Qwen-family model for primary technical review and general reasoning;
* DeepSeek-R1 14B distilled model for adversarial review;
* Qwen coder model for coding work;
* smaller model for lightweight classification or preliminary triage where justified.

Agents must access models through a Hermes-controlled model adapter rather than embedding Ollama-specific behavior throughout the system.

## Model identity requirements

Every registered model must include:

* model name;
* Ollama tag;
* model-family identity;
* quantization;
* local digest where available;
* context configuration;
* intended roles;
* installation date;
* qualification status.

A model update creates a new qualified identity. It must not silently replace the model used for prior evidence.

## Consequences

### Positive

* Local inference reduces recurring API cost.
* Models can operate without sending private vault data externally.
* Ollama provides a simple installation and serving interface.

### Negative

* Model quality and structured-output reliability vary.
* VRAM limits restrict model size and context.
* Model tags may change unless identities are recorded carefully.
* Ollama must not become the authority for model eligibility.

## Portability

Hermes must use a model-provider abstraction so that Ollama can later coexist with or be replaced by another local inference runtime without redesigning governance.
