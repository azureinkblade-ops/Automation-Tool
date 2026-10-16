# EA-4E.92KU canonical network-grant builder

Status: NON-LIVE / NON-AUTHORIZING CANDIDATE. Not a protected issuer.
Baseline: `8f0fba3337c0e48420237c635c55bfb5a9e582ea`.

The pure C# builder accepts explicitly supplied v2 field and label values,
sets the fixed network-create scope, computes canonical JSON and its artifact
hash, and returns bytes only after the existing complete v2 verifier accepts
them. The caller cannot supply `artifact_hash`; malformed identity, epoch,
time, labels, scope, or noncanonical numeric representations are denied.

One fake integration test passes builder-produced bytes to the v4 store,
reopens the store, claims once, and observes replay denial. This proves the
builder/verifier/store byte contract, not independent authority. Test inputs
in this harness are deliberately supplied by the fake test; they are not an
operator witness or trusted current-authority source.

Focused builder/v4-store/v2-verifier suite: 52 passed, 0 failed.
Adjacent EA-4E.92I/J/K and HJ/HV/HY fake-only suite: 551 passed, 0 failed.
Source scan found no process, network, model, GPU, MCP, or ComfyUI invocation
in the builder module. No protected binary was installed or executed.

Still required: an independently approved ceremony source for all expected
fields and current authority, a trusted clock and operator UAC witness, a
reviewed/pinned protected binary and dependency closure, protected durable
store placement, and separate action-specific Docker/receiver authorization.
No Docker mutation, Kilo/OpenCode/model call, GPU, ComfyUI, or production
activation occurred. Production remains HOLD.
