# EA-4E.92KD mutation-store identity and rollback substrate

Status: NON-LIVE / FAKE-ONLY QUALIFIED CANDIDATE / NO GRANT ISSUANCE.
Governing source: `f233c8aba1e4d7bb8692a1e0400dd9be2c5724da`.

This checkpoint adds a C# SQLite store-identity substrate using the previously
qualified `Ea4eProtectedSqlite` wrapper. A store is initialized with a 64-digit
lowercase hex store ID and positive epoch. It persists schema, store identity,
epoch, generation, hash-chained journal, and per-generation external anchor
files. Reopen verifies the full journal and every anchor against its matching
journal state. A fake event append uses an immediate SQLite transaction and
rejects a stale concurrent handle. Store paths must be absolute.

The source SHA-256 of `tools/Ea4eDockerMutationStoreIdentity.cs` for this
candidate is `584AE7FFA3ED76169AD9840560FF456D35EC8F7D59D219F00C3CE0A3EC9EFAB2`.
The disposable test executable is compiled from this source, the SQLite
wrapper, and `tests/hermes_core/fixtures/ea4e92kd_store_probe.cs`.

Focused Windows tests passed 10/10: reopen and two generations; duplicate
initialization; stale concurrent handle; rollback to an older database while
newer anchors remain; metadata tamper; trailing anchor bytes; removal from
the expected anchor namespace; altered earlier-anchor hash; journal tamper;
and invalid event input. The adjacent fake-only ladder passed 411/411.
Committed-tree requalification is required after the narrow commit.

This is a fail-closed **candidate**, not a proven protection against an
administrator able to roll back both the SQLite database and the anchor
namespace together. Protected storage placement, ACL and reparse checks,
independent anchor retention, install/runtime identity, crash reconciliation,
one-shot issuance and claim semantics, UAC ceremony, and real receiver
qualification remain open. A crash between SQLite commit and anchor creation
leaves the store denied until separately governed recovery; this checkpoint
does not silently repair it. No grant was issued or claimed. No Docker
mutation, Kilo/OpenCode call, model invocation, GPU, ComfyUI, or production
activation occurred. Production remains HOLD.
