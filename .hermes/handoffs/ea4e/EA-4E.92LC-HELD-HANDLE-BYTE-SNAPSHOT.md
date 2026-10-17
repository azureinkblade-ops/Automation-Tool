# EA-4E.92LC held-handle byte snapshot candidate

Status: NON-LIVE / READ-ONLY DIAGNOSTIC. Production HOLD.
Baseline: `e23ecf9d4fa05e9f33470e59dd096528bef14daf`.

The topology candidate can now open its leaf for read while retaining the
ancestor and leaf handles. The new byte candidate requires a canonical
lowercase SHA-256, hashes at most 64 MiB through that retained leaf handle,
checks the observed length, and lets the topology candidate recheck final
paths before releasing handles. A missing, changed, hardlinked, reparse, or
noncanonical target fails closed. Its only positive output is
`MATCH:BYTE_SNAPSHOT_ONLY`.

This is not the exact mapped-image byte invariant. An already-open writer or
trusted administrator may mutate bytes; the snapshot does not bind the bytes
that a later process loader maps. It also does not bind a dependency closure,
approved owner list, protected installation, operator witness, store anchor,
or Docker action. It has no issuer, Docker, receiver, model, network, GPU, or
ComfyUI capability and must not be interpreted as production authority.

Focused EA-4E.92LC/92KY/92LA tests: 26 passed, 5 Windows permission skips,
zero failures. The initial test attempt could not create pytest's default
sandbox temp directory; rerunning with an unused workspace basetemp produced
the reported result. The standalone C# probe also matched the current source
file's SHA-256 and denied an intentionally wrong hash.

The next independently governed boundary remains the protected issuer and
its reviewed binary/dependency closure, owner policy, app SID/root binding,
and exact live authorization. No UAC prompt, protected install, Docker
mutation, Kilo/OpenCode/model call, or production activation occurred.
