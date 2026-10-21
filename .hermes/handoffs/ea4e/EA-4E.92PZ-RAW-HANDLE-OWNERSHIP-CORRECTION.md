# EA-4E.92PZ Raw-Handle Ownership Correction

This non-live source change responds to the independent 92PY HOLD finding.
After a non-sentinel `CreateDirectory2W` return, the owner now brackets
result screening and `SafeFileHandle` construction with a `finally`: either
the wrapper owns the raw handle or `CloseHandle` is attempted on that exact
raw value. A failed raw close throws into the outer uncertain-denial path.
Zero and minus-one are rejected without closing. There remains no production
caller and the native export was not invoked during this checkpoint.

The fixture compiles the complete candidate source set but exercises only
pre-call policy. A source assertion checks the pre-wrapper cleanup edge; it
does not prove actual Windows handle behavior. Focused inert/ABI tests passed
12/12 and the adjacent unique non-live matrix passed 81/81 before staging.

This closes the specific source-level gap reported by 92PY but is **not** an
independent acceptance of the new blob. Known-folder/manifest/SID provenance,
issuer privilege, volume ACLs, first-child absence, native semantics,
effective client rights, and durable one-use remain HOLD. Strict 92AT byte
proof remains REJECT; live receiver and production remain unqualified. A new
independent review must bind to this corrected source before native use.
