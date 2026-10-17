# EA-4E.92LL current-token environment audit

Status: READ-ONLY ENVIRONMENT OBSERVATION / PRODUCTION HOLD.
Baseline: `66caa6a6ce7aaa24115179f87029b8f4471841c8`.

The current Codex process reports Low Mandatory Level. Its BUILTIN\Administrators
and local-administrator group memberships are deny-only. This token cannot
be used as the elevated operator token for the 92LK protected-pipe creation
positive. It also cannot be assumed to equal the actual Automation Tool app
token: the app's process, integrity level, enabled groups, and restricting
SIDs were not inspected in this checkpoint.

The earlier 92LF/92LG/92LJ same-process fixture positives therefore prove
only that those read-only Windows APIs behave as expected under the fixture
token outside the filesystem sandbox. They do not establish a same-account
UAC limited/elevated pair or a protected pipe DACL. No pipe was installed,
no UAC prompt occurred, and no issuer, Docker mutation, Kilo/OpenCode call,
model invocation, GPU activity, or production activation occurred.

The next native positive requires a separately bounded probe running under
the actual elevated operator and actual linked limited app tokens, with
exact source/binary identity, temporary object namespace, one-attempt
budget, cleanup, and evidence requirements fixed before execution. Broad
approval to keep working does not supply those runtime identities.
