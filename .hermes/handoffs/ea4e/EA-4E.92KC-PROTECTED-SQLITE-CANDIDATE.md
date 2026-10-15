# EA-4E.92KC protected SQLite dependency candidate

Status: NON-LIVE IMPLEMENTATION / NO GRANT STORE.
Governing source: `162cfe73e52f1e51e98503e3343a1e740247dfff`.

The standalone issuer path needs restart-durable one-shot state. This
checkpoint adds a small C# SQLite wrapper that loads the exact protected
`C:\Windows\System32\winsqlite3.dll` path, uses UTF-8 and bound text
parameters, enables foreign keys and a bounded busy timeout, and closes
statements/connections. Its generic SQL execution method is for fixed schema
and transaction statements only; untrusted request fields must be bound.
It does not define an authorization artifact, issue or claim a grant, create
an authority store, or call Docker.

Read-only DLL preflight on this machine observed version `3.53.4`, a valid
Microsoft Windows signature, TrustedInstaller ownership, and SHA-256
`A9148FBBBB59E40E0BE60B6F0F85D286AC55A4558A8A3B1E4CCDCAC41BFACFAB`.
The candidate wrapper source SHA-256 during this checkpoint was
`DE0040905ADA03D5873742FAF16FA2F3CCFA57C64092065AD54647F5E25FD27F`.
These are local observations, not an installation trust attestation. The
protected runtime and native-library identity must be reverified at any
separately authorized issuer installation.

`tests/hermes_core/fixtures/ea4e92kc_sqlite_probe.cs` and the focused
pytest module compile a disposable test executable and verify bound text
with quotes and Unicode, transaction commit, rollback, reopen, cross-language
Python SQLite readback, Unicode file path, and rejection of relative paths.
Focused tests passed 3/3. The adjacent fake-only regression ladder and
committed-tree verification remain required for checkpoint acceptance.

The wrapper intentionally does not decide whether a database path has a
protected ACL, store identity/epoch, rollback anchor, or one-shot issuance
semantics. Those are the next issuer/store implementation gates. No UAC,
Docker mutation, receiver/model call, GPU, ComfyUI, or production activation
occurred. Production remains HOLD.
