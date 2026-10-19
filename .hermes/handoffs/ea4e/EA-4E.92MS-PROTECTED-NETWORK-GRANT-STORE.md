# EA-4E.92MS protected network-grant store candidate

Status: NON-LIVE CANDIDATE / PRODUCTION HOLD.
Parent: `d2efdfbf57719811333284df8323324ac0103216`.

This checkpoint adds a side-by-side v5 durable store for the protected-v1
`network_create` grant bytes from 92MR. The v5 metadata, journal, rows,
row-digest domain, and anchor schema are distinct from the v4 fake store.
Neither database opens under the other schema. No fake grant can be issued
to v5, and no existing v4 fake transition is changed.

The v5 candidate preserves the audited v4 transition shape: append-only
journal generations, one anchor per generation, full reopen verification,
store ID/epoch expectation, duplicate grant/nonce/attempt/target denial,
one-shot claim, expiry, revocation, uncertain state, stale-handle denial,
and fail-closed post-commit anchor gaps. It does not repair an ambiguous
commit/anchor gap or automatically retry it.

Changed files: `tools/Ea4eNetworkGrantV5Digest.cs`,
`tools/Ea4eNetworkGrantV5Store.cs`,
`tests/hermes_core/fixtures/ea4e92ms_network_grant_v5_store_probe.cs`, and
`tests/hermes_core/test_ea4e92ms_network_grant_v5_store.py`.

Working-tree qualification: 125 passed / 0 failed across v5 dedicated,
protected grant, v4 fake store, builder, identity, request binding, and
ceremony tests. Tests use local compiler/probe processes and temporary
SQLite files only. No Docker mutation, receiver/model call, UAC, GPU,
ComfyUI, or production activation occurred.

This store is **not** a production authority. `IssueProtected` receives
caller-supplied expected values; the issuer still needs independently
qualified protected policy, operator/binary/installation witnesses, a
reviewed durable store location and anchor ownership, and a bounded UAC
ceremony. The current app must not open or issue v5 as production. Strict
92AT remains REJECT/HOLD; the accepted 92DE local-container profile is
separate and does not make mapped-image byte proof true.
