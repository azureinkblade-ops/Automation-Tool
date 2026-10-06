"""Fake-only prestart check for the proposed inert Docker mount probe."""

from __future__ import annotations

from typing import Any, Mapping

from tools.hermes_core.local_kilo_image_admission import (
    ImageAdmissionResult,
    inspect_prestart_image_binding,
)
from tools.hermes_core.local_kilo_inert_inputs import verified_inert_mount_sources
from tools.hermes_core.local_kilo_inert_plan import AGENT_ID


PROBE_COMMAND = (
    "set -eu; "
    "test -r /reviewed-input/config/kilo.jsonc; "
    f"test -r /reviewed-input/.kilo/agents/{AGENT_ID}/{AGENT_ID}.jsonc; "
    "test -r /tmp/kilo-home/config/kilo.jsonc; "
    f"test -r /tmp/kilo-home/.kilo/agents/{AGENT_ID}/{AGENT_ID}.jsonc; "
    "printf 'EA4E_MOUNT_OK\\n' > /tmp/kilo-home/ea4e-mount-marker"
)
PROBE_ENV = [
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME=/tmp/kilo-home",
]


def inspect_inert_mount_probe(
    container: Mapping[str, Any] | None,
    image: Mapping[str, Any] | None,
    prepared: Mapping[str, Any],
) -> ImageAdmissionResult:
    """Compare created-container metadata; never start or authorize it."""
    binding = inspect_prestart_image_binding(container, image)
    if binding.decision != "MATCH":
        return binding
    if not isinstance(container, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_CONTAINER_METADATA")
    config = container.get("Config")
    host = container.get("HostConfig")
    if not isinstance(config, Mapping) or not isinstance(host, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_CONTAINER_CONFIG")
    if config.get("Entrypoint") != ["/bin/sh"] or config.get("Cmd") != ["-ec", PROBE_COMMAND]:
        return ImageAdmissionResult("DENY", "PROBE_COMMAND_MISMATCH")
    if config.get("User") != "65532:65532" or config.get("WorkingDir") != "/work":
        return ImageAdmissionResult("DENY", "PROBE_IDENTITY_MISMATCH")
    if config.get("Env") != PROBE_ENV:
        return ImageAdmissionResult("DENY", "PROBE_ENV_MISMATCH")
    if config.get("ExposedPorts") or host.get("PortBindings") or host.get("PublishAllPorts"):
        return ImageAdmissionResult("DENY", "PROBE_PORTS_PRESENT")

    required = {
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "Privileged": False,
        "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges:true"],
        "PidsLimit": 32,
        "Memory": 67108864,
        "NanoCpus": 250000000,
    }
    if any(host.get(key) != value for key, value in required.items()):
        return ImageAdmissionResult("DENY", "PROBE_HOST_POLICY_MISMATCH")
    if host.get("CapAdd") or host.get("Devices") or host.get("Binds") not in (None, []):
        return ImageAdmissionResult("DENY", "PROBE_EXTRA_HOST_ACCESS")
    if host.get("PidMode") not in (None, "") or host.get("IpcMode") not in (None, "", "private"):
        return ImageAdmissionResult("DENY", "PROBE_NAMESPACE_MISMATCH")

    try:
        input_source, runtime_source = verified_inert_mount_sources(prepared)
    except (OSError, TypeError, ValueError):
        return ImageAdmissionResult("DENY", "PROBE_PREPARED_INPUT_MISMATCH")
    mounts = container.get("Mounts")
    expected = {
        (input_source, "/reviewed-input", False),
        (runtime_source, "/tmp/kilo-home", True),
    }
    if not isinstance(mounts, list) or len(mounts) != 2:
        return ImageAdmissionResult("DENY", "PROBE_MOUNT_COUNT_MISMATCH")
    observed = set()
    for mount in mounts:
        if not isinstance(mount, Mapping) or mount.get("Type") != "bind":
            return ImageAdmissionResult("DENY", "PROBE_MOUNT_TYPE_MISMATCH")
        observed.add((mount.get("Source"), mount.get("Destination"), mount.get("RW")))
    if observed != expected:
        return ImageAdmissionResult("DENY", "PROBE_MOUNT_BINDING_MISMATCH")
    return ImageAdmissionResult("MATCH", "INERT_PRESTART_METADATA_MATCHED")
