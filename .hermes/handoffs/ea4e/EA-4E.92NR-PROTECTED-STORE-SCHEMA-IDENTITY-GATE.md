# EA-4E.92NR protected-store schema and identity gate

Status: NON-LIVE BOOTSTRAP HARDENING / PRODUCTION ISSUER HOLD.
Parent: `6932ac86c1b3f85207b8d94e45ab880882bcb044`.

The 92NQ zero-generation protected store now checks the exact SQLite DDL
and rejects extra tables, views, triggers, and explicit indexes. Its
`OpenExpected` API requires a store ID and epoch supplied by the caller
from outside the database and anchor; mismatch closes the connection and
denies. The method does not itself establish trusted sourcing.

Focused: 18 passed, 0 failed. Combined with the adjacent protected grant
and fake v4 store regressions: 49 passed, 0 failed. Tests used the stage-2
Python venv and unique `output/ea4e92nr-*` base temp directories.

This is not a durable issuer. Replacing both the database and anchor with a
coherent older pair can still escape detection absent a protected external
lineage witness. No issue, claim, revoke, or uncertain transition exists.
No UAC, Docker mutation, receiver/model call, GPU/ComfyUI, or production
activation occurred.
