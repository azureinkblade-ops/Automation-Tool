# EA-4E.92LW/LX bounded agent text return

Status: NON-LIVE / FAKE TERMINAL RECORDS / PRODUCTION HOLD.
Baseline: `096834942926b22202aa4c1e9cbac17047c0e84f`.

The existing canonical result envelope now has a distinct
`hermes.agent_text_result/v1` validation path for Codex, Kilo, and OpenCode.
It accepts a nonblank inline UTF-8 text field of at most 4096 bytes and
binds it to the task input hash, accepted receiver receipt, result schema,
and exact receiver lineage. Outputs remain empty; v1 is success-only.
The result-store independently checks those fields and uses its trusted
clock to require delivery inside the active lease. Duplicate result
delivery replays the existing durable result; divergent or inactive
attempts fail closed.

`return_bound_agent_text` reads an existing Codex terminal registry record
or Kilo/OpenCode terminal capture and delivers to the originating mailbox.
It does not start or invoke an agent. The old ping paths and schemas remain
separate. Fake tests cover all three receivers, restart/replay, absent
terminal evidence, wrong schema/receiver, malformed or oversized text,
forged store-side payload, cancellation, and lease expiry.

Focused tests: 24 passed. Adjacent result-store, ping, terminal-capture,
receiver-lineage, and three-agent shared-store ladder: 141 passed plus
6 subtests, 0 failed. An earlier sandbox run of the legacy unittest
result-store file could not open Windows temporary files; the same
suite passed outside that filesystem sandbox. No production source
outside this text-result path was changed.

This proves provenance and bounded schema handling for fake terminal
artifacts, not the truth of model-authored text or compatibility with a
real receiver's output. It does not establish a protected app launch,
issuer, installed byte/dependency closure, live Kilo/OpenCode/Codex call,
or production activation. The strict 92AT route remains REJECT/HOLD;
the separate local-Docker route remains unqualified. No receiver, model,
GPU, ComfyUI, or Docker mutation occurred.
