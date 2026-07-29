# Phase 3 Freeze Prerequisite Remediation Authorization

- **Status:** AUTHORIZED
- **Authorized by:** David
- **Authorized at (UTC):** 2026-07-28T19:36:59Z
- **Authorization source:** Direct user instruction in the active Hermes session
- **Base harness commit:** `a263b31a34f1013a2dbc78a90743bd08c6e0b079`
- **Governance state:** Gate B remains paused; this is a separate remediation lane

## Authorized scope

1. Create a narrowly scoped, isolated remediation lane.
2. Correct fresh-index orchestration ordering so a new isolated database can create chunks before dependent embeddings and finish with truthful `COMPLETED` provenance.
3. Add regression coverage for the fresh isolated-database path.
4. Bind the production embedding adapter to the reviewed immutable MiniLM identity:
   - model ID: `sentence-transformers/all-MiniLM-L6-v2`
   - revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
   - model manifest SHA-256: `c7ccfdb624133e2050b67d34bd4b8c5d870872e2f58fefb0824b5cb58dea8f11`
5. Require explicit offline/local snapshot loading and auditable provenance of the model actually used.
6. Rerun the remediation-specific regression checks and Gate B prerequisite checks.

## Explicitly prohibited

- Qualifying or freezing candidate fixtures.
- Approving or changing threshold policy.
- Building or declaring the Gate B evaluation freeze index.
- Creating `frozen-manifest.json`.
- Creating `frozen-manifest.sha256`.
- Running any OFF or ON evaluation case.
- Calling `build_platform_posts(..., enable_retrieval=True)`.
- Activating retrieval.
- Push, deployment, publication, or release.
- Editing `app.py` or unrelated runtime surfaces.

## Lane file boundary

Expected production and test surfaces are limited to:

- `scripts/aivsb/retrieval/cli.py`
- `scripts/aivsb/retrieval/embed_worker.py`
- narrowly related retrieval provenance/index helpers only if a failing test proves they are required
- retrieval-specific regression tests
- this remediation handoff/witness

No broad cleanup, import reordering, or unrelated refactor is authorized.

## Completion boundary

The lane ends after fresh prerequisite revalidation demonstrates:

- the approved production index path can build against a new isolated database without a foreign-key failure;
- the resulting provenance truthfully records the immutable model ID and revision actually used;
- loading is explicitly offline and bound to the reviewed local snapshot;
- regression tests pass on the exact remediation bytes;
- no prohibited Gate B or Gate C action occurred.

At that point, STOP. Resuming Gate B freeze materialization requires a separate explicit decision after candidate and threshold review.
