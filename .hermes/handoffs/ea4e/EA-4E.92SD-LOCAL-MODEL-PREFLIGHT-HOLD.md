# EA-4E.92SD local-model preflight HOLD

Date: 2026-10-26

David authorized exactly one synthetic local-model smoke against source commit
`539388100e06a2d386e587b7f01d23fb8db5f7a1`, after correcting an
earlier mistyped commit prefix. The entrypoint SHA-256 was
`dd2a5e95cb945f19212527519128a4093202c3a54d89c64a9ab0f14d46210350`;
the Docker CLI SHA-256 was
`c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`;
the image was
`ollama/ollama@sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da`.
The staged six-file `qwen3:14b` inventory was revalidated before launch.

The one authorized invocation exited 1 in about nine seconds. It stopped
while validating the local `/api/tags` HTTP response in `_http_json` with
`SmokeDenied("local Ollama HTTP response invalid")`. It never reached
`/api/generate`; no model inference or agent handoff occurred. The failure
reason within HTTP validation is unknown because the pinned runtime did not
report status, content type, or body length. The launcher completed its
exact-owned-container cleanup, and a separate read-only Docker query found
no remaining `ea4e92rm-` container. No retry is authorized.

The unrun diagnostic successor changes only the error to report HTTP status,
whether content type is JSON, and body byte count, never the body. A focused
strict non-live fake suite passed 29/29, including a response-body secrecy
test. These tests do not establish native-model readiness. The successor
requires a narrow commit, fresh independent source review, and a new exact
one-shot authorization before any native retry. Production remains HOLD.
