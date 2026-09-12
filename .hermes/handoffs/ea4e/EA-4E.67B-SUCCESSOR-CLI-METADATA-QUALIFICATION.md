# EA-4E.67B Successor CLI Metadata Qualification

CLI metadata/interface qualification: PASS. Full successor promotion: NOT DONE.
Parent baseline: `8e2359623e0703f74109277bc70af2c96625338b`.

## Exact Identity and Probe Evidence

Path: `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.6.2-win32-x64\bin\kilo.exe`.
SHA-256: `5d54b522d8a59228951d141cd70438c29115963ecb38d7cdfcf313f59c0f865b`.
Size: 173595648 bytes. Extension manifest version: 7.6.2.
Windows version metadata: 1.3.14; CLI `--version`: **7.6.2**, exit 0.
`run --help`: exit 0; required `--format json`, `--pure`, `--agent`,
and `--model` options are advertised. Help is not behavioral proof of permissions,
JSON event schema, model readiness, or transport execution.

Two real metadata subprocesses were started, with no task prompt, credentials,
receiver execution, or model invocation. No assertion of OS-level network
containment is made: credential-free environment isolation is not a network
sandbox. No network request was intentionally issued by the probe.

Probe uses a fresh temporary home/config/cwd, an allowlisted environment,
shell=False, exact binary SHA gate, and a 15-second timeout per command.
Only --version and run --help are supplied. There is no retry. The tool rejects
wrong hashes, unexpected versions, failed commands, and missing help flags.

## Tests

Project interpreter: `C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe`.
Command: `-m pytest tests/hermes_core/test_ea4e67a_successor_static_inventory.py tests/hermes_core/test_ea4e67a_metadata_probe.py -q -p no:cacheprovider --basetemp=.pytest-ea4e67a-unique-20260912a`.
Result: **11 passed / 0 failed**.
Initial attempt: 5 passed / 6 setup errors due access denied to the preexisting
pytest-of-David temp directory. Fresh isolated base resolved all six errors;
no preexisting directory was deleted or changed to fix this.

## Four-File Checkpoint Scope

- tools/qualify_ea4e67_kilo_metadata.py
- tests/hermes_core/test_ea4e67a_successor_static_inventory.py
- tests/hermes_core/test_ea4e67a_metadata_probe.py
- .hermes/handoffs/ea4e/EA-4E.67B-SUCCESSOR-CLI-METADATA-QUALIFICATION.md

This checkpoint changes no existing production file or predecessor contract.
It is a bounded metadata qualification, not the full regression gate or authority
to substitute the successor in production. Old static inventory expectations
are historical baseline assertions and need classification during promotion.

Next: successor-specific transport/binding candidate and complete downstream
dependency/contract-ID diff, then fake-only reseal and regression verification.
Durable binding renewal, activation issuance, and live task remain gated by that
qualification. No GPU/ComfyUI work is needed or authorized by this evidence.
