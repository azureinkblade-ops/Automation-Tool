# EA-4E.92OZ fake v2 ceremony composition

Status: FAKE-ONLY INTEGRATION / NATIVE AND PRODUCTION HOLD.
Governing parent: `cfc358f270c4419afe463325102e565caa3b145d`.

`InertV2Ceremony` composes the 92OW attestation-byte validator with the
92OX record-value binding and v2 announcement decoder. It requires the
two independent expectation objects to agree before the first attempt,
accepts only explicit `fake_only=True`, and poisons an invalid first attempt
for the current process lifetime. A second consume or duplicate close
denies. The focused integration matrix passed 13/13, including replay,
malformed frame, mismatched hash/file ID, trailing bytes, and failed-first-
attempt cases.

This fake-only state is not a durable ledger. The test inputs are constructed
inside the process, not obtained from an authenticated elevated creator or
retained Windows handles. A fake PASS demonstrates local protocol composition
only; it cannot establish a trusted issuer, real Kilo/OpenCode communication,
or production readiness. No native file/pipe, UAC process, Docker mutation,
receiver, model, GPU, ComfyUI, or production action occurred.

Next boundaries: qualify the installed announcement namespace and its
effective rights, the two-way creator channel, retained-handle file and
descriptor observations, durable one-shot accounting, and a separately
authorized inert native probe. Full 92NK and production remain HOLD.
