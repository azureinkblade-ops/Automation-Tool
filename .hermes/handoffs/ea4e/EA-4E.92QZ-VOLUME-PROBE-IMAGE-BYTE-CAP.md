# EA-4E.92QZ Volume Probe Image Byte Cap

Status: NON-LIVE SOURCE HARDENING PASS / TRUSTED ISSUER AND PRODUCTION HOLD.
Source baseline: `b73b7153f8653da18cc0d5c1f458f92204390e7d`.

The unwired Python volume-probe runner now rejects an opened executable
whose `fstat` size is zero or exceeds 16 MiB. It also counts bytes actually
read and rejects growth beyond that cap before updating the digest. The
observed provisional 92QP probe binary is 8,704 bytes; this limit is not a
production image policy. An oversized-file fixture confirms denial before
process spawn. Focused tests passed 17/17 and the adjacent non-live matrix
passed 160/160 after correcting a test-only module alias typo.

The cap limits byte work, not elapsed time. A single blocked read or `fstat`
can still stall. It does not bind hash bytes to mapped image-section bytes,
protect the executable path from replacement, provide a durable one-use
issuer, or qualify a native run. The 92QU/92QW hard-containment HOLD and
strict 92AT REJECT remain unchanged. No native probe, Docker mutation,
receiver, model, credential, GPU, ComfyUI, or production action occurred.
