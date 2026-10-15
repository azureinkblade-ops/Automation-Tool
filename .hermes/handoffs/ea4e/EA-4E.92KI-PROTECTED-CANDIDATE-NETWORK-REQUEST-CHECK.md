# EA-4E.92KI protected-candidate network-request check

Status: NON-LIVE / PURE CANDIDATE / NOT INSTALLED.
Governing source: `5dff0eb40ca65fc880c96b998115caa1c428a4cc`.

The prior Python 92KA checker runs from the writable worktree and cannot be
the independent protected issuer's request parser. This checkpoint adds a
standalone C# comparison function and a test-only executable probe. It
parses the 92JV builder's actual network-create request bytes, verifies the
canonical ASCII JSON and SHA-256, compares separately supplied governing,
Docker, attempt, operator, network, and label expectations, and denies
altered policy, authority flags, argv, labels, duplicate keys, extra fields,
malformed bytes, and changed expectations. A successful comparison returns
`REQUEST_BYTES_MATCH_ONLY`; it does not issue, persist, witness, or execute.

The strict canonical-ASCII input requirement is narrower than the Python
92KA dict checker. It is the proposed wire format for this candidate only;
the real issuer's input transport and independent expectation sources are
not yet qualified. Test expectations derived from the same request prove
parser compatibility, not independent provenance.

Production source SHA-256:
`DDCF137A7426DF8BD5A08C27690F0302C44620EFABE5E60CA79D1380A40DD79C`.
The test compiler disables default response-file references and explicitly
uses the local .NET Framework `System.dll`, `System.Core.dll`, and
`System.Web.Extensions.dll`. The latter assembly is observed at
`C:\Windows\Microsoft.NET\assembly\GAC_MSIL\System.Web.Extensions\v4.0_4.0.0.0__31bf3856ad364e35\System.Web.Extensions.dll`,
SHA-256
`5E6378EDC06F5A61920AAADB2ABA839DD3CF302D6192E08AACD4454BA4CFF0B3`,
with a valid Authenticode signature. This is an observed dependency, not an
installed or independently attested protected closure.

Focused tests passed 19/19. The adjacent EA-4E.92I/92J/92K fake-only suite
plus 92HJ/92HV/92HY passed 453/453 before commit. Committed-tree rerun is
still required. The C# production source has no process, Docker API,
network, file-write, registry, issuer, or model capability. No UAC, Docker
mutation, receiver/model call, GPU, ComfyUI, or production activation
occurred. Protected deployment, witnessed SID, trusted time/source identity,
store binding, and actual agent handoff remain open. Production remains HOLD.
