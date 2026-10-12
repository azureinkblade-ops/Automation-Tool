# EA-4E.92HY Default-Disabled Text Process Owner

Status: NON-LIVE / INJECTED FAKE CONTROLLER / PRODUCTION_READY=NO.

`AgentTextProcessOwner` now connects an accepted ping command, its durable
intent, exact bridge, delegated authorization claim and start fence, and
the reported start/terminal store. It defaults to no controller. A supplied
controller must independently prepare a matching command before the claim.
Only the in-flight caller receiving `FENCED` can make one `start` call;
replay with a fence or reported start is reconciliation-only. Start and
wait ambiguity never cause a second call. A kill request is recorded as
requested, not as proof of process termination.

Qualification: 7 focused tests; 205 affected tests passed, 0 failed.
Kilo and OpenCode fake controllers exercised one reported terminal,
default denial, command mismatch, uncertain start, wait fault, start-report
fault, cancellation, and replay. No terminal capture, result, or mailbox
delivery is produced by this owner.

The injected test controller fabricates PID and bytes. No real executable,
receiver, model, network, Docker, GPU, ComfyUI, or production activation was
invoked. A concrete controller still needs exact binary/image, model,
credential/egress, environment, and command qualification; owned process
handle plus raw-byte observation; bounded retention; confirmed containment;
and crash reconciliation. The claim/fence does not attest process start,
and a reported terminal is not a trusted result.
