# EA-4E.92BA Independent Staging-Proof Review

## Reviewer and scope

- Reviewer: independent review session, AI assistant using Copilot SDK in VS Code
- Review date: 2026-09-29
- Review class: source-only, read-only, documentation-bound
- Subject baseline: `5732a522835ae19c09cb46fb14ba9a2c36625f21`
- Subject branch identified by request: `feature/ea4e67-kilo762-roll`
- Review checkout: `phase3-freeze-harness`, HEAD `f33439398db5a26c1983ba6bf1544cb99b3f4b14`
- Binding: findings below use exact Git objects from the subject baseline, not the review checkout's HEAD.

The review checkout was not the branch named in the request. To avoid repeating the prior integrity mistake, the three governing blobs were verified directly with `git rev-parse <baseline>:<exact-path>` before review. Each matched. No inference is made from the review checkout's branch name or mutable working tree.

| Governing file at baseline | Requested blob SHA-1 | Observed blob SHA-1 | Result |
| --- | --- | --- | --- |
| `.hermes/handoffs/ea4e/EA-4E.92AT-NATIVE-IDENTITY-AND-CREATOR-OWNER-DESIGN.md` | `5b3388c4cb9e7b4fa3b7c22753005fcf765dbb38` | `5b3388c4cb9e7b4fa3b7c22753005fcf765dbb38` | MATCH |
| `.hermes/handoffs/ea4e/EA-4E.92AY-INDEPENDENT-WINDOWS-IDENTITY-REVIEW.md` | `0ec838ef440bbd96e7456508efca9f8574b420cc` | `0ec838ef440bbd96e7456508efca9f8574b420cc` | MATCH |
| `.hermes/handoffs/ea4e/EA-4E.92AZ-MAPPED-IMAGE-PROOF-OPTIONS-REVIEW.md` | `5d96907cb6c08f9b79c7cfdadd529acc2842edc2` | `5d96907cb6c08f9b79c7cfdadd529acc2842edc2` | MATCH |

## Question and governing contract

**Question:** Can private fresh-file staging establish 92AT's post-create, pre-resume assertion that the executable image section represents the reviewed bytes, without substituting matching path, file ID, or a later file hash?

**Governing constraint:** 92AT requires an independently verified suspended image before `VERIFIED_SUSPENDED`; retained handles narrow replacement races but do not themselves prove which image a path-based process-create call mapped (92AT lines 34-43). 92AY Q2 is **REJECT** for file-ID equality plus a file-handle SHA-256 as proof of mapped-image bytes (92AY lines 77-105). 92AZ labels private staging an investigation candidate, not a qualified implementation, and leaves namespace substitution and section-byte correspondence unresolved (92AZ lines 42-74). This review does not relax or rename that invariant.

## Threat model used for the conditional findings

The `PASS` on freshness below is limited to this deliberately narrow model:

- The volume is local NTFS, fixed for the entire attempt; no network redirector, remote volume, removable-media substitution, or unsupported file system is in scope.
- A pre-existing staging directory and every ancestor are protected before use. Their DACLs deny untrusted principals the rights to create, replace, rename, delete, or add reparse points/mount points. All path components and the final directory have been independently checked for reparse redirection. No ancestor is a mount point.
- A dedicated staging service SID is the only non-SYSTEM principal allowed to create or access the staged file. The staging process and all processes holding that SID are trusted. Other unprivileged local processes cannot impersonate that SID, alter its token, or modify its directory/ACL.
- Only one trusted staging owner operates on the per-attempt directory/name; concurrent use by another trusted-SID process is denied by policy.
- SYSTEM, Administrators, kernel-mode code, file-system filters with equivalent authority, backup/restore privilege, and a compromised staging process are out of scope.
- The process-creation path uses the staged file's ordinary unnamed `$DATA` stream, has no colon/stream suffix, and is not redirected through an alternate data stream. Since the file object is newly created, no pre-existing hard link or alternate stream exists. Untrusted principals cannot add one after creation.
- No actor in scope can modify the relevant local or global DOS-device namespace or volume-mount namespace during the attempt. This is a threat-model restriction, not something a retained file handle enforces.

These assumptions are not measurements of the Windows host. The host, volume, ACLs, path ancestors, DOS-device namespace, and actual loader behavior were not inspected.

### Unverified host behavior

- Whether the intended host is local NTFS and supports the needed handle identity queries.
- Whether the proposed creation-time ACL and reciprocal `FILE_SHARE_READ` opens behave as required on that host.
- Whether `CreateProcessW` succeeds with the retained read-only handle and exact staged-file sharing configuration.
- Whether the expected debug event is delivered with a non-null, queryable `hFile` under the exact AppContainer/job/suspended/debug flag combination.
- Whether any host-specific filter, security product, filesystem behavior, or namespace configuration changes the sequence.

## Findings

### 1. Freshness: PASS, conditional on the threat model above

**Documented facts.** Microsoft documents `CREATE_NEW` as creating a new file only if the specified name does not already exist; if it exists, the call fails. `CreateFileW` also accepts a creation-time `SECURITY_ATTRIBUTES` security descriptor. A null descriptor instead selects a default descriptor, so null is not an acceptable substitute for the reviewed ACL. NTFS hard links are additional names for one file on one volume; streams are separate byte streams associated with a file.

**Precise policy needed for this conditional PASS.**

1. The staging directory and its ancestors must already have protected, reviewed DACLs. The DACL must grant only the dedicated staging SID the directory rights needed to create the one child and later remove it, and grant SYSTEM its required management rights. It must not grant untrusted groups write, delete-child, ownership, or ACL-changing rights. Disable inherited ACEs for the staging directory and staged file; do not rely on an inherited/default ACL being safe.
2. At file creation, pass a non-inheritable `SECURITY_ATTRIBUTES` whose security descriptor has a protected DACL granting only the dedicated staging SID the necessary file rights and SYSTEM its management rights. Do not pass `NULL` security attributes.
3. Create one new, ordinary file in that directory with `CREATE_NEW`; never use `CREATE_ALWAYS`, `OPEN_ALWAYS`, or a fallback open mode. A collision or any uncertainty is a denial, not a retry. Use a literal default-stream path with no colon.
4. Treat any failure to establish or verify the directory/ACL/volume assumptions as a denial. Do not accept junctions, symbolic links, mounted folders, or other reparse components in the stage path.

**Inference, bounded by those assumptions.** A successful `CREATE_NEW` under this ACL means the named file did not exist at that location and a new file was created. On the stated local NTFS model, an object created this way has no prior hard-link name, alternate stream, writer, writable mapping, or image section referring to that new object. That conclusion depends on protecting the name and limiting access from creation onward; `CREATE_NEW` alone does not establish those conditions.

**Hard-link, stream, volume, and privileged-actor limits.** A hard link cannot predate the new file object at the new name, but an actor able to create a later hard link elsewhere could add another name; the protected directory and file ACL plus the trusted-service-only assumption exclude that actor. `FILE_ID_INFO` is not stream identity, so the policy must use only the unnamed default stream and prevent untrusted stream creation. No conclusion is made for remote/redirected or unverified volumes. A privileged actor or compromised service can defeat these controls and is explicitly out of scope.

**Primary documentation:** [CreateFileW, `dwCreationDisposition` and `lpSecurityAttributes`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew); [File Streams](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams); [Hard Links and Junctions](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions); [SetSecurityDescriptorControl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptorcontrol).

### 2. Write exclusion: HOLD

**Required candidate sequence, not yet qualified for process creation.**

- **Directory DACL:** protected DACL, no inherited ACEs; allow only the dedicated staging SID `FILE_ADD_FILE`, `FILE_LIST_DIRECTORY`, `FILE_TRAVERSE`, and (for controlled cleanup) `FILE_DELETE_CHILD`; allow SYSTEM the required full management rights. Do not grant untrusted principals write, delete-child, ownership, `WRITE_DAC`, or `WRITE_OWNER` rights.
- **Creation-time file DACL and first handle:** pass a security descriptor with a protected DACL allowing only the dedicated staging SID `GENERIC_READ | GENERIC_WRITE` and SYSTEM `FILE_ALL_ACCESS`; no broad user/group ACEs. Pass `SECURITY_ATTRIBUTES.bInheritHandle = FALSE`. Call `CreateFileW` with `dwDesiredAccess = GENERIC_READ | GENERIC_WRITE`, `dwShareMode = FILE_SHARE_READ`, `dwCreationDisposition = CREATE_NEW`, and `dwFlagsAndAttributes = FILE_ATTRIBUTE_NORMAL`. Do not use `CREATE_ALWAYS`, `OPEN_ALWAYS`, `FILE_FLAG_DELETE_ON_CLOSE`, a colon/stream suffix, or a fallback open mode. Do not create a writable mapping. A name collision denies.
- **Finalize and retain:** write only the approved bytes; flush them; close the write-capable handle. Reopen the same protected path with `dwDesiredAccess = GENERIC_READ`, `dwShareMode = FILE_SHARE_READ`, `dwCreationDisposition = OPEN_EXISTING`, and `dwFlagsAndAttributes = FILE_ATTRIBUTE_NORMAL`. Require the reopened handle's file ID to equal the ID recorded at creation, hash the final unnamed stream through this read-only handle, and retain it through the one `CreateProcessW` attempt and post-create observation. The retained open omits `FILE_SHARE_WRITE` and `FILE_SHARE_DELETE`. Any open, identity, size, hash, or cleanup uncertainty denies. Do not silently retry with broader sharing.
- With the retained handle open, cleanup cannot assume deletion succeeds: its share mode denies delete opens. After process/debug teardown, close the staged-file handle, then delete the private staged name using the explicitly owned cleanup authority. A cleanup failure is sticky `UNKNOWN`; do not retry process creation. Do not use delete-on-close as a shortcut because it changes sharing and lifetime semantics.

**What the documented share rules establish.** A `dwShareMode` of zero blocks later read, write, and delete opens until the handle closes. Omitting `FILE_SHARE_WRITE` also makes a new open fail if an existing writable mapping is present. `FILE_SHARE_READ` permits later read opens but denies later write/delete opens, subject to the reciprocal sharing checks for every open. Thus a writer or writable mapping cannot predate a successful fresh create under the model, and later untrusted writer opens are blocked by the share/DACL policy. A read-only hash after closing the writer handle avoids claiming the earlier write handle is itself a stable read-only pin.

**Why this remains HOLD.** Holding an exclusive (`dwShareMode = 0`) handle across `CreateProcessW` is incompatible with the documented rule that the file cannot be opened again until that handle closes. Executable-image loading is documented as a file-backed image-section operation. Therefore an exclusive handle is not a defensible process-create compatibility choice. The less restrictive retained read-only handle is a plausible candidate, but the reviewed `CreateProcessW` documentation does not specify the loader's exact desired access and share mode for the executable. It is not established that a retained `GENERIC_READ`/`FILE_SHARE_READ` handle is compatible with the loader on all supported hosts. Do not assume this combination works, and do not broaden sharing without a separately reviewed ACL/access argument.

**Existing writer/mapping answer.** Under the stated assumptions, no pre-existing writer or image/writable section can refer to the newly created object. A writer cannot be opened after the read-only retained handle is established without violating its share mode; a writable mapping already present would cause a no-share-write open to fail, which must deny. The trusted staging process must not create such a mapping or continue writing through a retained write handle. This is a policy/inference, not host-tested behavior.

**Primary documentation:** [CreateFileW, `dwShareMode`, `CREATE_NEW`, and `FILE_FLAG_DELETE_ON_CLOSE`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew); [Creating a File Mapping Object](https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object); [Executable Images](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images); [DeleteFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-deletefilew).

### 3. Namespace binding: HOLD

`CreateProcessW` accepts `lpApplicationName` as a string naming the module. It has no parameter for the retained executable file handle. A retained handle therefore does not make the process-create path lookup handle-relative. Private ACLs on the stage directory can block an unprivileged rename/replacement inside that directory, but do not by themselves bind every ancestor, DOS-device mapping, mounted-folder/reparse target, or volume namespace at the time the string is resolved.

The exact fail-closed post-create observation available in this design is:

1. Before any resume, require the expected create-process debug event for the owned process/thread.
2. Require `CREATE_PROCESS_DEBUG_INFO.hFile` to be non-null.
3. Query `FILE_ID_INFO` through both the debug event image-file handle and the retained staged-file handle; require matching volume serial and 128-bit file ID. Query failure, null handle, PID/thread mismatch, or identity mismatch denies and cannot enter `VERIFIED_SUSPENDED`.

This is a useful file-object provenance check, not image-section byte proof. The debug structure documents that `hFile` is a handle to the process image file, but explicitly permits it to be null. `FILE_ID_INFO` compares file-object identity, not the stream contents or a section digest. `lpImageName` is optional metadata and is not a binding mechanism. The check also does not solve races on the other four 92AT paths.

To reduce path races under the narrow threat model, use a fixed, fully qualified path to a protected stage directory on the fixed volume; validate and retain the directory owners, prohibit all untrusted ancestor/namespace changes, and reject every reparse or mount-point component. Those are policy assumptions and inspections. No retained-handle technique in the reviewed API set makes `CreateProcessW` consume that handle directly.

**Primary documentation:** [CreateProcessW, `lpApplicationName`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw); [CREATE_PROCESS_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info); [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info); [Reparse Points](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points); [Determining Whether a Directory Is a Mounted Folder](https://learn.microsoft.com/en-us/windows/win32/fileio/determining-whether-a-directory-is-a-volume-mount-point); [Defining an MS-DOS Device Name](https://learn.microsoft.com/en-us/windows/win32/fileio/defining-an-ms-dos-device-name).

### 4. Mapped-byte binding: REJECT

**Documented facts.**

- Executable images are loaded using a memory-mapped image file/section. The file need not remain open once the section is established.
- `CREATE_PROCESS_DEBUG_INFO.hFile` is an image-file handle and may be null. The structure gives no image-section handle and no digest of section source bytes. `lpBaseOfImage` is an address, not a content attestation.
- `FILE_ID_INFO` establishes that two handles identify the same file on one computer. It does not identify a stream or prove the bytes represented by an image section.
- The `CreateFileMappingW` documentation describes copy-on-write for mapped views and says that for `SEC_IMAGE` the supplied page-protection value has no effect; protections of executable-image views are determined by the executable file. Thus copy-on-write semantics for ordinary mapped views cannot be treated as a byte attestation for an image section, and a process-memory hash is not interchangeable with a raw staged-file hash.
- A pre-existing section is a real concern for a previously existing file: the executable-image documentation says the file need not remain open while the section exists. Fresh staging, private ACLs, and no prior access can exclude a section for the newly created object under the threat model; this materially improves provenance.

**Unresolved byte invariant.** Fresh staging plus write exclusion can make a strong case that the staged default stream remains unchanged after its final hash. The post-create event can, when available, show that the process image-file handle is the same file object. But the reviewed APIs expose no documented mechanism to read or attest the bytes from which that particular created image section was constructed, nor an explicit loader-attested relation that upgrades file-ID equality plus a later file hash into a section-byte proof. Copy-on-write and section-versus-file semantics make hashing the process image an invalid substitute. Treating the causal chain as sufficient would be an inference beyond the requested evidence, not a documented proof.

**Decision.** The 92AT byte invariant remains **REJECT** on this evidence, consistent with 92AY Q2. Do not call `VERIFIED_SUSPENDED` from the staged path, matching file ID, staged-file SHA-256, or a fake test. Private staging can qualify a narrowly scoped file-provenance/immutability claim; it does not qualify the exact mapped-image-byte claim.

**Primary documentation:** [Executable Images](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/executable-images); [Creating a File Mapping Object](https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object); [CreateFileMappingW, `SEC_IMAGE` and page-protection semantics](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw); [CREATE_PROCESS_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info); [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info).

### 5. Contract impact: HOLD

Staging is not a transparent implementation detail for the frozen 92AT contract.

- **Runtime path/hash/file-ID pins:** the staged file is a new file object with a new path and file ID. The original runtime path/file ID cannot silently stand in for the staged identity. A new contract must distinguish the reviewed source runtime from the staged executable, record expected source and staged hashes, and pin the staged volume/file ID/path separately. Hash equality between source and staged files remains provenance of file contents, not image-section proof.
- **Five-path inspector:** 92AT names runtime executable, bootstrap, request artifact, request root, and existing AppContainer profile directory (92AT lines 15-32). Staging changes the executable path being inspected and adds a staging directory/file owner, ACL and cleanup obligations. If the original runtime file also remains a reviewed input, that is an additional separately pinned object. The five-path inspector cannot be reused without a versioned interface change.
- **Exact process flags/debugger lifecycle:** 92AY documents the frozen exact creation flags and equality-enforcing surfaces (92AY lines 129-171). Obtaining the debug event/file handle requires the separately reviewed debug path; adding `DEBUG_ONLY_THIS_PROCESS` is not a harmless extra bit and requires a versioned roll through call-plan construction, validators, receipt rules, and tests. Debug-event ownership, finite waits, event continuation, termination without resume, and cleanup remain unresolved in 92AY Q4 (92AY lines 129-173). Staging itself does not solve those obligations.
- **One-attempt accounting:** 92AT consumes the native process attempt before the call and forbids retries after ambiguous outcomes (92AT lines 56-71). The design must separately define whether file creation, final reopen/hash, and `CreateProcessW` are one staged transaction, how cancellation consumes the attempt, and how any failure cleans the stage. No stage collision, sharing conflict, or ambiguous launch may trigger an alternate path or second process attempt.
- **Cleanup:** retain the staged read handle until post-create checks and owned-process teardown are complete; then close it before deleting the file. Delete only within the protected staging directory. Any uncertain process termination, debug lifecycle, handle close, or staged-file deletion must remain sticky `UNKNOWN`; never reuse the path or treat cleanup failure as success.

**Source-only versus architecture change.** A source-only policy/model can validate intended ACL/share/path rules and deny incomplete evidence. Fake tests can prove that policy rejects bad inputs, but cannot prove Windows loader behavior and must never mint `VERIFIED_SUSPENDED`. Actually creating and launching from a staged file, changing pins/path arguments, adding debug flags, and changing cleanup/accounting is a new architecture contract requiring separate approval and qualification. This review authorizes neither.

**Source references:** 92AT lines 15-43 (five paths and retained-handle limit), lines 47-71 (owner/state/one attempt); 92AY lines 129-173 (debug lifecycle and exact flag contract); 92AZ lines 53-69 (staging obligations and contract impacts).

## Overall disposition for the 92AT byte invariant

**REJECT.** Under the stated narrow local threat model, private fresh-file staging can establish a plausible new-file/no-prior-section provenance condition and can constrain later writes when the DACL and sharing rules hold. It still lacks a reviewed, documented observation proving that the specific executable image section created by the path-based process launch represents the reviewed staged bytes. 92AY Q2 remains controlling. Do not weaken, relabel, or satisfy `VERIFIED_SUSPENDED` with path, file ID, a later file hash, or a fake.

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`

## Narrowest next non-live action

Record an explicit architecture decision: retain/reject the exact 92AT byte invariant, or separately authorize a weaker file-provenance-and-containment claim with a new name, contract, threat model, and independent review. If the exact byte invariant is retained, obtain authoritative Windows loader/filesystem evidence that closes the section-source-byte gap before any source-only positive creator is proposed. No live probe follows from this review.

## Action boundary

This was a read-only review of committed text and public Microsoft documentation. This report is the only file added for the review; no production or test source was changed. No real Windows path/object inspection, native call, process or fixture launch, receiver/model invocation, GPU/ComfyUI action, or production activation occurred. No prohibited action occurred.
