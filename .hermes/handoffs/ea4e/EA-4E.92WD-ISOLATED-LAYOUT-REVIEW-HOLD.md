# EA-4E.92WD Isolated layout review hold

Date: 2026-10-31 (America/Phoenix)
Status: INDEPENDENT READ-ONLY REVIEW HOLD / NO NATIVE SETUP OR RUN

David approved one independent read-only review of committed 92WC source at
`a070d195134fa0679729bc276bbd7d29a6b21d52`. The reviewer inspected
committed source and synthetic tests only and returned HOLD for treating the
policy as proof of an isolated Buildx launch. This one-review approval is
consumed. No tests or executables ran during the review.

Findings:
- Immediate path checks do not inspect root ancestors or resolve aliases, so
  an ancestor junction could pass. The synthetic reparse test does not create
  a real junction or validate ancestor behavior.
- The plugin hash and layout inventory are path-based snapshots; bytes or
  targets could change before or after validation. The policy does not hold a
  file handle or prevent replacement through launch.
- An empty config and exact one-plugin tree narrow Docker discovery only if
  the returned mapping is used as the complete process environment, without
  override, while the checked layout remains stable. The policy does not
  enforce that launch contract.

The helper remains a value-only candidate, not a launcher or native gate pass.
The 92VZ standalone probe also remains on HOLD. Next implementation must
bind private ACL/ancestor identity, stable executable bytes and complete
environment to an exact bounded process launch, then receive focused tests,
new independent review, and separate native authorization. No plugin copy,
permission change, Docker/Buildx invocation, container, archive upload, build,
model, GPU, receiver, handoff, or production action ran. Private model bytes
and preserved Docker runtime directories remain untouched. All native build,
model, handoff, and production gates HOLD.
