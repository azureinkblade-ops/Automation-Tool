# EA-4E.92AG Kilo 7.7.9 Static Candidate Diff

## Classification

Non-live static candidate only. No Kilo executable was launched, no
production pin or sealed artifact was changed, and no authority was issued.
The current Kilo 7.7.2 pin remains fail-closed because its executable path is
absent. This stage does not make the broad regression gate green.

## Governing State And File Identity

- Branch: `feature/ea4e67-kilo762-roll`.
- Parent commit: `3cf45e69f2c74237f17811921515182d67cddc36`.
- Candidate path: `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.9-win32-x64\bin\kilo.exe`.
- Candidate size: 175458816 bytes.
- Candidate SHA-256 (repeated static reads):
  `9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07`.
- Extension manifest version: `7.7.9`; name: `kilo-code`; publisher:
  `kilocode`; engine: `^1.105.1`; entry point: `./dist/extension.js`.
- Manifest SHA-256:
  `57f1949e30bf1e23b30eca07f22fd039401c0af017b6a1bd44e74641850f94af`.
- The Windows Authenticode query reported `NotSigned`; manifest fields and
  matching versions are not an independent publisher-signature proof.

## In-Memory Candidate Contract Diff

Only `binary_path`, `binary_sha256`, and `binary_version` change in the
transport material. Model binding and the permission/isolation policies stay
unchanged in the calculation. This does not prove 7.7.9 transport behavior.

- Candidate transport: `b97e4902056689fd7655c75955dcecb906d372b1a7dce012d9d0a1891472be06`.
- Candidate executable binding:
  `653317206aaba6161ff67d2a199ded169daa19869ea578fd4e8ccb2413570ddd`.
- Immediate predecessor version: `7.7.2`.
- Immediate predecessor transport:
  `40f23258d1abf1a799747d4ea2899a6103fa5e1fb33384f1c17dd4104ea1c578`.

Downstream candidate IDs (all 13 differ from the current pinned chain):

| Contract | Candidate ID |
| --- | --- |
| EA-4E.6 | `d26c3f6dd24c1fa25a1bc963bcdce17c8e5b1255695e10c63abe35d367b24ff2` |
| EA-4E.7 | `4bef69cfef38df6a5549062aa60393773c268a734c4cb4e8ee8c929bb9dc91fb` |
| EA-4E.8 | `bf1d279545f787ddd347c367c06be3c53f3462f7a253bf26a323ae867cce2156` |
| EA-4E.11 | `ff9e72b21a4b905e898ef88b2352a152bc32ad3a63d4e93a25dbb5d8fed13c4d` |
| EA-4E.14 | `ccef2473acceccd2548d10791ffdeaabce62c4adcf9be365577e95b6ed31b805` |
| EA-4E.17 | `f593677f85599e1a3bcc4956e190c5cfd06cfc5156d9200dc16dad5b31315032` |
| EA-4E.18 | `061cb8b52485a035c850ce675aa7025a98fbe18de86739fbe421430afbc3e704` |
| EA-4E.21 | `a429da60f529461ad3972b79b68cb1c7e886878aa5fd19d985495df06a265a0f` |
| EA-4E.22 | `27c4e7eaa5b894f607a9ec7d1430d686ef38c634874fbfbc2bca87e1ddd8aaf7` |
| EA-4E.23 | `d5043df466a2ef61a3d5b9e05eb70fc54cc2dacfa003b0fee705accb241f5fd2` |
| EA-4E.26 | `b97251db3f56ab27ecf937eaabc3cd4388b2ad56aaaac47e730c7f924815f92c` |
| EA-4E.28 | `379e2edd3673169eb9a86a2e811555bdc437e4f94362a8017eed9163dc587f90` |
| EA-4E.29 | `14ce38bad7c0f477239eae3b0342859742f3d69966bde9987807636eb9ef7103` |

## Verification And Boundary

- Guarded candidate, predecessor and current successor tests: 20 passed.
- Fake-only process/network tripwire events: 0.
- Filesystem tripwire events: 0.
- Exact staged and committed-tree results are recorded in Obsidian after
  qualification; this file itself does not claim those future results.

The next stage requires an exact bounded authorization for metadata-only
`--version` and `run --help` probes against the same rehashed file. No task,
prompt, model, receiver or production activation is authorized by this
candidate. Only after metadata qualification should the 7.7.9 pin and all
affected sealed IDs be considered for a separate non-live contract roll.
