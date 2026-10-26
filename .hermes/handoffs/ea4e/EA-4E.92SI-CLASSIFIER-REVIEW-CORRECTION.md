# EA-4E.92SI classifier review correction

Date: 2026-10-26

David authorized one independent read-only review of pinned 92SH commit
`717a6ceeada0a02107c82105026e5267513a5d48`. The reviewer returned
QUALIFIED. For well-framed responses, the classifier reports fixed categories
and metadata without server body text. The tags-only path still returns
before `/api/generate`, and containment and cleanup were unchanged.

The reviewer identified a disclosure path in the shared HTTP parser:
`HTTPResponse.begin()` can raise `BadStatusLine` containing a server-controlled
malformed status line, and the generic `SmokeDenied` was explicitly chained
from that exception. A printed traceback could therefore expose response
text. No native run followed this finding.

This correction suppresses the parser exception context when raising the
generic `SmokeDenied`. A fake regression test formats the full traceback for
a synthetic secret-bearing malformed status line and verifies that it does
not contain the secret. The focused strict non-live suite passed 38/38.
This is not native qualification. The reviewer authorization was consumed;
the corrected shared parser needs a new independent read-only review and a
fresh exact one-shot authorization before any native diagnostic. Production
remains HOLD.
