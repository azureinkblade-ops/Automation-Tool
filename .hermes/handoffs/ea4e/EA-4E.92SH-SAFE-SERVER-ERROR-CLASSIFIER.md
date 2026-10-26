# EA-4E.92SH safe server-error classifier candidate

Date: 2026-10-26

The one authorized 92SG tags-only run returned a local `/api/tags` HTTP 500
with a 99-byte JSON body. The body was neither emitted nor retained, and the
cause remains unknown. Its one-shot authorization is consumed.

This non-live successor maps a structured `error` string in a bounded JSON
server response to one fixed category: `permission_denied`,
`read_only_filesystem`, `missing_path`, `invalid_data`,
`other_server_error`, or `unclassified`. It emits only that category, HTTP
status, JSON content-type match, and byte length. It never emits the server
error text or body. Framing and CLI-output failures still fail closed without
classification. Categories are diagnostic hints, not proof of root cause.

The focused strict non-live suite passed 37/37, including five synthetic
category and body-redaction cases. The fixed tags-only entrypoint and pinned
image/model/CLI configuration are unchanged; the shared response parser is
changed and requires new independent source review. No native container,
inference, receiver, agent handoff, GPU, or production activation ran for this
candidate. A new exact one-shot authorization is required before native use.
Production remains HOLD.
