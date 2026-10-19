# EA-4E.92NV native pipe readback probe source

Status: SOURCE-ONLY FIXTURE / NATIVE EXECUTION HOLD.
Governing parent: `dfaf1157999736cd15cb77999728b48ed93585f2`.

The fixture `tests/hermes_core/fixtures/ea4e92nv_native_pipe_readback_probe.cs`
compiles with the existing protected token, descriptor screen, creator, and
readback sources. Its inert `--describe` mode and invalid-input paths are
the only modes executed in this checkpoint. The native mode requires an
elevated expected operator token, a nonempty ceremony ID, and a deadline no
more than two minutes away. It then creates one protected pipe, screens
owner/group/DACL/SACL on the retained handle, and disposes that handle.
The native mode was **not invoked**.

The fixture is intentionally narrower than the 92NK qualification plan. It
does not enable or prove `SeSecurityPrivilege`, exercise a distinct limited
client, test effective write or denied mutation rights, verify second-instance
or remote-client denial, provide durable one-shot accounting, or establish
trusted binary installation. A successful future readback would be only
candidate structural evidence, not a qualified issuer.

Focused source and adjacent 92NT/92NO tests: 27 passed, 0 failed. The
native mode requires a separate exact one-shot authorization binding the
reviewed source commit, compiled executable SHA-256 and path/arguments,
operator, expected token pair, deadline, and cleanup policy. No UAC prompt,
protected pipe, Docker mutation, receiver/model call, production activation,
GPU, or ComfyUI action occurred.
