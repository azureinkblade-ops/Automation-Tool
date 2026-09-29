# EA-4E.92AY Independent Windows Identity Review

## Reviewer and Binding

- Reviewer identity: Hermes Agent (xAI grok-4.6), independent of the 92AW/92AX authoring pass
- Review date: 2026-09-29T05:47:49-0700
- Review class: source-only, non-live, documentation-bound
- Baseline commit: `e7600ac520a3e9e34414d6a581ec60718cc85ab1`
- Branch at inspection: `feature/ea4e67-kilo762-roll`
- Worktree HEAD at inspection (not the review subject): `273fc7ef56494556f5fb783a1de0ddea62a1e62f` (packet commit only)
- Packet: `.hermes/handoffs/ea4e/EA-4E.92AY-INDEPENDENT-WINDOWS-IDENTITY-REVIEW-PACKET.md` at `273fc7e`

Blob SHA-1 verification against `e7600ac520a3e9e34414d6a581ec60718cc85ab1` (Measured: `git rev-parse <commit>:<path>`):

| File | Packet blob | Observed blob | Match |
| --- | --- | --- | --- |
| `.hermes/handoffs/ea4e/EA-4E.92AT-NATIVE-IDENTITY-AND-CREATOR-OWNER-DESIGN.md` | `5b3388c4cb9e7b4fa3b7c22753005fcf765dbb38` | `5b3388c4cb9e7b4fa3b7c22753005fcf765dbb38` | YES |
| `.hermes/handoffs/ea4e/EA-4E.92AU-NATIVE-IMAGE-IDENTITY-FEASIBILITY-REVIEW.md` | `43ccf6b630a48a2bc3257ce93fac06d9a90a345e` | `43ccf6b630a48a2bc3257ce93fac06d9a90a345e` | YES |
| `.hermes/handoffs/ea4e/EA-4E.92AW-DEBUG-IMAGE-HANDLE-CANDIDATE-REVIEW.md` | `d709dbd9362d84677f22a79f61899f0893e12820` | `d709dbd9362d84677f22a79f61899f0893e12820` | YES |
| `.hermes/handoffs/ea4e/EA-4E.92AX-DEBUG-PATH-CONTRACT-ROLL-IMPACT-REVIEW.md` | `7042cb77cc9dfa93d13d8202e2e8a9b875c41938` | `7042cb77cc9dfa93d13d8202e2e8a9b875c41938` | YES |
| `tools/ea4e92s_creation_provenance.py` | `7f482a77cccf4934aad378b3e621ec3cf72b89a2` | `7f482a77cccf4934aad378b3e621ec3cf72b89a2` | YES |
| `tools/ea4e92s_creator_preflight.py` | `56c0ebec3dbc16a44dd4be53184813b0de51dc4a` | `56c0ebec3dbc16a44dd4be53184813b0de51dc4a` | YES |
| `tools/ea4e92s_launch_inputs.py` | `4bd96252dd64f29b595db319357ad6dcd15ae3f3` | `4bd96252dd64f29b595db319357ad6dcd15ae3f3` | YES |
| `tools/ea4e92s_windows_profile.py` | `f86e3ca355a2f742783c3f7443abbb400e36bb70` | `f86e3ca355a2f742783c3f7443abbb400e36bb70` | YES |

No blob mismatch. Review proceeds against those exact Git objects, not later HEAD.

Primary documentation rechecked this session via Microsoft Learn pages listed in the packet. Findings below cite those pages and the frozen blobs. A matching pathname, `FILE_ID_INFO` equality, fake-test result, or this review file is not trusted image binding.

## Windows Host and Filesystem Assumptions

UNVERIFIED. This review did not inspect the live host, volume type, Node image, profile path, or Windows build. The following remain assumptions, not measurements:

- Target is a local NTFS volume on a current Windows 10/11 desktop SKU where `FileIdInfo` actually works. The `FILE_ID_INFO` page lists minimum supported client as "None supported" and server as Windows Server 2012. That page conflict is unresolved for this host.
- `FILE_ID_INFO` uniqueness is "on a single computer" (volume serial + 128-bit file ID). Network redirectors, FAT, subst, and some ReFS cases are out of evidence.
- AppContainer + job + `EXTENDED_STARTUPINFO_PRESENT` + `CREATE_SUSPENDED` + `DEBUG_ONLY_THIS_PROCESS` is an undocumented combination. No host proof exists in this packet.
- DOS-device map and volume mount points are stable between inspection and `CreateProcessW`. That is an assumption, not a proof.

## Threat Model

In scope unless a later live packet narrows it:

- Local filesystem adversary who can create junctions, mount-point reparse, `subst`/`DefineDosDevice` remaps, hard links, or alternate data streams on any prefix of the five 92AT paths, without needing SeDebugPrivilege.
- Concurrent writer who already holds a writable handle or a writable file mapping of the runtime image. Microsoft documents that an existing writable mapping can cause a later exclusive open to fail (`CreateFileW` share-mode table; "Creating a File Mapping Object" exclusive-access guidance).
- Replacement of a path after inspection but before path-based `CreateProcessW`, including delete-pending + recreate under the same name.
- Pre-existing `SEC_IMAGE` section for the same file object, so later file bytes and the already-created image section can diverge.
- Extra debug events (`LOAD_DLL`, `EXCEPTION`) if the wait/continue loop is not strictly bounded to one create-process event.

Out of scope residual:

- Privileged adversary (Administrator/SYSTEM) who can rewrite kernel objects, impersonate, or plant a debugger. Source review cannot close that class.
- Remote/network filesystem identity.

Exact attacker privileges assumed for any later positive receipt: unprivileged local user with write or reparse control over some ancestor, plus any process that already mapped the same executable. If a later design claims to defeat a privileged adversary, that claim is unsupported here.

## Question 1. Process-create debug event image-file handle

**Decision: HOLD**

Proven by documentation (not host behavior):

- `DEBUG_ONLY_THIS_PROCESS` (0x00000002): "The calling thread starts and debugs the new process. It can receive all related debug events using the WaitForDebugEvent function." Process Creation Flags.
- `WaitForDebugEvent`: "Only the thread that created the process being debugged can call WaitForDebugEvent." Finite timeout is a documented parameter (`dwMilliseconds`; zero polls, `INFINITE` waits forever).
- On `CREATE_PROCESS_DEBUG_EVENT`, `WaitForDebugEvent` remarks say the debugger receives `u.CreateProcessInfo.hFile` (image file), `hProcess`, and `hThread`.
- `CREATE_PROCESS_DEBUG_INFO.hFile`: "A handle to the process's image file. If this member is NULL, the handle is not valid." Null is a documented, first-class failure. Fail-closed on null or failed `GetFileInformationByHandleEx` is the only documented-safe policy. 92AW states that deny. That deny rule is acceptable as a source rule. It is not evidence that the handle is non-null on the required launch.
- `CREATE_SUSPENDED` (0x00000004): primary thread "is created in a suspended state, and does not run until the ResumeThread function is called." The pages do not say that this flag suppresses `CREATE_PROCESS_DEBUG_EVENT`.
- `DEBUG_EVENT.dwProcessId` / `dwThreadId` identify the process/thread of the event. `GetProcessId` / `GetThreadId` can query owned handles (`PROCESS_QUERY_INFORMATION` or `PROCESS_QUERY_LIMITED_INFORMATION`; `THREAD_QUERY_INFORMATION` or `THREAD_QUERY_LIMITED_INFORMATION`). Binding event IDs to `PROCESS_INFORMATION` and independently to those queries is a supported comparison. The pages do not state that debug-event `hProcess`/`hThread` are the same HANDLE values as `CreateProcessW` outputs. They are additional debugger handles.

Not proven:

- That AppContainer startup attributes, job assignment, `EXTENDED_STARTUPINFO_PRESENT`, `CREATE_UNICODE_ENVIRONMENT`, `CREATE_SUSPENDED`, and `DEBUG_ONLY_THIS_PROCESS` together still deliver `CREATE_PROCESS_DEBUG_EVENT` on the owner thread with a non-null, `FileIdInfo`-queryable `hFile`.
- Access rights on that `hFile`. The structure text says the debugger "can use the member to read from and write to the image file." It does not list a guaranteed `DesiredAccess` mask, and it does not promise `FileIdInfo` success.
- That the first wait returns exactly the expected create-process event for the owned PIDs, with no timeout, no foreign PID, and no extra event, under a finite wait.

Residual: 92AW already labels this a candidate, not a receipt. Independent review agrees. A source-only implementation may encode the null/query-fail deny. It may not treat the handle as reliably present.

## Question 2. File identity and SHA-256 versus mapped executable bytes

**Decision: REJECT**

The question is whether `FILE_ID_INFO` match on event `hFile` and the retained runtime handle, plus a reviewed SHA-256, proves the bytes mapped as the executable image. Documented APIs do not prove that. This is a missing invariant, not an unmeasured host fact.

What those APIs do prove, at most:

- `FILE_ID_INFO`: "The file identifier and the volume serial number uniquely identify a file on a single computer. To determine whether two open handles represent the same file, combine the identifier and the volume serial number for each file and compare them." That is file-object identity of two handles, not image-section content.
- A SHA-256 over bytes read through a retained handle is content of that handle's default data stream at read time. 92AT requires hashing through the same owned handle. That is file-content evidence, not mapped-section evidence.
- Debug `hFile` is "a handle to the process's image file," i.e. the file object, not the `SEC_IMAGE` view. `lpBaseOfImage` is "the base address of the executable image that the process is running." Those are different objects.

Races and mismatches the FILE_ID+SHA-256 pair does not close:

- Hard links share the NTFS file record, so `FILE_ID_INFO` equality is expected. That is same-file, not a counterexample. It also does not distinguish names.
- Alternate data streams: `CreateFileW` documents `file:stream` names. `FILE_ID_INFO` identifies the file, not the stream. A hash of `$DATA` plus a create that mapped another stream, or the reverse, is not excluded by file ID.
- Mutation between hash and section creation: an exclusive open (no `FILE_SHARE_WRITE`, no `FILE_SHARE_DELETE`) can block new write/delete opens while the handle is held (`CreateFileW` share table; `NtCreateFile` ShareAccess remarks). Microsoft also documents that an existing writable mapping can make that exclusive open fail. Failure is deny, not proof that no mapping already exists.
- "Creating a File Mapping Object": the first `CreateFileMapping` creates the mapping object; later callers receive the existing object (`ERROR_ALREADY_EXISTS`). Loader image sections are not shown by that page to be hashed or rebound to later file reads. A pre-existing image section can therefore disagree with a later SHA-256 of the file.
- PE `SEC_IMAGE` mapping is not a byte-for-byte file copy. Hashing file bytes cannot, from these pages, equal hashing process memory at `lpBaseOfImage`.
- Replacement of the path used by `CreateProcessW` after inspection is exactly why 92AT forbids pathname-only proof. File-ID match of debug `hFile` to the retained handle can close the "same file object as inspected" claim if and only if both queries succeed on non-null handles. That still leaves the mapped-bytes claim unproven.
- Selected filesystem/volume: unverified (see assumptions).

Exact attacker privileges for the rejected proof: unprivileged local writer or reparse owner on a path prefix, or any process holding a writable mapping / existing image section of that file. FILE_ID equality plus SHA-256 does not defeat that class.

Missing invariant that would be required before any positive image verdict:

> The bytes the Windows loader mapped as the process executable image at creation, before any resume, are the reviewed SHA-256 payload of the retained runtime file object, with no pre-existing image section, no alternate stream, and no intervening mutation.

No reviewed user-mode API in this packet establishes that invariant. Do not substitute path comparison, file-ID equality, or a file-handle hash for it.

## Question 3. Supported retained-handle no-reparse traversal of all five paths

**Decision: HOLD**

Five 92AT paths (92AT "Boundary to Implement Next"): runtime executable, bootstrap, request artifact, request root, existing AppContainer profile directory.

Committed inspector `tools/ea4e92s_windows_profile.py` is not that walk:

- One profile directory only.
- `CreateFileW(path, 0, FILE_SHARE_READ_WRITE_DELETE=7, NULL, OPEN_EXISTING=3, PROFILE_DIRECTORY_FLAGS=0x02000000|0x00200000, NULL)` then `CloseHandle` in `_cleanup`. Access 0, share read/write/delete, handle not retained.
- 0x02000000 is `FILE_FLAG_BACKUP_SEMANTICS`; 0x00200000 is `FILE_FLAG_OPEN_REPARSE_POINT`. Final-component reparse open, not ancestor validation.
- 92AX correctly refuses to promote this module to the five-path owner.

API ambiguities, rechecked, still unresolved:

1. `OBJECT_ATTRIBUTES.Attributes` documents `OBJ_DONT_REPARSE`: no reparse points followed while parsing the name; encounter returns `STATUS_REPARSE_POINT_ENCOUNTERED`. The `NtCreateFile` winternl parameter text for `ObjectAttributes.Attributes` says the value "can be zero or OBJ_CASE_INSENSITIVE" and does not list `OBJ_DONT_REPARSE`. Packet question 3 required that mismatch to be resolved. Independent review cannot resolve it from these two pages. Using `OBJ_DONT_REPARSE` with user-mode `NtCreateFile` remains an inference.
2. `NtCreateFile` `FILE_DIRECTORY_FILE` compatible `CreateOptions` are listed as only `FILE_SYNCHRONOUS_IO_ALERT`, `FILE_SYNCHRONOUS_IO_NONALERT`, `FILE_WRITE_THROUGH`, `FILE_OPEN_FOR_BACKUP_INTENT`, and `FILE_OPEN_BY_FILE_ID`. `FILE_OPEN_REPARSE_POINT` is documented as its own create option and in remarks (bypass reparse processing for the opened file; never returns `STATUS_REPARSE`). Combining `FILE_DIRECTORY_FILE` with `FILE_OPEN_REPARSE_POINT` is not listed as supported. Do not freeze that pair.
3. `CreateFileW` `FILE_FLAG_OPEN_REPARSE_POINT` is a final-object flag. Absolute-path opens still parse ancestors. Component-relative opens need a retained `RootDirectory` (`OBJECT_ATTRIBUTES.RootDirectory` / `NtCreateFile` alternate name form). No frozen source specifies per-component `DesiredAccess`, `ShareAccess`, `CreateDisposition`, `CreateOptions`, or root-handle lifetime for all five paths.
4. `CreateProcessW` still consumes a path, not the retained runtime handle. Retained no-reparse handles do not bind DOS-device or volume-namespace changes between inspection and path-based creation. Debug `hFile` is the only candidate post-create file object for the executable, and question 2 rejected it as mapped-byte proof. Bootstrap, request artifact, request root, and profile directory have no equivalent create-event handle in this candidate.

No exact user-mode sequence with access/share/disposition/options/root handling and retained handles is present in the frozen blobs. 92AT deferred those values. 92AW/92AX left them unqualified. Independent review will not invent them.

## Question 4. Debugger ownership, bounded wait, cleanup, versioned flags

**Decision: HOLD**

Supported fragments:

- Debugger ownership: create thread must call both `WaitForDebugEvent` and `ContinueDebugEvent`.
- Bounded wait: `WaitForDebugEvent(..., dwMilliseconds)` with a finite value is documented. Timeout returns failure. 92AT sticky `UNKNOWN` on ambiguous cleanup is the correct fail-closed posture. It is design prose, not implemented native cleanup.
- `ContinueDebugEvent` "enables a debugger to continue a thread that previously reported a debugging event." The debugger main-loop page states that a debug event suspends all threads in the debuggee until `ContinueDebugEvent`. `CREATE_SUSPENDED` is a separate creation-time suspend. The pages do not specify the combined suspend-count after `ContinueDebugEvent` without `ResumeThread`. Terminate-without-run therefore still needs an ordered, reviewed sequence (typical sketch: `TerminateProcess` on the owned process, wait for `EXIT_PROCESS_DEBUG_EVENT`, `ContinueDebugEvent`, close image/`hFile`/process/thread handles, no `ResumeThread`). 92AW explicitly does not approve `ContinueDebugEvent`, detach, `ResumeThread`, or termination. That lifecycle is still missing.
- Duplicate attempt: 92AT consumes the attempt before the native call and forbids retry from `UNKNOWN`. Committed source has no native creator that implements that machine.

Versioned exact-flag contract (Measured from `e7600ac` source; equality, not superset):

Required value today:

`CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT`
(`0x00000004 | 0x00000400 | 0x00080000`)

Surfaces that freeze that exact integer:

1. Constructor: `tools/ea4e92s_launch_inputs.py` lines 37-38 (`build_probe_launch_inputs`).
2. Plan validator: `tools/ea4e92s_creator_preflight.py` lines 110-111 (`prepare_creation_call_plan` rejects any other `buffers.inputs.creation_flags`).
3. Receipt validator: `tools/ea4e92s_creation_provenance.py` lines 57-64 (`validate_creation_receipt`: `if type(flags) is not int or flags != required`).
4. AE tests: `tests/hermes_core/test_ea4e92ae_creation_provenance.py` lines 20-21, 51-61 (malformed and extra-bit denial).
5. AF tests: `tests/hermes_core/test_ea4e92af_provenance_observation.py` lines 26-27, 101-103 (including `FLAGS | 0x10`).
6. AP tests: `tests/hermes_core/test_ea4e92ap_launch_inputs.py` lines 39-41 (assert constructed flags).
7. AS tests: `tests/hermes_core/test_ea4e92as_creator_preflight.py` lines 61-62, 114-124 (plan flags and `creation_flags=0` denial).

`DEBUG_ONLY_THIS_PROCESS` is 0x00000002. Adding it without a versioned roll makes plan and receipt validators deny. 92AX is correct that silently adding the bit at the native call would desynchronize call, buffers, plan, and receipt. No arbitrary superset validation is acceptable. `EXACT_FLAGS_ROLLED=NO` in 92AX remains true.

92AX's 71/71 AE/AF/AP/AS claim is not re-executed in this review (non-live, no fixture). It is not evidence that debug flags or native APIs work. This review does not adopt it as proof.

Because the fail-closed continue/detach/terminate-without-run sequence is not documented as a complete ordered contract, and is explicitly unapproved in 92AW, question 4 cannot PASS.

## Unresolved Invariants

1. Non-null, `FileIdInfo`-queryable create-process `hFile` under the required AppContainer/job/debug/suspended flag set on the target build.
2. Mapped executable bytes equal reviewed SHA-256 of the retained runtime file (question 2 REJECT).
3. User-mode `NtCreateFile` acceptance of `OBJ_DONT_REPARSE` despite the narrower winternl Attributes text.
4. Directory open flags that both refuse silent reparse and stay inside the `FILE_DIRECTORY_FILE` compatibility list.
5. Component-walk `DesiredAccess` / share / disposition / options / root retention for all five paths, including no-delete share versus pre-existing runtime opens.
6. DOS-device and volume-namespace stability, or a create path that does not re-resolve a Win32 path.
7. Ordered terminate-without-run plus handle cleanup without `ResumeThread` or a second create attempt.
8. Versioned four-flag integer and the corresponding exact-equality tests, if debug is ever accepted.

## Overall Decision (source-only inspector / contract-roll proposal)

**HOLD**

Conditions:

- Trusted native creator stays HOLD. `TRUSTED_IMAGE_BINDING_QUALIFIED=NO`. `TRUSTED_NATIVE_CREATOR=HOLD`.
- Question 2 is REJECT: do not implement or document FILE_ID+SHA-256 as proof of mapped image bytes.
- Questions 1, 3, and 4 remain HOLD. A later source-only fake adapter may encode documented denials (null `hFile`, query failure, flag mismatch, snapshot drift). It may not mint `VERIFIED_SUSPENDED` from a path, file ID, fake, or this review.
- A versioned flags roll is not authorized by this HOLD. Inventory above is the required surface if a later packet authorizes that roll after questions 1-3 are actually closed.
- Even a later PASS on a source-only implementation would not authorize a native process attempt, Node fixture, receiver/model, GPU/ComfyUI, or production activation. Those need a separate exact live authorization after a frozen host/build/image inventory (92AT "Separate Live-Qualification Gate").

## Live / Native / Production Confirmation

This review performed no live or native action:

- `NATIVE_PROCESSES_STARTED=0`
- No host path inspection of runtime, bootstrap, request, profile, or Node image
- No `CreateProcessW`, `WaitForDebugEvent`, `NtCreateFile`, `CreateFileW` against host objects
- No Node fixture, thread resume, receiver, model, GPU, or ComfyUI
- `PRODUCTION_ACTIVATED=NO`
- No production or test source mutation. This file is the independent review artifact only.

`INDEPENDENT_REVIEW_RECEIVED` is a packet field. Do not rewrite the packet bytes. This artifact is the review.

## Finding Category Counts

- Measured: blob match table; exact flag equality sites and line numbers in the four Python modules and AE/AF/AP/AS tests at `e7600ac`.
- Observed: Microsoft Learn page text for the packet-listed APIs, re-fetched this session.
- Inferred: AppContainer/job/debug combination behavior; `ContinueDebugEvent` versus `CREATE_SUSPENDED` suspend-count; `NtCreateFile` actually honoring `OBJ_DONT_REPARSE`. All three stay unlabeled as proof.

## Exit State

`EA4E92AY_INDEPENDENT_REVIEW_COMPLETE=YES`

`Q1_IMAGE_FILE_OBJECT=HOLD`

`Q2_BYTE_IDENTITY=REJECT`

`Q3_NO_REPARSE_TRAVERSAL=HOLD`

`Q4_LIFECYCLE_AND_CONTRACT_ROLL=HOLD`

`OVERALL=HOLD`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`TRUSTED_NATIVE_CREATOR=HOLD`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
