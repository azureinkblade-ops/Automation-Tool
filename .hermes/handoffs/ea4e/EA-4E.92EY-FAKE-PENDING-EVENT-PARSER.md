# EA-4E.92EY Fake Pending Event Parser

Status: SOURCE-ONLY EVENT-SHAPE PASS / EVENT AUTHENTICITY HOLD
Baseline before this change: `494ed90ae7a1b096be2e6f17b7fcfee7885e7d95`
Date: 2026-10-08 (America/Phoenix)

`kilo_fake_pending_event.py` accepts only one bounded newline-terminated JSON
event with the exact four fields emitted by the 92EW fake gateway. Duplicate
keys, extra fields, noncanonical/non-IPv4 peers, empty or oversized body
length, malformed/lowercase-incorrect SHA-256, and extra log lines deny. The
result carries only peer IP, body length, and body digest; it has no authority
or peer-qualified flag. The parser does not read Docker, open a socket, invoke
a receiver, or treat stdout as authenticated evidence.

Focused fake-only tests for the new parser plus raw peer and scoped reader:
44 passed, 0 failed. No container, receiver, model, provider, GPU, ComfyUI,
or production activation ran. The previously built 92EX image remains tied to
committed 92EW source; this parser is host-side and does not alter that image.

Next: a fake-only coordinator must bind one exact container event to an
expected image and request attempt, use fresh scoped daemon reads before any
release, and fail closed on timeout, change, or cleanup failure. Even that
would be an inert-probe result, not a production trust claim.

`EVENT_SHAPE_PARSER=PASS`
`EVENT_SOURCE_AUTHENTICATED=NO`
`PEER_QUALIFIED=NO`
`SEND_AUTHORIZED=NO`
`PRODUCTION_READY=NO`
