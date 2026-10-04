# EA-4E.92CR Kilo request-shape probe prepared

Status: NON-LIVE PREPARATION / RECEIVER LAUNCH NOT AUTHORIZED
Source checkpoint: `97b68a9c8473a271c6dc9ff8cc5a769a1459bc3a`

A fresh, credential-free probe home was created outside the repository at
`C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-shape-probe-92cr-20261004`.
It uses the pinned Kilo 7.8.3 executable, the inert model and dummy-only
provider config, a fresh home/agent profile, and loopback port 49322.
The 92CP fake provider source is prepared to record a privacy-bounded
request-shape summary if a *new* one-shot receiver probe is later approved.

Frozen preparation identities:

- plan SHA-256: `339e0a1b0a9fdc66bd368a62f89433ce5f0db92e8c9ae808b1826b41b52c0338`
- config SHA-256: `21174acb8422b4459404244050133ed02d58eaafe4f47bfc2c632709759dba32`
- executable SHA-256: `8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a`
- model: `openai-compatible/ea4e-inert`
- local provider: `127.0.0.1:49322` only

At post-preparation verification, `launch_authorized`,
`network_isolation_verified`, and `real_provider_calls_authorized` were all
false; `attempt.json` and `probe-result.json` were absent; no Kilo process
was observed. No receiver, real provider, model, GPU, or ComfyUI operation
occurred. The previous 92CM home and consumed claim were not touched.

This plan is **not launchable by the committed 92CM runner**, whose root and
port checks are pinned to the consumed 92CM home. Before any 92CR run, a
separate runner revision must be reviewed and fake-tested against this exact
fresh root/port, and the operator must issue a new bounded authorization
covering one Kilo process, timeout, output cap, dummy provider, egress-risk
decision, and no retry. Do not infer permission from the presence of this
plan. The same-user loopback peer-identity decision and independent 92S
mapped-byte HOLD remain open.
