# EA-4E.92PV Unwired Native Error Capture

Status: SOURCE-ONLY ABI CANDIDATE / NATIVE INSTALL HOLD. Parent: `a35e9c51332e4c9b76884f5b66e1e33b44852b33`.

The independent 92PT review identified missing immediate Win32 error capture. `Ea4eDirectory2NativeAbiCandidate.InvokeUnwired` now has a five-argument call to the private Unicode `CreateDirectory2W` declaration and copies `Marshal.GetLastWin32Error()` into an `out` value as its next statement. The wrapper deliberately does not screen the returned pointer or enforce a durable one-attempt ceremony; its name reflects that limitation. No production or other candidate source calls it.

The 92PO fixture reflects the wrapper signature without invoking it. A source assertion checks that no other `Ea4e*.cs` tool calls `InvokeUnwired`. The adjacent 92P/92PU suite passed 73/73 and all 51 C# candidate sources compiled. No native export, directory operation, receiver/model, Docker mutation, GPU, ComfyUI, or production action was run.

Still required: a trusted default-deny one-attempt owner; exact path, parent, SID, volume and privilege preflight; descriptor-in-creation scope; screening of zero and `INVALID_HANDLE_VALUE`; ownership of the returned handle; exact-handle shape, path, identity, ACL/label and effective-rights readback; fail-closed uncertain creation and cleanup; independent review; and separate bounded native authorization. Strict 92AT remains REJECT/HOLD.
