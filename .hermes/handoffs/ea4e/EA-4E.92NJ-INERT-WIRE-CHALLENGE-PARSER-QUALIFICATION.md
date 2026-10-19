# EA-4E.92NJ inert wire challenge parser qualification

Status: NON-LIVE CROSS-LANGUAGE FIXTURE / PRODUCTION HOLD.
Parent: `55b5821eb17d56afe571c34d9eae1e5ebbdaada2`.

The 92NI inert separate-process client now accepts caller-supplied base64
bytes in a fixture-only WIRE mode. It sends one message over its random local
pipe while staying connected. The server captures the message under the 92NG
deadline and 512-byte bound, then invokes the read-only kernel PID/creation
time comparison from 92NH before returning captured bytes. Python decodes
those bytes and applies the unchanged 92NE canonical challenge parser with
an expected ceremony, challenge, and app-instance nonce.

The fixture verifies exact canonical byte preservation and parser acceptance.
It also verifies that noncanonical leading whitespace and a wrong nonce are
not rescued by a successful pipe capture or kernel process observation. This
is test-only transport and parser composition; the base64 command argument is
not an issuer input or production protocol. The process is a disposable copy
of the fixture, not Kilo, OpenCode, a model, or a protected app.

Open gates remain protected pipe policy/readback, trusted app launcher and
expected process/package identity, independent issuer and install, durable
one-shot accounting, exact bounded live authorization, and strict 92AT
mapped-byte proof. No real receiver, production activation, Docker mutation,
GPU, or ComfyUI action occurred.
