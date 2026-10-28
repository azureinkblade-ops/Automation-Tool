# EA-4E.92UT staging review correction

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

The 92UR helper no longer promotes a path by check-then-rename. It creates
one exclusive, randomly named `.unverified.tar` and returns that same path
only after complete streaming and file sync. A bounded output wrapper
checks each write before it reaches disk; failed files remain for explicit
reconciliation, and a caller must never discover candidate tar files by
directory scan. Synthetic-only focused tests passed (13/13), including a
write that would exceed the bound. No real model bytes or native component
ran.

This is a narrower source correction, not a native-ready staging path.
The file remains mutable after return, a failed partial may contain model
bytes, and Windows ACL privacy and crash durability are not proven. A
future build launcher needs a private staging directory, exact storage
budget, final file identity and hash verification, no use of unreturned
files, and reconciliation of any Docker side effects. A new independent
review and exact bounded authorization are required before real staging
or build. Production remains HOLD.
