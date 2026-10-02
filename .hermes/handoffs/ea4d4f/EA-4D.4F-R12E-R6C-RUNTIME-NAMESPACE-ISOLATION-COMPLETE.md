# EA-4D.4F-R12E-R6C Runtime Namespace Isolation Complete

## Disposition

`EA-4D.4F-R12E-R6C: PASS / READY FOR CLEAN COMMIT`

R6C gives each fresh governed qualification proof a deterministic isolated
runtime namespace before any delegation or execution identity is created. The
repair is entirely non-live.

## Precheck

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `627d297f9da3399df3facf562fce6a42952f66a5`
- Parent: `91a70d46cfa2538720a9c88fce17d0fab3d004ba`
- Frozen R11 SHA-256:
  `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Tracked modifications/staged paths before R6C: `0 / 0`
- Unrelated untracked WIP: `139` paths, preserved

## Root Cause

The committed live harness selected:

`ROOT / ".hermes" / "runtime" / "ea4d4f" / "r12e"`

That is the immutable original-R12E terminal namespace. It contains ten files,
including `live-proof-evidence.json`. `prepare()` correctly detected that
evidence and refused reuse before identity creation.

The R4 terminal namespace remains separately fixed at `r12e-r4`.

## Namespace Contract

- Contract version: `hermes-runtime-namespace/v1`
- Owner type: `governed-qualification-proof`
- Owner source: fixed governed proof identity, not delegation or invocation ID
- Manifest: `runtime-owner.json`
- Namespace name: `proof-` plus the first 24 hexadecimal characters of the
  canonical owner hash
- Owner hash material: contract version, owner type, and proof identity
- Source binding: exact canonical lowercase Git object ID (40-character SHA-1
  in the current repository; 64-character Git object IDs are also supported)

The R6 proof identity is:

`ea4d4f-r12e-r6-one-shot`

Its owner hash is:

`adb795668b3266a8d95572cc0fe59a7fa9de1dd021fa0d0382a6cce54b3c2162`

Its deterministic future runtime path is:

`.hermes/runtime/ea4d4f/proof-adb795668b3266a8d95572cc`

That path does not exist after R6C testing. Namespace reservation is wired as
the first operation in future `prepare()`, before any real delegation,
authorization, attempt, receipt, schema, transport, or process state.

## Closed Ownership And Filesystem Safety

- Proof identities accept only canonical lowercase alphanumeric, dot, and
  hyphen forms.
- Empty, uppercase, separator-bearing, absolute-looking, hidden, malformed,
  and `..` identities fail closed.
- Historical proof identities are read-only and cannot be reserved as fresh.
- Runtime paths are derived internally beneath the trusted runtime root; there
  is no caller path override.
- Owner manifests use exclusive creation.
- Missing, malformed, foreign, source-drifted, or otherwise inconsistent owner
  manifests fail closed.
- Existing terminal files are never deleted, truncated, or rewritten.

## Determinism And Isolation Proof

Fake A:

- Identity: `ea4d4f-r12e-fake-a`
- Owner hash:
  `2967bfe3e8a5cc98da52877764d7847c4f01a099d054dee24610a95c6f13210c`
- Namespace: `proof-2967bfe3e8a5cc98da528777`

Fake B:

- Identity: `ea4d4f-r12e-fake-b`
- Owner hash:
  `a0f5099efca677e4245ed2027c7c3ab29f98346557b2d70d9b5c7cb004d55658`
- Namespace: `proof-a0f5099efca677e4245ed202`

Same owner/source replay returns the same namespace and manifest. Different
owner or source material conflicts or resolves to a different namespace.
Restart does not create a second namespace. Same-owner terminal replay leaves
terminal evidence unchanged and creates no process state.

Historical mappings remain read-only:

- `ea4d4f-r12e-original` -> `r12e`
- `ea4d4f-r12e-r4` -> `r12e-r4`

Fresh R6 cannot construct either historical identity as a reservable owner and
cannot resolve to either historical path.

## Historical Immutability

- Original R12E evidence SHA-256:
  `67758d5c5843d8f9a0ffb7fc324e3297244c5af7496bbe3b773817091b380f62`
- R12E-R4 evidence SHA-256:
  `6bc7af15e81f29a4545dc5557608801a4fa87a2ed6733367012f554a0b59eb0a`
- Prior R6 HOLD evidence SHA-256:
  `b4551e8eb76b17c90af1d503f85ecca7221cfa5e87f65b658d045a769e3f28d9`

All remain unchanged. No historical directory was renamed or migrated.

## Verification

Interpreter:
`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

| Gate | Result |
| --- | --- |
| R6C runtime namespace | **19 passed, 15 subtests passed** |
| R6B/preflight/result group with R6C | **183 passed, 24 subtests passed** |
| R12A/B/C focused | **97 passed, 40 subtests passed** |
| Authority/start/routing current slice | **548 passed** |
| Complete Hermes Core | **1,301 passed, 96 subtests passed** |

`py_compile` and `git diff --check` passed. No failures remain.

## Capability Audit

- Codex task process starts: `0`
- Model invocations: `0`
- Real R6 identities: `0`
- Real R6 runtime namespace created: no
- Live budget consumed: no
- Generic shell/arbitrary executable/path override: no
- Historical evidence mutation: no
- Network/browser/MCP/scheduler/Kilo/GPU/ComfyUI/image-pipeline/RHR action: no

## Boundary

- Current R6 authorized starts: `1`
- Current R6 definitive starts: `0`
- Current R6 remaining: `1`

`RUNTIME NAMESPACE ISOLATION: QUALIFIED`

`HISTORICAL TERMINAL STATE: IMMUTABLE`

`FRESH ATTEMPT COLLISION PROTECTION: PASS`

The next gate is a fresh R12E-R6 live authorization bound to the committed R6C
HEAD and the `hermes-runtime-namespace/v1` contract. R6C does not authorize
identity creation or a live Codex start.
