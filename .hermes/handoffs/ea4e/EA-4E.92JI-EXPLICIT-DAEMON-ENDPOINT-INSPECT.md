# EA-4E.92JI explicit daemon endpoint inspect

Status: READ-ONLY ENDPOINT OBSERVED / FAKE TRANSPORT PASS / NO START.
Governing predecessor: `e9b1d46e13c9913b2929845ea65fe2b0d150093c`.

Read-only `docker context inspect desktop-linux` reported the Docker Desktop
Linux engine endpoint `npipe:////./pipe/dockerDesktopLinuxEngine`. A direct
read-only `docker --host <that endpoint> image inspect --platform linux/amd64`
of the frozen image index returned the frozen platform manifest ID. The
92JF inspect argv now pins that endpoint explicitly, instead of relying on
resolution of the mutable `desktop-linux` context name. The executable
hash and exact image/container/network ID checks remain in place.

The focused observer/transport tests passed 21/21 before commit. No Docker
container was created or started, and no Kilo/OpenCode receiver or model
was invoked. Endpoint string binding does not protect against host-admin
or Docker-daemon compromise under the original strict 92AT threat model;
it is evidence only for the approved local-container profile. A concrete
bounded runner, fresh recorded-container observation, and separately
governed receiver authorization are still absent. Production remains HOLD.
