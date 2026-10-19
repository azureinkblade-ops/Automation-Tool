# EA-4E.92NQ protected network-grant store bootstrap

Status: NON-LIVE BOOTSTRAP QUALIFIED; PRODUCTION ISSUER HOLD.
Parent: `c3b52cc444820d52726eb007bb93560ebb594fc4`.

This checkpoint adds an independent `protected-v1` zero-generation SQLite
schema and separate anchor. It rejects fake-store files, missing or modified
anchors, modified metadata, duplicate initialization, and unqualified rows.
The class has no issue, claim, revoke, uncertain, Docker, receiver, or model
method. A store instance is not an authorization.

Focused test command (stage-2 venv, unique local basetemp):
`python -m pytest -q -p no:cacheprovider --basetemp output/ea4e92nq-pytest-stage2 tests/hermes_core/test_ea4e92nq_protected_store_bootstrap.py`
Result: 12 passed.

Adjacent command with the new bootstrap test, protected grant parser test,
and fake v4 store test: 43 passed, 0 failed.

Remaining HOLD: this bootstrap cannot record a grant transition. It does
not prove protected anchor ownership or rollback resistance against an
operator able to replace both SQLite and anchor files. Durable append-only
issue/claim/revoke/uncertain transitions, independent expected-value sourcing,
installed issuer identity, and native UAC/pipe access remain unqualified.
No Docker mutation, real Kilo/OpenCode/Codex call, credential, model, GPU,
ComfyUI, or production activation occurred.
