# EA-4E.92OI protected pipe-name announcement boundary

Status: NON-LIVE DESIGN / ANNOUNCEMENT INTEGRITY HOLD.
Governing parent: `8798a5a28cc2cab631267fe06d0d244453e63c97`.

92OE qualified a bounded structural readback. 92OG and 92OH are inert
access-policy and source-only client-open candidates. They do not establish
that a medium-integrity client learns the elevated creator's random pipe
name from the actual creator. Name shape is not an authority credential.

For the accepted 92DE local-container profile, one candidate is an
administrator-owned, preinstalled announcement namespace that the trusted
medium app host can read but cannot create, replace, rename, delete, or
modify. The elevated creator would exclusively create one ceremony-bound
record after protected pipe creation/readback; the record would bind the
ceremony ID, random pipe name, pinned creator executable identity, exact
creator PID/creation time, deadline, and one-use state. The medium
coordinator would read the record from a retained handle, verify the
installed namespace and record owner/DACL, reject reparse/replacement,
compare the pinned launch/process identity and ceremony, and then pass the
name to its separately retained medium client. The record is a routing
announcement, never an authorization or substitute for same-handle
client-token observation.

This is not yet a qualified mechanism. No path, installer, ACL, immutable
record protocol, or restart/cleanup semantics have been frozen or tested.
An ordinary per-user temp file, writable workspace path, process command
line, or unbound stdout is insufficient evidence of creator provenance.
The trusted app-host decision in 92DE does not silently grant trust to
arbitrary same-user processes or satisfy strict 92AT mapped-byte proof.

Next non-live gate: select and qualify the installed namespace and exact
record/handle protocol, including fail-closed stale-record, replay,
replacement, crash, and permission tests. Only after that may a source-only
two-process fixture be composed. A native medium-client run remains
separately governed; no such run occurred here. Production, Kilo/OpenCode
receiver execution, model use, Docker mutation, GPU, and ComfyUI remain off.
