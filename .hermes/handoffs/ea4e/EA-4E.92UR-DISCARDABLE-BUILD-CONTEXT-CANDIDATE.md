# EA-4E.92UR discardable build-context candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

The source-only staging helper writes the existing six-file pinned tar stream
into one exclusively created, randomly named `.partial` file in a caller-
selected canonical directory. It flushes and syncs the file, checks its
bound and opened-file identity, and renames it to `.ready.tar` only after
the stream completes. The return value is available only on success. On
failure, it deliberately retains the partial file for explicit operator
reconciliation rather than deleting it or offering it to Docker.

Synthetic-only focused tests passed (12/12). They cover complete output,
late failure, and a noncanonical staging directory. No real model bytes
were read or written, and no Docker build, container, Ollama server, model,
GPU, receiver, agent handoff, cloud call, or production activation occurred.

This helper is not a complete build launcher. It does not prevent a separate
actor from mutating a ready file, prove directory-entry crash durability,
bind disk free space, clean retained partial files, or reconcile Docker
side effects. Staging a real approximately 9.3 GB model tar is a material
storage and confidentiality operation and requires a separately reviewed,
exact bounded authorization. Actual Docker build utilities, registry
behavior, resulting image ID, and model operation remain unverified.
Production remains HOLD.
