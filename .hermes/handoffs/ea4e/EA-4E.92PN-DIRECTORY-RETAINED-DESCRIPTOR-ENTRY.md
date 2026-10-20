# EA-4E.92PN Directory Retained-Descriptor Entry

`Ea4eAnnouncementFileDescriptorCandidate.ReadDirectory` now selects the
existing exact directory descriptor policy after the same retained-handle
`GetSecurityInfo` readback path used by file mode. The file-mode entry point
still selects its original, different exact file mask. Both modes request
owner, group, DACL, SACL, and label data. Caller retains handle ownership
and must provide any required privilege scope.

The inert fixture exercises null, zero, and `INVALID_HANDLE_VALUE` wrappers
for the directory entry, plus null for the unchanged file entry. All deny
without bytes before any native read. Static descriptor tests cover the
different directory/file masks; no fixture supplies a valid native directory
handle. Focused suite: 31 passed. Adjacent suite: 371 passed, 3 existing
skips. All 48 `Ea4e*.cs` sources compiled into an ignored diagnostic DLL;
the DLL was not installed.

This checkpoint does not qualify native directory creation, a valid-handle
descriptor read, effective client rights, the installed namespace, the full
92NK issuer, the strict 92AT mapped-byte proof, or production. No directory,
ACL, Docker, receiver/model, GPU, or ComfyUI action occurred. A separately
reviewed adapter and exact one-shot native authorization remain required.
