# EA-4E.92QQ Independent Parent Volume Probe Review

One separately approved independent, read-only review inspected the five
pinned `<commit>:<path>` Git blobs at source commit
`936eb90b14262f89fc0d725edd982d193157e4d8`. All five SHA-1 values in
the 92QQ review request matched before substantive review. The attributable
report is Codex thread `01a163af-0b6b-7e43-b255-3c3d1094f496`.

No critical or high-severity source defect was found. The reviewer accepted
the Win32/.NET ABI shapes, read-attributes and existing-object disposition,
one explicit directory-open and one volume query on the positive path, and
owned SafeFileHandle cleanup by source inspection. The reviewer did not
reproduce the reported build hash or run tests.

Two medium qualification limits remain:

1. The deadline is checked only on entry. The ceremony ID is syntactically
   parsed but not authenticated, consumed, or logged. A separately trusted
   one-shot runner must bind identity/action and enforce an external process
   deadline without retry.
2. `FILE_FLAG_OPEN_REPARSE_POINT` can observe a final link itself rather than
   the redirected target; it does not reject reparse points or prove ancestor
   topology. Sharing permits concurrent rename/delete. A positive flag is
   only a volume-capability observation for the handle actually opened, not
   proof of the intended parent, its ACL, effective rights, or issuer authority.

Verdicts: source safety/ABI **PASS**; native qualification readiness **HOLD**;
issuer authority **HOLD**; production **HOLD**; strict 92AT byte invariant
**REJECT**. The reviewer made no edits, builds, native/Docker calls,
receiver/model calls, GPU/ComfyUI use, or production activation. The one
independent-review approval is consumed.

The narrowest next non-live step is a source-only external one-shot runner
contract and denial tests. Any later native volume probe needs an exact new
authorization binding executable SHA-256, Windows SID, independently checked
ProgramData path, fresh ceremony ID, UTC deadline, one invocation, output
capture, and no retry. A positive native result must remain labeled volume
capability only.
