# EA-4E.92UM minimal model build-context candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / NATIVE HOLD / PRODUCTION HOLD

This checkpoint adds a streaming tar context writer for the 92UL pinned
Dockerfile. It includes only `Dockerfile` and the six named qwen3:14b files,
sets fixed tar metadata, bounds total input bytes to 10 GiB, and hashes each
file as it is streamed. It normalizes LF/CRLF checkout differences in the
recipe. It does not invoke Docker, create an image, or run a model.

Focused strict fake/source tests passed (120/120) across the context writer,
recipe, shared container smoke runner, and adjacent Bash transport tests.
No real 9.27 GB model stream was performed. Fake tests do not establish
production readiness.

The digest for a file is known only after its bytes have been sent to the
output stream. A future build launcher must treat any mismatch or stream
failure as a failed build, terminate the exact child, and reconcile any
partial local image/build side effects. The current code does not enforce
the build process deadline, Docker daemon isolation, output bound, disk
budget, or post-build image-internal hashes. The recipe and writer do not
authorize a build. A separately reviewed bounded launcher and exact native
authorization are required before Docker is touched. A built image cannot
be used until its six-file inventory and hashes are independently verified
from the image and its image ID is pinned.

Production remains HOLD.
