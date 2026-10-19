# EA-4E.92NI distinct inert client identity qualification

Status: NON-LIVE TEST EVIDENCE / PRODUCTION HOLD.
Parent: `9212817c082edfd0f9cab335d5a8ddf78df449fe`.

The prior 92NH fixture used a same-process client. This fixture launches a
separate copy of its own inert compiled test program, creates one random
local pipe, sends three fixed bytes, and keeps the child connected until
the server completes its observation. The 92NH composition reads first,
then invokes the existing read-only kernel client-process lease observer on
that same handle. It compares the kernel PID and creation time to the
retained exact child process. A modified expected PID and a modified expected
creation time each deny and return no frame.

The child is only a test process, not Kilo, OpenCode, a protected app, or a
model. The fixture releases and waits for the exact child, killing that exact
child only if cleanup times out. It does not create a protected pipe or issuer,
verify token/package identity, parse the 92NE canonical frame, or issue
authority. Strict 92AT mapped-byte proof and production activation remain
on HOLD.
