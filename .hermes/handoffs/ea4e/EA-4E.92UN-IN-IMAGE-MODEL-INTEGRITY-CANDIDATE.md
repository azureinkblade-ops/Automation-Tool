# EA-4E.92UN in-image model integrity candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / NATIVE HOLD / PRODUCTION HOLD

The 92UL Dockerfile now includes one build-time `RUN` instruction after the
six exact `COPY` instructions. It counts regular files under `/models`,
denies symlinks there, and runs `sha256sum -c` against the six pinned model
paths. The 92UM minimal-context writer accepts only the corresponding exact
recipe and normalizes Windows CRLF checkout bytes to LF in the tar stream.

Focused strict fake/source tests passed (120/120). No Docker build,
container, Ollama server, model inference, GPU assignment, receiver, agent
handoff, or production activation occurred. The pinned Ollama base image's
availability of `find`, `wc`, and `sha256sum` has not been verified natively;
an absent utility must fail the build, not bypass verification.

This source change is not a complete launcher. A separately reviewed build
path must enforce a bounded local-only context, process and output limits,
no registry push, exact failure reconciliation, and an image-ID check before
use. `--network=none` for Docker build applies to `RUN` instructions and
does not by itself prove that base-image resolution cannot reach a registry.
Any build would need an exact bounded authorization that names storage and
network side effects. Until a successful native build is independently
verified and its resulting content-addressed image ID pinned, the model
remains unqualified. Production remains HOLD.
