# EA-4E.92PQ Retained First-Child Ownership

Status: SOURCE-ONLY CANDIDATE / NATIVE INSTALL HOLD. Parent:
`ee73b6af347b41f8494427f09fe050abb5019a89`.

The existing first-child fake coordinator disposed the returned handle even
after a successful descriptor screen. That is correct for its fake-only
`Attempt` caller but cannot model the retained no-delete-share ownership
required by a future installer. `AttemptAndRetain` now transfers exactly the
screened handle on success. Parent, create, and descriptor denials or port
exceptions dispose a returned handle and return no ownership. The original
`Attempt` still closes on return, including fail-closed handling of a dispose
exception. No native directory API, installed path, or issuer is connected.

Fake-port cases cover success transfer, collision, descriptor denial,
screen exception, and legacy disposal failure. Focused source tests passed
32/32; the adjacent 92P source matrix passed 57/57. All 49 `Ea4e*.cs`
candidate sources compiled as an ignored diagnostic library. These tests
make no native create or readback claim. Staged-byte equivalence and
post-commit results are recorded in the paired Obsidian continuation note.

This candidate does not establish that a native `CreateDirectory2W` return is
a valid owned handle, that its descriptor/identity matches the screened
bytes, that ProgramData ancestry is protected, or that the app has effective
read-only rights. Independent ABI/security review, a bounded native
qualification, protected installation, trusted issuer, receiver/model
qualification, and production activation remain separate gates. Strict
92AT exact mapped-byte proof remains REJECT/HOLD; the accepted 92DE local
profile is a distinct claim.
