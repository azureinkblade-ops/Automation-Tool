# EA-4E.92UB local-log control start hold

Date: 2026-10-27
Status: ONE AUTHORIZED NATIVE NON-MODEL RUN FAILED / HOLD

The exactly one authorized 92TZ local-log-only comparison used source commit
`3c2482988ee7af1006a477f82698bb392752b2ec`, with runtime unchanged
from the independently reviewed `a3fad2c094e58cedeee258cc607d3b0ca4252694`.
The entrypoint, runner, imported Docker client, and Docker CLI SHA-256 pins
were checked before invocation. The probe failed at `container start` with
the fixed `Docker CLI command failed` denial. It did not reach the Bash,
cat, loopback, or expected-refused localhost checks. The container was
created and passed pre-start inspect restrictions; the source's `finally`
path attempted exact-owner removal and absence confirmation. A separate
read-only `docker ps -a` query for the 92TZ name prefix found zero residual
containers.

The previous current-host small control with logging disabled passed, while
this otherwise matching control with requested Docker-local logging failed
to start. This is evidence supporting a logging-related hypothesis, not
proof of causation or a diagnosis of the Docker start error. The generic
CLI denial exposes no fixed root-cause category. No raw Docker log was
read. Requested one-file 16 KiB logging is not a hard disk/retention bound.

The one-run authorization is consumed. There was no retry. No Ollama server,
model, GPU, receiver, agent handoff, cloud call, or production activation
ran. Any further native diagnostic requires a new reviewed scope and exact
one-shot authorization. Production remains HOLD.
