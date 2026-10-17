# EA-4E.92LD combined ACL and byte snapshot candidate

Status: NON-LIVE / READ-ONLY DIAGNOSTIC. Production HOLD.
Baseline: `45273af7b6db1fa438021cb9a78827ebce2c26c3`.

The 92LA ACL observer and 92LC SHA-256 observer now have a combined entry
point. They inspect the leaf through one retained readable handle while the
topology candidate also retains ancestor handles. The ACL check runs before
the leaf byte read; topology paths are rechecked before handle release. The
legacy ACL-only and byte-only entry points remain available and unchanged in
their result vocabulary. A positive result is named
`MATCH:ACL_AND_BYTE_SNAPSHOT_ONLY`.

Focused 92LD/92LC/92KY/92LA tests: 31 passed, 5 Windows permission skips,
zero failures. A read-only probe under the ordinary unelevated Windows token,
outside the Codex filesystem sandbox, matched the existing
`C:\Program Files\Git\etc\gitconfig` with protected root
`C:\Program Files\Git` and its measured SHA-256. The same file with a
deliberately wrong hash denied with `BYTE_HASH_MISMATCH`. This is an existing
protected-file diagnostic, not a separately provisioned issuer fixture.

The expected app SID, protected root, and hash are still supplied by the
caller. The current-token observation cannot be used as an elevated issuer's
independently established app token. No approved owner allowlist, protected
issuer binary/dependency closure, installation, durable mapped-image byte
witness, store placement, or Docker action follows from this snapshot. A
local administrator is trusted by the accepted threat model and could change
the file after observation. The exact mapped-byte invariant remains unproven.

No UAC prompt, protected installation, Docker mutation, Kilo/OpenCode/model
call, GPU/ComfyUI operation, or production activation occurred.
