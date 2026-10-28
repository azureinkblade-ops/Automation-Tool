# EA-4E.92VB PAX-compatible consumer candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

The consumer no longer calculates fixed member offsets. It uses parsed
data offsets, accepts PAX metadata that the writer may need for large
members, checks zero padding after each parsed member, and checks a
zero-only trailer. It still verifies member order, type, selected
metadata, Dockerfile bytes, and six model hashes. Both Windows handle
to-descriptor and descriptor-to-file conversion failures now close
their owned resources. The exclusive read handle remains held through
future consumption and closes on caller failure.

Focused strict fake/source tests passed (141/141). The new tests cover a
PAX extended header, nonzero padding, an existing writer, descriptor
conversion failure, and a synthetic six-file tar from the actual writer.
No real model bytes, Docker build, container, GPU, receiver, agent
handoff, or production activation occurred.

This is logical archive verification, not a byte-for-byte canonical tar
proof. The synthetic PAX case is small, not a native multi-gigabyte
archive. A private ACL must be rechecked, a hard scan/build deadline and
Docker side-effect reconciliation are still absent, and no resulting
image ID or model operation has been verified. Docker build network-none
only governs `RUN` networking; it does not prove offline base resolution.
Independent review and exact native authorization remain separate gates.
Production remains HOLD.
