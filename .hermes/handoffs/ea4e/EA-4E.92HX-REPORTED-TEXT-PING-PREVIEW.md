# EA-4E.92HX Reported Text Ping Preview

Status: NON-LIVE / NO RESULT PUBLICATION / PRODUCTION_READY=NO.

`preview_reported_text_ping_candidate` reads bounded reported stdout bytes,
requires a zero exit code and strict UTF-8, runs the existing Kilo or
OpenCode JSONL parser, and validates the inner result against the exact
instance-bound ping schema. A valid candidate is returned for inspection
only. This path cannot write terminal capture, delegation result, or
originator mailbox state.

Qualification: 8 focused tests; 198 affected tests passed, 0 failed.
Malformed bytes/JSONL, an error event, plain PONG, nonzero exit, and a
wrong-task result all deny. Tests use fabricated process reports; no real
receiver or model was invoked.

The report store has not independently proved that a controlled process
produced its bytes. A concrete owner must establish that provenance and
durably account for crash, cancellation, and process containment before
any preview candidate may be promoted to trusted capture or delivery.
