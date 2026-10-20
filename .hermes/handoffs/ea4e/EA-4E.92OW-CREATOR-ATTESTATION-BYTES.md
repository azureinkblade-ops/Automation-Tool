# EA-4E.92OW creator attestation bytes

Status: NON-LIVE SYNTAX CHECK / CHANNEL AUTHENTICATION HOLD.
Governing parent: `50ec7e370f4d4da6fe067ab5a776c1b6d4d46ecb`.

The pure `ea4e92ow_creator_attestation` validator accepts one bounded,
canonical ASCII JSON frame with exact fields for ceremony, fresh nonce,
retained launch PID/creation time, pinned executable and installer digest,
record volume/file ID, record content hash, record descriptor hash, protected
pipe descriptor hash, and issue/deadline times. It rejects duplicate or
unknown fields, noncanonical bytes, malformed/zero identity, wrong digest
shape, mismatched independently pinned launch inputs, stale/future times,
and a second protocol version. The focused mutation matrix passed 40/40.

The returned file identities and hashes are **claims** until the same
connection is authenticated to the retained elevated creator and each is
compared with trusted handle observations. This parser does not read Windows
handles, establish a two-way channel, prove label/SACL policy, compare the
record bytes with the medium handle, or consume a durable ledger. A parser
PASS cannot authorize issuer-pipe use, receiver/model execution, or
production. No native pipe/file, Docker, receiver, model, GPU, ComfyUI, or
production action occurred.

Next: source-only binding of the attestation claims to v2 record bytes and
medium retained-handle observations, followed by independent channel and
installer qualification. Full 92NK and production remain HOLD.
