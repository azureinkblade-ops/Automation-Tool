# EA-4E.92QN Independent Corrected Volume Review

One separately approved, independent reviewer matched all seven pinned
`<commit>:<path>` blob SHA-1 values at source commit
`3127dc16c98dbdd69d2c908e24836d5a946138b3` before substantive review.
The attributable report is Codex thread
`01a16179-0517-74c3-a051-aaee8e5dc39a`.

No blocking source defect was found in the corrected reader. The 92QL
catchable-exception denial gap and failed-call flag exposure are closed by
source inspection. Ordinary preflight, delegate, and marshaling exceptions
return a denial with zero public flags and no asserted Win32 error; fatal
out-of-memory and stack-overflow exceptions are rethrown. A Boolean native
failure preserves its immediately captured Win32 error while clearing
public flags. `lastError == 0` alone does not mean success; the returned
status is authoritative.

`Read` always supplies the private native reader. The internal `ReadWith`
injection can fabricate a candidate result within the assembly, so it is a
testing seam, not an authority boundary. The helper does not create or
dispose the caller's handle. SafeHandle marshaling protects lifetime during
P/Invoke, but preflight alone is not an atomic reservation. No other pinned
`tools` source referenced the new class.

The inert fixture did not cover non-null closed/invalid handles, other
ordinary exceptions, throws after writing nonzero delegate outputs, or a
failed delegate returning error zero. It does not prove actual marshaler
races, Win32 last-error capture, or unsupported-transport behavior. The
unwired test searches one literal call spelling rather than all possible
future wiring.

Verdicts: corrected unwired source reader **PASS**; authenticated native
issuer and production **HOLD**; strict 92AT mapped-byte proof **REJECT**.
Parent identity/topology, trusted manifest/SID, native persistent-ACL
observation on the intended handle, and limited-client effective rights
remain open. The reviewer ran no tests, made no edits, created no handles,
and invoked no native or live service.

Narrowest next non-live action: extend inert denial cases and wiring guard
on a new pinned revision. Native qualification needs separate exact
authorization. The one-review approval was consumed by this review.
