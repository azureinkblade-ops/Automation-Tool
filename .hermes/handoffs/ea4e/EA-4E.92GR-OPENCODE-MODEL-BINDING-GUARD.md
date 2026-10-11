# EA-4E.92GR OpenCode Model-Binding Guard

Status: NON-LIVE SOURCE CHECKPOINT. Baseline
`3c68ed5802b1ac90920464d0e5ae25757052f495`. No receiver, provider,
model, network request, GPU, ComfyUI or production activation is authorized.

## Read-only model evidence

The interactive OpenCode state last recorded `providerID=opencode` and
`modelID=nemotron-3-ultra-free` on 2026-09-06. The global user config defines
Ollama models but no default model. This evidence does not establish the
currently selected model for a new session.

The separate EA-4E receiver config still names `ollama/qwen3:14b` in both
its top-level and named-agent model fields. Its SHA-256 observed during this
review was `bf98deaa2a8c052213a599716c5fa2d229bb89b72d7cb810e7b6a4cc178b7756`.
Interactive model selection does not silently rebind the governed receiver.
The frozen EA-4E.4 binding is Ollama-specific and its v1 provider policy
requires non-streaming calls; it cannot verify 92GQ's streamed capture path
or a hosted Nemotron successor without a reviewed contract roll.

## Scoped correction

The 92GQ entry previously accepted `expected_request_model` independently
of the authorization's `model_binding_id`. A caller could provide a new
request model while passing the unchanged binding ID through to the store.
92GR requires an injected binding verifier to return that exact model from
the supplied binding ID before the one-shot claim. An absent, failing, or
disagreeing verifier denies before a receiver start or credit consumption.
The only verifier in this tree is a test fake; this correction does not
create a trusted verifier or qualify any new model.

Existing authorizations and historical captures are not rewritten. The
capture remains default-disabled and all emitted manifests remain
`acceptance_eligible=NO` and `FAKE_INJECTED_NONLIVE`.

## Qualification

Focused fake tests prove missing, wrong, and throwing verifier denial,
including attempted Nemotron substitution under the old authorized model.
Record exact test counts and commit identity at checkpoint completion.

## Remaining boundary

Before a real capture, freeze a successor provider-binding schema and
canonical bytes tying exact provider ID, model ID, transport/streaming
contract, isolated receiver config, credential policy, egress policy, and
runtime identity to the authorization's `model_binding_id`. Supply a
trusted verifier for that frozen material; do not reuse the Ollama v1 hash.
Separately qualify current runtime selection, trusted issuer, enforced
egress, one-call accounting, process cleanup, and applicable GPU policy.
A hosted model name alone is not proof of those controls. A fresh exact
live authorization is required after these preflight gates pass.
