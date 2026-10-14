# EA-4E.92JV pure network-create issue request

Status: NON-LIVE REQUEST DATA / NO AUTHORITY.
Governing predecessor: `118dff9a56a7be3a1a4cd78e9e0f59768c88fe78`.

The new pure builder revalidates the reserved Kilo plan and prepared launch
spec, then binds the exact deterministic network name, internal bridge
policy, candidate labels, cleanup owner, source commit, Docker executable
digest and endpoint, operator candidate, nonce, and bounded requested TTL.
It includes the proposed Docker network-create argv only as canonical data.
There is no network ID yet because this is a pre-create request. It has no
authorization ID and its operator/issue/create/launch flags remain false.

David selected the current administrator account with a visible UAC
confirmation as the future operator ceremony boundary. This checkpoint does
not implement or exercise UAC, verify the operator, issue authorization,
consume a budget, or call Docker. An app caller cannot promote the request
to authority by setting an operator name or a flag.

Focused network/Kilo-create request tests passed 20/20. The adjacent
fake-only 92I/92J/HJ/HV/HY ladder passed 361/361 before commit. The builder
has no subprocess, socket, Docker SDK, receiver, or model call path.

Next: implement and qualify the independent UAC-backed operator witness and
durable one-shot network-create issuer/claim from 92JU/92JT. A real network
create, gateway create/start, Kilo create/start, and model call remain
separate boundaries. Production remains HOLD.
