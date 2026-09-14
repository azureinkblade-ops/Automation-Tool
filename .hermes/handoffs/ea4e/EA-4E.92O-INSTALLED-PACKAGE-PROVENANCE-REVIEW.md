# EA-4E.92O Installed Package Provenance Review

Baseline: f0b0b2899b668ffc599320e06c786a7c8974172f.
Result: LOCAL PACKAGE BYTE ASSOCIATION CONFIRMED / EFFECTIVE SDK PROVENANCE HOLD.
Read-only investigation only; no receiver or SDK import/execution.

## Bounded Discovery

Reviewed installed opencode-ai package, its two nested Windows binary packages,
the hidden isolated runtime home, and local opencode-1.18.11 source/build files.
The opencode-src directory listing was empty. Hidden runtime home contains
SDK/provider/plugin-related dependencies, but the bounded hidden-file search
found no openai-compatible implementation under that home or opencode-ai package.
This corrects the incomplete non-hidden runtime inventory; it is not proof that
the implementation is absent globally or absent from the compiled executable.

Exact roots:
- C:\Users\David\AppData\Local\Hermes\node\node_modules\opencode-ai
- C:\Users\David\AppData\Local\Hermes\runtime\ea4e\opencode\home
- C:\Users\David\AppData\Local\Hermes\opencode-1.18.11

No other package version was substituted. No installation, build, download,
binary extraction, model task or provider call occurred.

## Observed Binary Association

Installed bin/opencode.exe and nested
node_modules/opencode-windows-x64/bin/opencode.exe both hash to
578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35.
This matches the registered pin. Nested baseline binary instead hashes to
0e80c44457a95108e1932a1c31bcaddc011e143943f13624891a114b21262347.
Both nested package metadata files report version 1.18.11.

Equality proves observed byte association with the regular x64 artifact, not
which historical installer branch ran, OS hardlink identity or upstream build
provenance. Do not claim the baseline package was used or change its pin.

postinstall.mjs SHA-256:
5a7c990fe552e76b16422cdba3f4b0550590c7a487f7932c773362f74317c87b.
Source inspection shows resolveBinary locating platform package/bin, copyBinary
hardlinking or copying to the installed executable, and verifyBinary invoking
--version. Installation fallback invokes npm and deletes its temporary directory.
None of this script was executed. It must not be imported as an offline probe:
its top-level main() can launch processes, install packages and mutate files.

## Source Build Route and Missing Link

Local packages/opencode/script/build.ts SHA-256:
c98c068580faac0ebcade9a1179827a24bd3f3102e6c08fef637a0636fa9f19d.
The inspected build route uses Bun.build with compile options, an entrypoint and
target-specific output. Its source also performs generation/build/install steps.
It is not a safe import-only request harness and was not run.

These observations explain why an unpacked runtime package is not enough to
inspect the compiled application dependency graph. They do not establish that
this exact local source/build produced the installed binary. A trusted release
attestation, exact source/build manifest, or reviewed extraction tying effective
SDK bytes to the pinned executable remains missing from this reviewed surface.

EA92N's streamText compatibility risk remains unresolved. A package lock's
version label or unrelated installed SDK/provider package is not sufficient
effective implementation evidence. No actual HTTP request/body was captured.

## Required Next Slice

Obtain authoritative source/build provenance or design a bounded read-only
extraction/inspection path for this exact compiled artifact. Review any tooling
before use; prohibit installer/build execution, receiver startup, plugins and
network side effects. Only a proven effective implementation may enter an inert
SDK request-construction harness. Retain streaming HOLD until then.

Do not spend the live one-shot budget to discover package identity. Do not invent
policy bytes, register synthetic IDs, relax v1, or make more fixtures substitute
for effective SDK proof. A streaming-capable contract revision remains a separate
design option, not an automatic remedy or authorization to execute.

## Checkpoint Limits

One evidence file; no production/test source edits. Formatting/scope checks are
the gate for this read-only evidence checkpoint. No new regression tests or
full-suite results are claimed. EA92N's six current-ID passes and EA92M's raw
committed gate remain results for their exact historical source checkpoints.

No production activation/issuance, runtime/config mutation, listener, receiver,
provider/model/GPU/ComfyUI, downloads or deletion. Effective SDK, trusted acquisition,
real target freeze and production readiness remain HOLD.
