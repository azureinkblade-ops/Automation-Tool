# EA-4E.92TC start-error classifier candidate

Date: 2026-10-27

The one approved 92TB tags-only native diagnostic failed at `docker
container start`; no log category was produced. This source-only candidate
adds an opt-in fixed-category classifier for the bounded Docker CLI start
stderr. It never reports raw stderr or paths. On a start denial, the
diagnostic also re-inspects exact ownership and full containment before
reading at most one bounded startup log from a verified stopped container.
If the log is unavailable or unclassified, it uses the fixed CLI category.
If the process is running, it preserves the fixed start denial and does
not read logs. Other Docker commands and the ordinary no-logging tags path
retain their existing failure behavior.

Focused strict non-live tests passed 68/68, including rejected-start,
CLI-category fallback, fixed stderr redaction, recheck containment,
running-process denial, no inference, and exact cleanup fakes. No Docker,
Ollama, model, GPU, receiver, or handoff call ran for this candidate.
The fake suite does not prove native behavior or identify the 92TB start
failure's cause.

The new committed source requires one independent read-only review.
Any subsequent native run requires new exact one-shot authorization that
explicitly accepts transient Docker-local logging. Production remains
HOLD.
