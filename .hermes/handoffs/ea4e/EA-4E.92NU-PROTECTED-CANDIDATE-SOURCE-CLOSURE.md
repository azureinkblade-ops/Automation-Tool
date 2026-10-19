# EA-4E.92NU protected candidate source closure

Status: NON-LIVE COMPILE AND REGRESSION CHECK / NATIVE AND PRODUCTION HOLD.
Governing parent: `d28b7890bb76d87ffbd86c9aad11ae356064be0b`.

The 24 committed C# sources matching `tools/Ea4eProtected*.cs`,
`tools/Ea4ePipe*.cs`, `tools/Ea4eNetworkGrantV5*.cs`, and
`tools/Ea4eNetworkMutationGrantCandidate.cs` compile together as a library
with the local .NET Framework compiler and `System.Web.Extensions.dll`.
The compiler SHA-256 is
`46809206887326d2d24db1eff1f3064de972c3451abe766b49111450a5e08e00`.
The local diagnostic DLL SHA-256 is
`01f860c9bb6a5be8e0a1aecdbf9e73f2682864e8b872ed5103f2169b72585083`.
The DLL is ignored output, not an installed or authorized issuer. No entry
point, runtime closure, installation policy, or operator approval is supplied
by this compile check.

The 92NQ, 92NS, 92NL, 92NO, and 92NT adjacent pytest files passed
90/90. They exercise inert store and synthetic descriptor cases. They do
not call the native pipe creator or readback methods.

The 92NK one-shot native qualification remains a separate exact gate. It
must pin the source commit, final executable hash and invocation, operator,
deadline, token pair, and one-attempt budget before creating a protected
pipe. The candidate ledger still lacks trusted independent input sourcing,
protected installation, and an external lineage witness. Strict 92AT
mapped-byte proof remains REJECT/HOLD; the accepted 92DE local-container
profile is a separate contract. No Docker mutation, Kilo/OpenCode receiver,
model, production activation, GPU, or ComfyUI action occurred.
