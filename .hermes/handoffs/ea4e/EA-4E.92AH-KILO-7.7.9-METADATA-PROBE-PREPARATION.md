# EA-4E.92AH Kilo 7.7.9 Metadata Probe Preparation

## Disposition

Non-live preparation only. The exact-file metadata qualifier is implemented
and fake-tested but has **not** been called against the installed executable.
No Kilo process, receiver, model or task was started by this checkpoint.

## Frozen Probe Envelope

- Executable:
  `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.9-win32-x64\bin\kilo.exe`.
- Required SHA-256:
  `9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07`.
- Expected CLI version: `7.7.9`.
- Only admitted argument vectors: `--version`, then `run --help`.
- The first command must pass before the second is attempted. SHA-256 is
  checked before, between and after the commands. Drift aborts without retry.
- Each process has a 15-second timeout, closed stdin, `shell=False`, a fresh
  temporary HOME/config/cwd, and an explicit credential-free environment.
- Version output must exactly match; help must contain `--format`, `json`,
  `--pure`, `--agent` and `--model`. Captured output above 65536 characters
  is denied after capture. This is a review-size check, **not** an OS-level
  streaming/output resource cap.
- The returned result contains command arguments, exit status and output
  hashes, not the entire help text.

## Fake-Only Verification

- Metadata qualifier safety tests: 8 passed / 0 failed.
- Fake-only process/network tripwire events: 0.
- Filesystem tripwire events: 0.
- Exact staged and committed-tree results are recorded in Obsidian after
  qualification; this file does not claim those future results.

## Authorization Boundary

The user's request to continue allows this non-live source and test slice.
It does not by itself identify a one-shot execution window or authorize
running the installed unsigned binary. The actual two-command metadata probe
needs a separate exact authorization bound to this SHA-256, path, command
allowlist, timeout, isolated environment and one-attempt budget. A probe
success would qualify CLI metadata only, not transport behavior or a live
receiver. Production pin/reseal and live model use remain separate stages.
