# EA-4E.92CB Kilo 7.8.3 Metadata Probe Preparation

## Scope and result

Non-live source and fake-only test preparation for the candidate recorded in
EA-4E.92CA. The installed Kilo executable was not launched. Production still
pins 7.7.9, and no transport, downstream contract, activation, or authority
was changed. This is preparation, not successor qualification.

## Prepared probe

`tools/qualify_ea4e92cb_kilo783_metadata.py` binds to the candidate path,
SHA-256 `8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a`,
and version `7.8.3`. Its only allowed arguments are `--version` and
`run --help`; neither supplies a task or model invocation. It rechecks the
file hash before and after each command, uses an isolated temporary home and
config, a credential-free explicit environment, `shell=False`, null stdin,
and a 15-second timeout. It denies version, exit-status, required-option,
hash, and captured-output-size mismatches. Captured output is limited only
after the process exits; the 65536-character review limit is not an OS-level
streaming bound.

The file defines `qualify()` but has no command-line entry point. A separate
exact bounded authorization is required before calling that function against
the installed executable. This checkpoint did not grant one.

## Fake-only verification

`py -3.14 -m pytest tests/hermes_core/test_ea4e92cb_kilo783_metadata_probe.py tests/hermes_core/test_ea4e92ah_kilo779_metadata_probe.py -q -p no:cacheprovider`

Result: 16 passed / 0 failed. Subprocess calls were monkeypatched to fake
results and temp-file identities. Tests cover the two allowed argv forms,
isolated environment, hash drift, version/exit failure, missing help options,
timeout without retry, and oversized output. The historical 7.7.9 probe and
tests remain unchanged.

## Next decision

Review this source and issue a separate exact bounded authorization if the
two installed-binary metadata calls are desired. A passing fake-only gate does
not verify 7.8.3 runtime behavior. After live metadata evidence, the successor
contract and downstream sealed IDs require independent review. No real task,
receiver, model, production activation, GPU, or ComfyUI use is authorized.

`KILO_7_8_3_METADATA_PROBE_PREPARED=YES`

`KILO_7_8_3_METADATA_PROCESS_EXECUTED=NO`

`KILO_7_8_3_RUNTIME_BEHAVIOR=UNQUALIFIED`

`PRODUCTION_ACTIVATED=NO`
