# EA-4E.92CK Kilo inert-provider probe prepared

Status: PREPARED / RECEIVER LAUNCH HOLD
Governing parent: `132405edb4071f2a4448fea5af3fe74d300eb838`

## Prepared artifacts

`tools/ea4e92ck_kilo_inert_probe.py` provides two separate commands:
`prepare` writes a new isolated probe home/config/launch plan, and `serve`
hosts a loopback-only fake OpenAI-compatible endpoint. Neither command starts
Kilo, forwards a provider request, reads real credentials, or activates
production. The script has no Kilo execution command.

The prepared runtime is
`C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-inert-probe-92ck-20261004`.
Its `launch-plan.json` pins Kilo 7.8.3 SHA-256
`8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a`,
the inert `openai-compatible/ea4e-inert` model, a fresh home/config, dummy
local-only key, and loopback port 49321. The three plan flags
`launch_authorized`, `network_isolation_verified`, and
`real_provider_calls_authorized` are all false. No existing runtime state or
credentials were copied into that directory.

The fake endpoint accepts only the dummy bearer value, responds to
`GET /v1/models` and `POST /v1/chat/completions`, supports deterministic
JSON/SSE replies, and rejects other paths. It records only method, URL path,
status, and streaming flag; no body, query string, or authorization value.
It cannot forward any request.

## Verification

Focused preparation, loopback fake-provider, and existing Kilo-adapter tests:
120 passed, 1 expected opt-in inert-process skip. The loopback test was
explicitly enabled; it started only the fake HTTP server, then shut it down.
The bundled Codex Python lacks pytest, so this check used the existing
Python 3.14 pytest installation. The prepared launch plan was read back and
confirmed to reference the inert model and all three false authorization
flags. The planned port was not listening at preparation time.

## Remaining launch gate

The current production adapter fixes the real `kilo/...` model and points to
a home with a real local auth-state reference. The inert probe deliberately
uses a different argv/config and a fresh home; its result cannot prove the
unchanged production transport is equivalent. Kilo's installed executable
was hash-checked but never run.

Before any inert Kilo process starts, independently verify OS-level outbound
network isolation that still permits the loopback fake endpoint, and obtain
a separate exact authorization for one pinned Kilo process, the isolated
home, fixed inert model/task, 30-second deadline, bounded output, no real
provider credentials, no retry, and teardown. `WindowsSandbox.exe` was not
present during this preparation; no alternative egress block was assumed.
If isolation or any pin fails, abort before process creation. A fake-only
result would qualify only the inert custom-provider path. A future production
gateway still requires model/credential/transport contract review and the
independent EA-4E.92S mapped-byte proof remains HOLD.
