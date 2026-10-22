# EA-4E.92QP Parent Volume Readback Probe Source

The 92QN-reviewed volume reader is source-qualified but has never been
called on a real retained directory handle. This checkpoint prepares a
separate, read-only probe candidate. Its native mode would bind a supplied
two-minute deadline and ceremony ID, compare the running Windows SID, resolve
the ProgramData known folder, require an exact expected path, open that
existing directory with read-attributes access and no write/create
disposition, call the reviewed reader once, and close its handle. A later
runner must impose its own process deadline; the source only gates entry.

The candidate was compiled, but only its description, malformed arguments,
and expired/out-of-range deadline paths were executed. Focused tests passed
9/9 and the adjacent inert matrix passed 143/143 before staging. The native
mode was not invoked. The probe is not wired to the owner or issuer.

Microsoft documents `FILE_FLAG_BACKUP_SEMANTICS` for opening an existing
directory and `FILE_PERSISTENT_ACLS` as a volume ACL capability flag:

- https://learn.microsoft.com/en-us/windows/win32/fileio/obtaining-a-handle-to-a-directory
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew

A later positive result would qualify only the observed ProgramData handle's
volume flag under the trusted local-host profile. This source does not
authenticate parent topology, manifest/SID provenance, effective client
rights, or a creation-time handle. The known-folder string and no-reparse
open are not complete ancestor-topology proof. The reviewed 92QM reader
remains unwired. Native qualification needs a pinned build, independent
review, and exact one-shot authorization. No native probe, directory
creation, Docker mutation, Kilo/OpenCode/model, GPU, ComfyUI, or production
activation occurred here. Native issuer and production remain HOLD; strict
92AT remains REJECT.
