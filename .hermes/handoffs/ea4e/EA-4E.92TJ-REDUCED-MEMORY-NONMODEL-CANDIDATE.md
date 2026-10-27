# EA-4E.92TJ reduced-memory non-model candidate

Date: 2026-10-27

92TI repeated Docker start exit 128 with Ollama replaced by a sleeping Bash
process, while retaining the six-file read-only model mount and 20 GiB
resource ceiling. The cause remains unknown. The reported Docker daemon memory
is about 15.5 GiB, below that ceiling, but this does not prove causation.

This source-only candidate changes one variable: an opt-in non-model
`reduced_memory_probe` keeps the 92TG pinned image, read-only staged mount,
network-none, no GPU/published ports, four CPUs, 64 PIDs, 2 GiB tmpfs,
requested one-file 16 KiB Docker-local logging, sleeping Bash command,
loopback check, deadlines, fixed-category diagnostics, and exact-owner
cleanup. It reduces only the container memory and swap limits to 8 GiB and
uses a distinct `ea4e92tj-` name. Validation rejects 8 GiB in model-serving
mode or with an arbitrary memory value. The path returns before any HTTP or
inference and does not read model files inside the container.

Focused strict non-live tests passed 80/80 and cover success, failed start and cleanup,
entrypoint isolation, no HTTP/inference, and invalid mode combinations. These
are fakes and do not establish native readiness. No Docker, model, GPU,
receiver, or handoff call occurred for 92TJ. Independent committed-source
review and a separate exact one-shot native authorization are required.
Production remains HOLD.
