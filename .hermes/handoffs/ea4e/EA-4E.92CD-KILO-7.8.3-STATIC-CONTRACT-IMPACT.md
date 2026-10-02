# EA-4E.92CD Kilo 7.8.3 Static Contract Impact

## Scope

Non-live candidate calculation after the 92CC metadata PASS. Production
still pins Kilo 7.7.9. No process, receiver, model, credential, store,
activation, or sealed production contract was changed or invoked in this
checkpoint.

## Candidate identity and lineage

The 7.8.3 executable identity is the exact path, size, SHA-256, and manifest
version recorded in 92CA and metadata-checked in 92CC. Relative to the
7.7.9 canonical transport material, only `binary_path`, `binary_sha256`,
and `binary_version` change. Candidate transport ID:
`b9836a346bf73d8c6af62539164aa88c3ea373600e7ee1a73b241da4774a4543`.

The successor binding uses 7.7.9, not 7.7.2, as the immediate predecessor.
Its candidate binding ID is
`23872196c03dce605ea3f2e0a3b58b75e93a6ae2d254bff0992fb8934248e76e`.
The Kilo model binding remains
`b327fad4d90292b3e451c7ec4aa06d123eca091ac84eb7b116400ec96ca45544`.

## Sealed contract impact

All 13 EA-4E IDs calculated by the existing canonical functions rotate.
The exact candidate IDs are frozen in
`tests/hermes_core/test_ea4e92cd_kilo783_candidate_contract_diff.py`:

| Contract | Candidate ID |
| --- | --- |
| EA-4E.6 | `b044f6a703d6ca4a2b94bead81b07a05e4b52948a40ad40e1565db4d2598ebc4` |
| EA-4E.7 | `a79c2e9b9b268fedd5595114bf9aeb1ebca44b7726eaae023e3ef951ed193e6d` |
| EA-4E.8 | `94ec4047b30498a6dbf4266d44ddb43a90dc65ac3b2582b4ce273e404f0e422f` |
| EA-4E.11 | `7c594aa0dcf6107010a17230bbf43a225a9a65022ba345617ce7165d059dc363` |
| EA-4E.14 | `fc60a3794980c7cecb983c9303961eb217a99c199c3baa318e44f4d4fc7fa171` |
| EA-4E.17 | `fb60c0a4a6471aedb748258931ec06fc87dd980adbcf5503ea772e55d12ed430` |
| EA-4E.18 | `25ec6a8940c302c8803d0d72b3058478fb3a55c078db2dbd2a5313cd1211b5e7` |
| EA-4E.21 | `9589badd010b0433cf1aece4cad70626d7f5525673dedcc8c98f495cffc07d70` |
| EA-4E.22 | `09dc4dd1768a18fcf5cb1680ad2736272f0be5d79fd6f31bc64d47821d36402c` |
| EA-4E.23 | `a64ec10512a1e714f06b40b7597efbcf63fb625e2702fe8b1f120c5cc6d19a49` |
| EA-4E.26 | `23baa20906675865c4c10028b181b5ddadd9cb218eebc599a28030877306cdd6` |
| EA-4E.28 | `3a5f0bff52dafd3fb68cfbd483803634c44c68f8f79fbad6a24fcbf15141eda1` |
| EA-4E.29 | `7711cbec4f094f9e3e2df5aa6f6b2d6860c9db28a4f40a8ce9cc5935233390b6` |

These are candidate hashes, not production authorities. A roll must preserve
7.7.9 as historical lineage, update exact source constants and tests, and
requalify the affected chain against staged and committed trees. Metadata
success is not evidence of task transport or provider behavior. No live
receiver/model work is authorized by this candidate diff.

Focused static and inherited fake-only tests: 57 passed / 0 failed.

`KILO_7_8_3_CANDIDATE_ID_COUNT=13`

`PRODUCTION_PIN_CHANGED=NO`

`PRODUCTION_ACTIVATED=NO`
