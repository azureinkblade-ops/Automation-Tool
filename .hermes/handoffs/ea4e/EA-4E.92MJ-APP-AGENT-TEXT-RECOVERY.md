# EA-4E.92MJ app agent text recovery

Status: NON-LIVE APP INTEGRATION / PRODUCTION HOLD.
Parent baseline: `5477e92526854a38f6f6583190ef522f08822d61`.

`app.py` now exposes explicit configuration, inspection, and recovery for
the existing `AgentTextRecoveryHost`. The host defaults disabled and is not
configured by `main()`. Its established store-binding, attempt, schema,
receiver, terminal, result, and mailbox checks remain the authority for
these calls. No new app endpoint or automatic receiver start was added.

The dedicated fake-only tests cover missing configuration, disabled access,
one idempotent bounded text return for Codex, Kilo, and OpenCode, and claimed
Kilo/OpenCode starts without text remaining unknown with no message.
Focused: 6 passed. Affected app ping/text and three-agent chain: 57 passed.

The broader run including the old EA-4E.52 host fixture had 64 passed and
20 failures, all at its binding setup. One failure reproduced in isolation
on an untouched archive of the parent commit at the same assertion
(`DENY` instead of `BOUND`), so this is inherited and outside 92MJ. The
older fixture was not changed to make this checkpoint pass.

The tests use synthetic receiver evidence. This change does not establish
real Kilo/OpenCode/Codex output, a protected app owner, installed issuer,
local-container provenance, or production activation. No receiver/model,
Docker mutation, GPU, or ComfyUI call occurred. Production remains HOLD.
