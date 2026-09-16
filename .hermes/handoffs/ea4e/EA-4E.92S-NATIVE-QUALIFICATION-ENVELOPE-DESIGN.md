# EA-4E.92S Native Qualification Envelope Design

Date: 2026-09-16
Governing synchronized baseline:
`5cfcbba6c8c3e92b7dbf8cae4ef3bacd201668f6`

State: DESIGN COMPLETE / NATIVE EXECUTION HOLD / NO PROCESS STARTED

## Purpose

Define the separately governed Stage 3 qualification envelope required after
the fake-only broker checkpoint. This document does not authorize or implement
a native adapter, resume a thread, execute a parser, create or modify an
AppContainer profile, change an ACL, open a network listener, or run any probe.

The purpose of Stage 3 is to prove OS containment and owned cleanup with a
dedicated deterministic probe artifact. It is not parser semantic
qualification, SDK inspection, receiver/model execution or production
activation.

## Entry Preconditions

Every item below must be exact and immutable before a positive native launch is
authorized:

- synchronized governing commit and clean tracked tree;
- Windows host identity and OS build;
- absolute Node runtime path, byte length and SHA256 (expected hash currently
  recorded as `3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237`,
  but path and current bytes must be rebound at authorization time);
- dedicated probe/bootstrap artifact path, byte length, SHA256 and license
  provenance;
- parser artifact path, byte length and SHA256 if any parser bytes are staged;
  the existing inert region identity is not a standalone executable identity;
- exact ordered argv and explicit credential-free environment allowlist;
- request-root path plus volume/file identity and no-reparse proof;
- existing AppContainer profile name, binary SID, storage path, volume/file
  identity and no-reparse proof;
- reviewed read/write ACL requirements for runtime, bootstrap and request root;
- exact native broker, process adapter, pre-resume verifier and capture-loop
  source identities;
- framed request/result schemas and byte limits;
- exact network target identities owned by the qualification harness;
- exact cleanup/reconciliation procedure and evidence destination.

Any missing or changed identity is `HOLD`, not an invitation to discover values
during a live run.

## Probe Matrix

The envelope contains at most twelve single-shot probes. Each probe gets a new
request ID and fresh owned job/process resources. There is no retry, fallback,
parallelism or continuation after an unknown containment outcome.

| ID | Probe | Required result |
| --- | --- | --- |
| NQ-01 | Suspended creation and pre-resume verification | Exact job membership, active process count 1, expected AppContainer SID and suspended primary thread; terminate without resume. |
| NQ-02 | Minimal contained start/exit | Dedicated probe starts once, emits one bounded framed result and exits zero. This proves transport only, not parser behavior. |
| NQ-03 | Child-process attempt | Descendant creation is denied by the one-process Job limit; owned worker remains bounded and is cleaned. |
| NQ-04 | Loopback connection attempt | Connection to the exact harness-owned loopback target is denied; no bytes accepted. |
| NQ-05 | Non-loopback outbound attempt | Connection to the exact harness-owned non-loopback target is denied; no external service is contacted. |
| NQ-06 | Forbidden filesystem read | Read of one exact harness-owned file outside the allowed request/profile roots is denied. |
| NQ-07 | Allowed staged-file read | Exact approved bootstrap/input fixture is readable through the frozen staging/ACL policy. |
| NQ-08 | Wall-clock timeout | Non-terminating probe is terminated through owned job/process cleanup by the 10-second deadline. |
| NQ-09 | Process-memory limit | Dedicated allocator cannot exceed 256 MiB; job evidence and owned cleanup are recorded. |
| NQ-10 | Stdout overflow | Incremental capture stops above 4 MiB, terminates owned work and never buffers unbounded output. |
| NQ-11 | Stderr overflow | Incremental capture stops above 64 KiB independently of stdout and cleans owned work. |
| NQ-12 | Broker-death recovery | A separately reviewed controller interruption leaves no surviving owned worker/descendant and produces durable reconciliation evidence. |

NQ-02 through NQ-12 require process start and are therefore outside the current
authorization. NQ-01 also creates a native suspended process and is outside the
current authorization even though no worker code resumes.

## Global Budgets

- maximum native probes in one authorization: 12;
- maximum concurrently owned workers: 1;
- maximum attempts per probe: 1;
- maximum descendants: 0;
- wall clock per probe: 10 seconds unless the timeout probe's controller budget
  is separately frozen;
- process memory: 256 MiB;
- synthetic input: 64 KiB UTF-8;
- stdout: 4 MiB incrementally enforced;
- stderr: 64 KiB incrementally enforced;
- network success budget: 0;
- filesystem escape success budget: 0;
- model/receiver/SDK/browser/GPU/ComfyUI activity: 0.

## Evidence Contract

Each probe record must bind the governing commit, host identity, request ID,
probe ID, runtime/probe/broker hashes, profile and SID identity, job/process/
thread IDs, monotonic start/deadline/end, expected outcome, observed result,
cleanup order and cleanup confirmation. Raw worker output is untrusted and must
not grant authority.

The run must stop immediately on identity drift, unexpected success, unexpected
process count, unbounded output, cleanup ambiguity, surviving owned process,
profile/ACL mismatch, or evidence-write failure. An unknown result blocks every
later probe until reconciliation. Cleanup is limited to exact owned handles and
jobs; machine-wide process termination and unrelated file deletion are
forbidden.

## Machine-Mutation Boundary

This envelope authorizes no profile creation/deletion, loopback exemption,
capability grant, ACL change, firewall change, service installation, package
installation or security-policy mutation. If an existing compatible profile and
staging ACL are unavailable, Stage 3 remains on HOLD and a separate mutation
design/authorization is required.

## Current Blockers

Native execution is not ready because the following remain unbound or absent:

1. dedicated probe/bootstrap artifact and immutable identity;
2. exact ordered argv and credential-free environment;
3. concrete native suspended-process adapter and resume/capture implementation;
4. native pre-resume query adapter;
5. immutable existing profile/SID/storage identity and ACL proof;
6. exact loopback and non-loopback harness-owned network targets;
7. exact forbidden/allowed filesystem fixtures;
8. durable probe-evidence schema/store and broker-death controller design.

## Exit State

`EA4E92S_STAGE3_ENVELOPE_DESIGNED=YES`

`EA4E92S_NATIVE_PROBES_AUTHORIZED=NO`

`EA4E92S_NATIVE_PROBES_EXECUTED=0`

`EA4E92S_NATIVE_CONTAINMENT_QUALIFIED=NO`

`EA4E92S_NEXT_NONLIVE_SLICE=PROBE_BOOTSTRAP_AND_ADMISSION_CONTRACT`
