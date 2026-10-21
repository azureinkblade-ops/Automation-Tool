# EA-4E.92PU Retained Directory Shape Source

Status: NON-LIVE SOURCE CANDIDATE ONLY. Parent: `5cf989d2b0d09842e19dd63959a7de9c034414d4`.

The independent 92PT review found the retained directory-handle observation incomplete. `Ea4eDirectory2RetainedShapeCandidate.Read` now accepts only a caller-owned `SafeFileHandle` and does not open, create, close, or delete any path. It reads file type, attributes and reparse tag, link count, final DOS path, and file identity from that handle. It repeats metadata/path/identity observations and denies drift. `Screen` is a pure predicate for disk-backed non-reparse directory shape and exact expected path. The reader returns a candidate result, never an installer success result.

The inert fixture exercises only `Screen` and a null-handle denial; it never invokes the native `Read` method. Focused tests passed 10/10. Adjacent 92P source tests plus this fixture passed 72/72 with isolated pytest import settings; all 51 `Ea4e*.cs` sources compiled as an ignored diagnostic library. No directory or native observer was run.

Remaining HOLD: the caller must prove this is the exact `CreateDirectory2W` returned handle, bind the trusted path and app SID, verify descriptor readback and token-specific effective rights, establish the no-delete share policy, implement a one-attempt native caller with immediate last-error capture, and qualify cleanup and uncertain creation. The strict 92AT mapped-byte requirement remains separate and REJECT/HOLD. No receiver/model or production action is authorized.
