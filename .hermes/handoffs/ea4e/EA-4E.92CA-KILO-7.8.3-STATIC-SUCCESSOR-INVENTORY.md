# EA-4E.92CA Kilo 7.8.3 Static Successor Inventory

## Classification

Non-live, read-only host inventory and in-memory contract calculation at
source commit `87ce4dba9a6933c53cfa2890f6b4c1bfbcc04827`. The Kilo
executable was never launched. No production pin, contract, test, store,
runtime configuration, authority, or receiver state was changed.

## Pin drift

`tools/hermes_core/kilo_adapter.py` still pins Kilo 7.7.9 at
`C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.9-win32-x64\bin\kilo.exe`
with SHA-256
`9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07`.
That path is absent. The only `kilocode.kilo-code-*` extension directory
observed under the local VS Code extensions root is 7.8.3. A current
Kilo-only live call cannot use the frozen 7.7.9 executable binding.

Candidate, not production identity:

- Executable: `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.8.3-win32-x64\bin\kilo.exe`
- Size: 175349592 bytes.
- SHA-256, two independent read-only passes:
  `8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a`.
- Extension manifest: name `kilo-code`, publisher `kilocode`, version
  `7.8.3`, VS Code engine `^1.105.1`, entry `./dist/extension.js`.
- Manifest SHA-256:
  `c1dea2a6e86bbb19af8fd59c51491d1e6386b3a0859068dffdedfcb690453384`.
- Windows Authenticode status: `Valid`. The reported signer subject is
  `Anaconda, Inc.` with certificate thumbprint
  `6CF704CA4AA6E24A45CAE2E16960BD3C1D44BFB2`. This is not, by itself,
  proof of Kilo Code publisher provenance or transport behavior.

## In-memory contract impact

Calling the existing canonical material function with candidate values,
without modifying module globals or files, changed exactly
`binary_path`, `binary_sha256`, and `binary_version`. Current transport ID:
`b97e4902056689fd7655c75955dcecb906d372b1a7dce012d9d0a1891472be06`.
Candidate transport ID:
`b9836a346bf73d8c6af62539164aa88c3ea373600e7ee1a73b241da4774a4543`.
Candidate executable-successor binding ID:
`23872196c03dce605ea3f2e0a3b58b75e93a6ae2d254bff0992fb8934248e76e`.
These candidate IDs are calculations, not qualified or sealed production IDs.
The 13 downstream contract IDs must not be rolled from static inventory alone.

## Existing process-free checks

- `test_kilo_fully_governed.py`: 22 passed / 0 failed, fake executors only.
- `test_ea4e42_nonlive_app_factory.py`: 17 passed / 0 failed, fake
  executors and real-path tripwires.

These tests verify inherited fake-only Kilo routing and composition, not
the 7.8.3 executable, model, credentials, external transport, or production
activation. No full regression gate was run for this documentation-only
inventory.

## Next boundary

1. Requalify exact 7.8.3 metadata under a separate bounded authorization
   before any version/help process call. Static hashes do not authorize it.
2. If metadata qualifies, review the successor contract and all affected
   sealed downstream IDs, then run staged and committed fake-only gates.
3. A real Kilo task requires a later exact receiver/model/source/authority,
   process, budget, and cleanup authorization. The historical Kilo live
   pilot and 7.7.9 pin do not cover 7.8.3.

The EA-4E.92AT image-section-byte HOLD concerns the separate 92S Node
containment probe. This inventory does not relax it, qualify OpenCode, or
activate the Kilo path. The app production feature gate remains default
disabled, and the app does not auto-register real executors.

`KILO_7_7_9_PIN_PATH_PRESENT=NO`

`KILO_7_8_3_STATIC_IDENTITY=RECORDED_ONLY`

`KILO_7_8_3_RUNTIME_BEHAVIOR=UNQUALIFIED`

`PRODUCTION_ACTIVATED=NO`
