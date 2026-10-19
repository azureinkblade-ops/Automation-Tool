# EA-4E.92MX issuer source-closure inventory

Status: NON-LIVE INVENTORY / NOT AN ISSUER / PRODUCTION HOLD.
Governing commit: `ba236dd34380df05894981154d48ea55017482dc`.

The following working files had Git blob IDs identical to `HEAD:<path>` before
SHA-256 measurement. This is a source inventory, not an approved installation
manifest or independent operator witness.

| Source under `tools/` | SHA-256 |
| --- | --- |
| `Ea4eProtectedIssuerToken.cs` | `cbe7475af48d7cb4d10298466eceace333035c6e80cc9484d8174ad45c866b22` |
| `Ea4eProtectedIssuerImage.cs` | `dc249e39d1a8bd6dec2f0790b46d3a543fd1ccecd63d4c225a56d41e0b4eda1a` |
| `Ea4eProtectedIssuerPolicyCandidate.cs` | `c36ec7018b526701f61c414d8aa01907f6492f17fde6969eb0c0708b163957ef` |
| `Ea4eProtectedIssuerAdmissionCandidate.cs` | `dbd529d61dac0b75e7144c2ae9de97b1217db0edd745d51209f7ccf5734d93be` |
| `Ea4eNetworkMutationGrantCandidate.cs` | `33095f9016dbf6fa796340849eb62f73ab19bb846ad4380890c5790a03014fc3` |
| `Ea4eNetworkGrantV5Digest.cs` | `ff68b5724e3b76d40dfc606cf3e9b89a85647104b383bdaa7978b1e6d081bfa6` |
| `Ea4eNetworkGrantV5Store.cs` | `40e734e20155c810983bd745834fbbea091172bc27142b0244223c398f3a56f9` |
| `Ea4eProtectedSqlite.cs` | `bc13bd2ce3d9a01ef719c8504d414d17d6791878e3a59eb5b358aa80022f9328` |
| `Ea4eProtectedPathTopologyCandidate.cs` | `2f2817bcd78bd62bd9789c0375fb9a31f37d37c989a543384c8b86b307d3d872` |
| `Ea4eProtectedPathAccessCandidate.cs` | `1171eaafe8fc938121139541aed7b7fce70a78552efb583ba459910d35f882ac` |
| `Ea4eProtectedByteSnapshotCandidate.cs` | `23e135491e63899cee4b243128fef390729db43bccc827fb166a707b8efbcd09` |

All 11 compile together with the local .NET Framework 4.8 C# compiler as a
*library* using `System.Web.Extensions.dll`. One path-spelling attempt failed
to locate sources; the absolute-path retry passed. The temporary output DLL
is not a reviewed issuer executable and has no entry point or authority.
Current machine dependency observations (SHA-256):

| Dependency | SHA-256 |
| --- | --- |
| `Framework64/v4.0.30319/csc.exe` | `46809206887326d2d24db1eff1f3064de972c3451abe766b49111450a5e08e00` |
| `Framework64/v4.0.30319/System.Web.Extensions.dll` | `5e6378edc06f5a61920aaadb2aba839dd3cf302d6192e08aacd4454ba4cff0b3` |
| `System32/winsqlite3.dll` | `a9148fbbbb59e40e0be60b6f0f85d286ac55a4558a8a3b1e4ccdcac41bfacfab` |
| `System32/advapi32.dll` | `b864e1468a01a44f1901e03c05c1029e71655dd9abddd6d840bcfff5e7227d44` |
| `System32/kernel32.dll` | `e132eba4166256e2f414b91fe7d5386590bc5ea8626aee5af9c9738383cf2ae1` |

These are observations only. The transitive CLR/OS library set and loader
behavior are not pinned. `Ea4eProtectedSqlite` explicitly imports the system
`winsqlite3.dll`; token and path checks import `advapi32.dll` and `kernel32.dll`.

## Blocking gaps

- No self-contained issuer entry point, protected policy source, independently
  approved policy hash, fixed module search path, or protected installed binary
  exists in this inventory.
- `Ea4eProtectedPathAccessCandidate.DenialForCurrentUnelevatedApp` opens the
  *current process* token and requires it to be unelevated. Inside an elevated
  issuer it therefore cannot observe the ordinary app account's effective
  rights. A separately bound app-token observer or equivalent qualified
  mechanism is needed; do not reinterpret this method as an elevated check.
- 92MW compares caller-supplied observations and returns
  `CANDIDATE_MATCH_NOT_AUTHORITY`; it does not source store/authority/clock or
  operator approval independently. 92MP hashes the executable on disk, not
  mapped image bytes. The strict 92AT route remains REJECT/HOLD.
- No installation/UAC ceremony, Docker action, receiver/model call, GPU,
  ComfyUI, or production activation is authorized by this inventory.

Focused current-tree test gate: the 92MO, 92MP, 92MR, 92MS, 92MV, and 92MW
pytest files passed 79/79. This is candidate behavior evidence, not a
protected-install or production qualification. The next non-live slice should
design and fake-test an elevated issuer's independent app-token/path observer
and complete dependency manifest before requesting a bounded install review.
