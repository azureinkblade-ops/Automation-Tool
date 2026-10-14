# EA-4E.92JH image-index inspect binding

Status: READ-ONLY DAEMON IDENTITY OBSERVED / TRANSPORT CORRECTED / NO START.
Governing predecessor: `1e97ad052a40a42f07eed599deaa1ed8306d1487`.

The 92JF transport queried `docker image inspect --platform linux/amd64`
with the platform manifest digest as the image reference. A read-only
current-daemon query of that exact digest returned `No such image`.
The pinned local image index remained addressable. A second read-only query
of the index with `--platform linux/amd64` returned the expected platform
manifest as both `Id` and descriptor digest, on Linux/amd64:

- Index: `sha256:c170379623cd8d16feb2c15fcdd473c401275336dc046fe72a5a5075c3474303`
- Manifest: `sha256:2eaab2a5675726461630106859873c29f03641c142ae47c6b6060aebc611504d`
- Docker CLI SHA-256: `c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`

The observer now passes both frozen identities to the read client. The
client queries by index and requires the response `Id` to equal the
manifest, failing closed on malformed identities or a wrong returned ID.
The 92JE and 92JG fake read contracts were updated accordingly. Focused:
21 passed. Adjacent fake-only ladder: 304 passed before commit.

The CLI queries were read-only. No container was created or started, and
no Kilo/OpenCode receiver, model, GPU, or ComfyUI was invoked. There is
still no concrete bounded runner or independently verified container
observation. Historical local image metadata is not mapped-byte proof or
production activation authority. Production remains HOLD.
