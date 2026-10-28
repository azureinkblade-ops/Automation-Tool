# EA-4E.92VA PAX consumer review HOLD

Date: 2026-10-28 (America/Phoenix)
Reviewed commit: `f4885653c2ec677d75a4618102511b27406ff09a`
Status: INDEPENDENT SOURCE REVIEW HOLD / NATIVE HOLD / PRODUCTION HOLD

The one approved independent read-only review returned HOLD for 92UZ.
The writer permits a 10 GiB context and uses PAX tar, but the consumer's
fixed offset calculation could reject a valid large member carrying a
PAX size header. Its exact-framing claim was too strong: per-member
padding and all raw header fields were not checked. A descriptor created
by `open_osfhandle` could leak if `os.fdopen` failed.

The reviewer judged the read-sharing-only Windows open appropriate for
excluding ordinary new writer and delete opens while held, but identified
missing tests for active writers, PAX, padding, and descriptor failure.
The review made no edits and ran no tests, real model bytes, Docker,
build, container, GPU, receiver, handoff, or network operation.
Production remains HOLD.
