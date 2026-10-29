# EA-4E.92VI stdout image-ID build policy candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD

The value-only build policy no longer names an image-ID output file.
Instead it requests Buildx `--quiet` with local `--load`, and retains the
proposed bounded output budget. Docker's current CLI reference describes
`--quiet` as suppressing build output and printing the image ID on success:
https://docs.docker.com/reference/cli/docker/buildx/build/

This removes the policy's prior output-file collision and overwrite path.
Focused synthetic/source tests passed (33/33), including a preexisting
unrelated image-ID file that the policy does not use or change. No Docker,
model, GPU, receiver, handoff, or production action ran.

The policy does not parse stdout or prove the CLI's native output shape.
A later launcher must enforce a byte cap and deadline, reject any extra
output or malformed ID, then independently inspect the exact built image.
The archive's returned-path/ACL proof, builder locality, offline base
resolution, pre-start process limits and daemon cleanup remain separate
gates. A new independent source review is required. Production HOLD.
