# EA-4E.92US staging review HOLD

Date: 2026-10-28 (America/Phoenix)
Reviewed commit: `627a2657f031766fc9bc147abc2b820bd2cde6e6`
Status: INDEPENDENT SOURCE REVIEW HOLD / NATIVE HOLD / PRODUCTION HOLD

One separately approved independent read-only reviewer found the 92UR
staging helper unsuitable for native use. The absent-destination check and
`os.rename` are not atomic; a new destination can be overwritten on some
platforms, and the partial file can be swapped between its identity check
and rename. The size check happens after streaming, so it does not bound
peak disk use. Retained partial files can contain private model bytes, and
`0o600` does not prove a private Windows ACL on the staging directory.

The reviewer confirmed that incomplete streams do not return a ready path,
but found no test for collision, replacement, excessive output, sync and
rename failures, or retained-partial handling. The review made no edits and
ran no tests, real model bytes, Docker, build, container, model, GPU,
receiver, handoff, or network operation. Production remains HOLD.
