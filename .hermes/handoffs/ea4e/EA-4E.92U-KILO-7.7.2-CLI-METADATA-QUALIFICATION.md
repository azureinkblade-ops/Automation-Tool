# EA-4E.92U Kilo 7.7.2 CLI Metadata Qualification

## Disposition

PASS / qualified bounded metadata surface.

This phase executed exactly two metadata-only commands against the installed
Kilo 7.7.2 binary. It did not submit a task or prompt, invoke a receiver/model,
activate production, mutate a durable authority store, or promote the
production Kilo pin.

## Governing state

- Branch: feature/ea4e67-kilo762-roll
- Local HEAD at qualification:
  4b066e22608861f5cf7d34eebd0929952bed36b4
- Remote baseline:
  0c1c8be8d7889e0b2575e63ac31223f138eac33e
- Local ahead / behind: 2 / 0

## Exact executable identity

- Path:
  C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.2-win32-x64\bin\kilo.exe
- Size: 174145024 bytes
- SHA-256:
  3dca5f2eb8cc2d875e8cdef756f77347d4899247c318bf2a018d39e0184455cd
- Expected and reported CLI version: 7.7.2

The qualifier recomputed the SHA-256 before starting either process and again
after both processes exited. The identity was unchanged.

## Bounded process evidence

The qualifier used a fresh temporary HOME/config/cwd, a credential-free
allowlisted environment, shell=False, closed stdin and a 15-second timeout.
There was no retry.

Exactly these commands were admitted:

1. kilo.exe --version
   - Exit: 0
   - Output: 7.7.2
2. kilo.exe run --help
   - Exit: 0
   - Required options present: --format with json, --pure, --agent, --model

No message positional argument, command, session, attachment, server address,
credential, auto-approval flag or model selection was supplied.

The help surface also advertises --auto. It was not used and is not admitted
by this qualification.

No claim of OS-level network containment is made. No network request was
intentionally requested by either metadata command.

## Process audit

After the probes, one Kilo process was visible:

- PID at review: 24268
- Command: kilo.exe serve --port 0
- Parent: VS Code Code.exe PID 34484
- Kilo creation time: 2026-09-22 05:03:55 local
- Parent creation time: 2026-09-22 05:03:03 local

This is the editor-owned Kilo extension service, not a child of the qualifier
and not one of its two admitted command lines. It was not stopped or modified.
No qualifier-owned Kilo process remained.

## Tests

Fake-only qualifier safety tests:

- 7 passed / 0 failed
- Process/network tripwire events: 0
- Filesystem tripwire events: 0

Combined static candidate, metadata safety, predecessor and current-roll set:

- 26 passed / 0 failed
- Process/network tripwire events: 0
- Filesystem tripwire events: 0

Initial immutable staged-tree export:

- Tree: 94d2bcc7179e988352e8e16c002090a20e3c0152
- Archive: .ea4e92u-kilo772-metadata-index-a.zip
- Archive SHA-256:
  916ce43588256ea8e661fa38a9488ec8d25d5dda0bdd80a8688360504fece5c7
- Exported-tree result: 26 passed / 0 failed
- Exported-tree process/network tripwire events: 0
- Exported-tree filesystem tripwire events: 0

## Boundary

Kilo 7.7.2 CLI metadata and required run-help interface are qualified. This is
not behavioral transport proof and does not promote the successor.

Next:

- roll the production Kilo pin and executable-successor binding to the already
  frozen EA-4E.92T identities;
- reseal the 13 downstream contract IDs;
- update exact affected tests/evidence only;
- run the full fake-only regression ladder and committed-tree gate.

Until that work passes:

- Kilo 7.7.2 production pin promotion: NOT COMPLETE.
- Observer-binding schema commits push: HOLD.
- Native provider implementation: NOT AUTHORIZED.
- Real receiver/model execution: NOT AUTHORIZED.
- Production activation: NO.
- GPU / ComfyUI activity: NO.

Checkpoint state: EXACT THREE-FILE METADATA QUALIFICATION STAGED / EXPORTED
TREE QUALIFIED / NOT COMMITTED / NOT PUSHED.
