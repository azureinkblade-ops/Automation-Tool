# EA-4E.92CR Kilo request-shape probe result

Status: ONE-SHOT INERT HOST PROBE COMPLETE / PRODUCTION HOLD
Probe source commit: `1db07f9184d1bf01ea9519e94ecb977bf65da1a6`
Prepared root: `C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-shape-probe-92cr-20261004`

The operator authorized one Kilo 7.8.3 process against only the dummy
loopback provider on port 49322, accepting that OS-level outbound isolation
was not proved. The limits were 30 seconds, 4 MiB stdout, 128 KiB stderr,
sanitized request-shape capture, and no retry. Before launch, the plan,
config, and executable SHA-256 values matched the 92CR preparation record;
the one-shot claim and result were absent; the port was free. The committed
fake-only affected suite passed 86 tests with 3 skips.

## Observed result

- The launcher wrote the durable claim before starting the child. Its SHA-256
  is `ced9cc862abadbb61bc86238ca2bb75cf1d56d5b23bdda73508d8d8a3a41f2d6`.
- One Kilo PID (51336) exited 0 in 5.338 seconds. The exact inert marker was
  present. There was no timeout, output overflow, or capture error.
- The fake provider observed exactly one `POST /v1/chat/completions`, returned
  200, and saw `stream: true`. No automatic retry was recorded.
- The sanitized request body was 64,878 bytes, 658 bytes below the probe's
  65,536-byte cap. Its SHA-256 is
  `a683a99dd24ec4ccbc43758357168ef1e045d1eab022ed0cdbcb5342ab0e8690`.
  It contained two messages (one system, one user), with content kinds string
  and array. Observed top-level field types were `model` string, `messages`
  array, `stream` boolean, `stream_options` object, `tools` array,
  `tool_choice` string, and `max_tokens` number. The sanitizer recorded no
  unknown top-level or message fields. It did not persist prompt text or the
  dummy authorization header.
- The loopback listener closed and the recorded Kilo PID exited. Production
  activation remained false. The sanitized result SHA-256 is
  `3f63835fce2e3f5bd34ea51f463707ee2bdd2808d63edab38eb47dc11edad29b`.

Kilo rewrote the isolated dummy config after launch, adding a `$schema` field
and formatting the JSON; its post-run SHA-256 is
`0c92015a2f9d79aa7a8a89ce9a212b626c36c65e182aebfc6ed62be26027e15d`.
The model, dummy key, and loopback URL remained the same. This config drift
initially made read-only replay validation fail on config identity before it
reached the consumed-claim check. A follow-up change moved the durable claim
check first without restoring the config or enabling another run. The affected
fake-only suite then passed 86 tests with 4 skips; read-only validation now
reports `one-shot probe already claimed`.

## Qualification boundary

This proves the observed dummy custom-provider request shape for this pinned
Kilo build and one inert prompt only. It does not prove zero host egress or
absence of all real model activity, although the configured endpoint and one
observed response were dummy-local. It does not qualify a production gateway,
upstream credential, larger/different prompts, a fixed 65,536-byte production
body cap, process-bound peer identity, or the independent 92S mapped-byte
requirement. The 92CR claim is consumed; no retry or second Kilo process is
authorized. Any further receiver or provider operation requires separate
exact authorization.
