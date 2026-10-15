# EA-4E.92KL candidate build-byte closure review

Status: NON-LIVE EVIDENCE / BUILD OUTPUT NOT APPROVED OR INSTALLED.
Governing committed source: `6260bb6326b052faf88294cc232dcf8cece4b3c2`.

Two local builds of the combined 92KJ/92KK preflight used the same three
committed C# source files and the same explicit .NET Framework references.
Each produced a 13,824-byte `preflight.exe`, but their SHA-256 values
differed:

- Build A: `AE5A4B6EB8FCD8184FBB4242E136ED872618C71DFA683B2EDECE061DB152E0F9`
- Build B: `B70EEF4C895FFDBA06C710B079CB7482FC1F54A0369DA5201640DF751D78D0CD`

Exactly 16 byte positions differed, at offsets `0x29D0` through `0x29DF`.
The PE timestamp fields matched in this pair. The field responsible was not
independently decoded, so this evidence does not claim a cause or a
reproducible build. A source hash cannot substitute for approving the exact
compiled executable bytes. Neither output was installed or executed.

| Input | SHA-256 | Observed signature |
| --- | --- | --- |
| `tools/ea4e_docker_operator_preflight.cs` | `46D1970615C50F93114E10E6E8E65F3CA747351A68E3C4D913EC9DDA80C5AABF` | source file |
| `tools/Ea4eNetworkIssueRequestCandidate.cs` | `DDCF137A7426DF8BD5A08C27690F0302C44620EFABE5E60CA79D1380A40DD79C` | source file |
| `tools/Ea4eNetworkIssuePreflightCandidate.cs` | `5F093230D63773711A6D82AB6C4ADDAF6E704BEFCB33BD7A7BB41D23FFB89707` | source file |
| `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` | `46809206887326D2D24DB1EFF1F3064DE972C3451ABE766B49111450A5E08E00` | Valid |
| `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.dll` | `2B3C17C6208A0B4B6BEB94E1A066F99BA06CDB2EA919479E99D47E8C6D96DC71` | Valid |
| `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Core.dll` | `8B898BED54AE8CC61F9C58CC3EB062724F8357D2BDDA338B5D363654ECFF333D` | Valid |
| `C:\Windows\Microsoft.NET\assembly\GAC_MSIL\System.Web.Extensions\v4.0_4.0.0.0__31bf3856ad364e35\System.Web.Extensions.dll` | `5E6378EDC06F5A61920AAADB2ABA839DD3CF302D6192E08AACD4454BA4CFF0B3` | Valid |

The source also declares P/Invoke references to Windows `kernel32.dll` and
`advapi32.dll`. This table records observed local inputs, not a complete
transitive runtime/import, filesystem ACL, or protected-install closure.
The older Framework compiler did not advertise a deterministic-build option
in its local help output; no alternate compiler or download was used.

The next protected-install proposal must identify one exact executable
SHA-256 after build, review its dependency closure and protected destination,
obtain an independent operator approval of those exact bytes, and verify
destination bytes and effective ACL/reparse status before any elevated run.
No UAC, Docker mutation, receiver/model call, GPU, ComfyUI, or production
activation occurred. Production remains HOLD.
