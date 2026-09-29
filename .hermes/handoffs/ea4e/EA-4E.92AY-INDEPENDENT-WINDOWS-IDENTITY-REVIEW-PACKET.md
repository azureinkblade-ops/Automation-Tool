# EA-4E.92AY Independent Windows Identity Review Packet

## Request and Boundary

Review the EA-4E.92AW debug image-handle candidate and 92AX contract-roll
impact independently of their author. This is a read-only, non-live review
request, not a verdict. Use committed baseline
`e7600ac520a3e9e34414d6a581ec60718cc85ab1` on
`feature/ea4e67-kilo762-roll`. Do not modify source, inspect actual
runtime/request/profile paths, invoke native Windows APIs against host
objects, create a process, run the Node fixture, resume a thread, invoke
receivers/models, use GPU/ComfyUI, or activate production under this packet.
Fake-only source inspection and primary API documentation are in scope.

The current status remains `TRUSTED_NATIVE_CREATOR=HOLD`. A reviewer
must not infer approval from a prior fake-test pass, matching pathname,
file-ID equality alone, or this packet's existence.

## Frozen Review Surface

Review the following committed Git blobs. If any blob differs, stop and
rebind the packet before deciding:

| File | Git blob SHA-1 |
| --- | --- |
| `.hermes/handoffs/ea4e/EA-4E.92AT-NATIVE-IDENTITY-AND-CREATOR-OWNER-DESIGN.md` | `5b3388c4cb9e7b4fa3b7c22753005fcf765dbb38` |
| `.hermes/handoffs/ea4e/EA-4E.92AU-NATIVE-IMAGE-IDENTITY-FEASIBILITY-REVIEW.md` | `43ccf6b630a48a2bc3257ce93fac06d9a90a345e` |
| `.hermes/handoffs/ea4e/EA-4E.92AW-DEBUG-IMAGE-HANDLE-CANDIDATE-REVIEW.md` | `d709dbd9362d84677f22a79f61899f0893e12820` |
| `.hermes/handoffs/ea4e/EA-4E.92AX-DEBUG-PATH-CONTRACT-ROLL-IMPACT-REVIEW.md` | `7042cb77cc9dfa93d13d8202e2e8a9b875c41938` |
| `tools/ea4e92s_creation_provenance.py` | `7f482a77cccf4934aad378b3e621ec3cf72b89a2` |
| `tools/ea4e92s_creator_preflight.py` | `56c0ebec3dbc16a44dd4be53184813b0de51dc4a` |
| `tools/ea4e92s_launch_inputs.py` | `4bd96252dd64f29b595db319357ad6dcd15ae3f3` |
| `tools/ea4e92s_windows_profile.py` | `f86e3ca355a2f742783c3f7443abbb400e36bb70` |

The exact-flags behavior is exercised by committed AE, AF, AP, and AS
tests. At 92AX, those existing-contract tests passed 71/71 with both
non-live tripwires at zero. This is not evidence that the proposed debug
flags or native API combination works.

## Questions Requiring Individual Decisions

For each question, record `PASS`, `HOLD`, or `REJECT`, with the precise
API contract/source and residual assumptions. An unsupported inference is
`HOLD`, not `PASS`.

1. **Image-file object:** Does a process created with the required
   AppContainer/job attributes, `CREATE_SUSPENDED`, and
   `DEBUG_ONLY_THIS_PROCESS` reliably yield the process-create event on
   the owner thread with a non-null, queryable `hFile`? Are the event's
   process/thread IDs independently bound to the returned owned handles?
   What is the fail-closed outcome if the handle is null or the query fails?
2. **Byte identity:** Does matching `FILE_ID_INFO` on the event `hFile`
   and retained runtime handle, plus a reviewed SHA-256, prove the bytes
   mapped as the executable image? Address pre-existing image/writable
   mappings, hard links, alternate streams, mutation between read and
   section creation, replacement, and the selected filesystem/volume.
   State exact attacker privileges. If the available documented APIs do
   not prove this, identify the missing invariant rather than substituting
   a path comparison.
3. **No-reparse traversal:** Give a supported user-mode component-walk
   sequence for all five 92AT paths with exact `DesiredAccess`, share,
   disposition, options/flags, root-directory handling, and retained
   handles. Reconcile the `OBJ_DONT_REPARSE` description in
   `OBJECT_ATTRIBUTES` with the narrower `NtCreateFile` parameter text,
   and the `FILE_DIRECTORY_FILE` compatibility list with
   `FILE_OPEN_REPARSE_POINT`. Cover DOS-device/volume namespace changes
   between inspection and path-based process creation.
4. **Lifecycle and contract roll:** Show how debug event ownership,
   finite wait, termination-without-run, `ContinueDebugEvent`/detach,
   primary-thread suspension, and cleanup work without a resume or
   duplicate attempt. Identify every launch/plan/receipt validator and
   test whose exact three-flag value must be versioned if the debug bit
   is accepted. No arbitrary flag-superset validation is acceptable.

## Required Review Output

The independent reviewer should return one signed or attributable
artifact bound to the baseline commit and these blobs. It must contain:

- reviewer identity and review date;
- the four per-question decisions with primary-source links and precise
  source/line references;
- exact proposed Windows host/build and filesystem assumptions, or an
  explicit statement that these remain unverified;
- a threat model and any remaining race or privileged-adversary caveat;
- a single overall `PASS`, `HOLD`, or `REJECT` for a source-only native
  inspector/contract-roll proposal, with conditions for any later live
  probe stated separately;
- confirmation that no live/native/process/receiver/model/GPU/ComfyUI or
  production action was performed as part of the review.

Even an overall `PASS` would only permit a separately authorized,
fake-injected **source-only** implementation/contract roll. It would not
authorize a native process attempt. A missing answer, changed blob,
unresolved API ambiguity, or unproven byte invariant keeps the outcome
`HOLD`.

## Primary Documentation To Recheck

- [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)
- [WaitForDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent)
- [CREATE_PROCESS_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info)
- [ContinueDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-continuedebugevent)
- [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
- [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)
- [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [Creating a file mapping object](https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object)

## Exit State

`EA4E92AY_REVIEW_PACKET_READY=YES`

`INDEPENDENT_REVIEW_RECEIVED=NO`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
