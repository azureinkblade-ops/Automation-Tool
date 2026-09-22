# EA-4E.92T Kilo 7.7.2 Static Candidate Diff

## Classification

PASS / qualified non-live static candidate diff.

This checkpoint identifies the installed Kilo 7.7.2 executable and freezes the
deterministic contract-chain impact entirely in memory. It does not execute the
binary, promote a production pin, mutate a durable store, invoke a receiver or
model, activate production, or authorize live work.

## Governing state

- Branch: feature/ea4e67-kilo762-roll
- Local HEAD: 1ce3986f333245e15ba506ed176d973c34d81cba
- Remote baseline: 0c1c8be8d7889e0b2575e63ac31223f138eac33e
- Local ahead / behind: 1 / 0
- Observer-binding schema commit remains isolated and unpushed.

## Static executable identity

- Path: C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.2-win32-x64\bin\kilo.exe
- Size: 174145024 bytes
- SHA-256: 3dca5f2eb8cc2d875e8cdef756f77347d4899247c318bf2a018d39e0184455cd
- Extension manifest version: 7.7.2
- Publisher: kilocode
- VS Code engine: ^1.105.1
- Extension entry point: ./dist/extension.js
- Windows file/product version: 1.3.14

The former pinned 7.6.2 executable path is absent. No Kilo executable was
launched while collecting this identity.

## Frozen candidate identities

- Transport contract:
  40f23258d1abf1a799747d4ea2899a6103fa5e1fb33384f1c17dd4104ea1c578
- Executable successor binding:
  cee3f5c96ef344ead9954030b671ae4e387f3a08e6e9df86885aaeafb4106840
- Predecessor executable binding:
  b89f9f02f3e99cf70a98de8b4fb02b545e51855bb7340ed829ece749256b9be1

Downstream candidate IDs:

- EA-4E.6: 67435bdb8169cd7973131c5df6e89c5fdd86d9a495a7f428fd681b05db8a7d2e
- EA-4E.7: 71a5c8e9feb6c755743292f758fe3a04adef74565f9f56027f904608c6588e54
- EA-4E.8: 62dd1a6d7a66a91b7d7348ecdf56925a3285ccbc38da9674a08ed0ec54e4a544
- EA-4E.11: d0d9709ddbb5876599ac19ece28665d0f78721774576afee9934bb665cda0492
- EA-4E.14: fb75980ba6f8812f9cde51977120fb4283987b1badd9047605217b15802ca99e
- EA-4E.17: 7e8e6e668791b38e085329dde5c364750b163897caa0cf7977de3985e289203c
- EA-4E.18: 1b2cd071de0d8a58d248c8b6c38f9699ffcc729c02909584f45870b901d8a12e
- EA-4E.21: 3f159719f0109a43fa3fff9b50f661694aad1e83e06b161f8b5026e4cc050d72
- EA-4E.22: 19747974b50bdb400471496c6eae91ae552a296a6b58695324ffd323709961c9
- EA-4E.23: 31bc9f5587fa93a770dd32968174c114abc1cc064f513e9b1697772516008b2c
- EA-4E.26: 3c9cdd52383a7c28a25638cef5a9f72fa6c7f27fb2ac807d13e7d084f9288576
- EA-4E.28: eaeae2dfda8444596e98b7beb949975d4e05453001af1140c694751f246d351e
- EA-4E.29: 64770d93dd04eaaa8149cb4e4bea1f69adbb032b446069dc79850a4ecd2334e9

Every candidate downstream ID differs from its frozen 7.6.2 predecessor while
the identity-key set remains unchanged.

## Verification

Test file:
tests/hermes_core/test_ea4e92t_kilo772_candidate_contract_diff.py

- Candidate test: 1 passed / 0 failed.
- Candidate plus predecessor and current successor-roll tests:
  19 passed / 0 failed.
- Fake-only process/network tripwire events: 0.
- Filesystem tripwire events: 0.

First staged-tree export:

- Tree: 196e45062f4efc21f2adaeb2be63e5e60a2221e5
- Archive: .ea4e92t-kilo772-static-index-a.zip
- Archive SHA-256:
  a7231f2a8dd02e09d3a3bcc297ae5126a6a26ca6f65b253e4ab4da2465ba5318
- Exported-tree qualification: 19 passed / 0 failed.
- Exported-tree fake-only process/network tripwire events: 0.
- Exported-tree filesystem tripwire events: 0.

The test derives the transport, executable binding and 13 downstream identities
in memory, verifies exact frozen values, and proves the current 7.6.2
predecessor chain has not drifted.

## Remaining boundary

This checkpoint does not establish Kilo 7.7.2 runtime or transport compatibility.
Before production promotion, a separately bounded stage must qualify the exact
CLI metadata/transport surface and then perform the full pin/reseal regression
ladder. Until then:

- Kilo 7.7.2 production pin promotion: NOT QUALIFIED.
- Observer-binding schema commit push: HOLD.
- Native provider implementation: NOT STARTED / NOT AUTHORIZED.
- Real receiver/model execution: NOT AUTHORIZED.
- Production activation: NO.
- GPU / ComfyUI activity: NO.

Checkpoint state: EXACT TWO-FILE STATIC CANDIDATE CHECKPOINT STAGED / EXPORTED
TREE QUALIFIED / NOT COMMITTED / NOT PUSHED.
