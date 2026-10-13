"""Non-launchable comparison of a created container with the revised Kilo candidate."""

from collections.abc import Mapping

from tools.hermes_core.agent_local_kilo_fake_inputs import (
    verified_agent_local_kilo_fake_mount_sources,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.local_kilo_image_admission import (
    ImageAdmissionResult,
    inspect_prestart_image_binding,
)


def inspect_agent_local_kilo_fake_prestart(
    intents, attempt_id, v1_plan, prepared, container, image,
) -> ImageAdmissionResult:
    """Check candidate-bound metadata only; MATCH never grants start authority."""
    try:
        candidate = build_agent_local_kilo_fake_launch_candidate(
            intents, attempt_id, v1_plan,
        )
        input_source, runtime_source = verified_agent_local_kilo_fake_mount_sources(
            intents, attempt_id, v1_plan, prepared,
        )
    except (OSError, TypeError, ValueError) as exc:
        return ImageAdmissionResult("DENY", f"CANDIDATE_OR_INPUT_DENIED:{type(exc).__name__}")

    bound = inspect_prestart_image_binding(container, image)
    if bound.decision != "MATCH":
        return bound
    if not isinstance(container, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_CONTAINER_METADATA")
    config = container.get("Config")
    host = container.get("HostConfig")
    if not isinstance(config, Mapping) or not isinstance(host, Mapping):
        return ImageAdmissionResult("DENY", "MISSING_CONTAINER_CONFIG")
    if (config.get("Entrypoint") != candidate["entrypoint"]
            or config.get("Cmd") != candidate["argv"]):
        return ImageAdmissionResult("DENY", "RECEIVER_COMMAND_MISMATCH")
    if (config.get("User") != candidate["user"]
            or config.get("WorkingDir") != candidate["workdir"]):
        return ImageAdmissionResult("DENY", "RECEIVER_IDENTITY_MISMATCH")
    expected_env = {f"{key}={value}" for key, value in candidate["env"].items()}
    observed_env = config.get("Env")
    if (not isinstance(observed_env, list)
            or any(type(item) is not str for item in observed_env)
            or any("=" not in item for item in observed_env)
            or len(observed_env) != len(set(observed_env))
            or len({item.split("=", 1)[0] for item in observed_env}) != len(observed_env)
            or not expected_env.issubset(set(observed_env))
            or any(item.split("=", 1)[0] in candidate["env"]
                   and item not in expected_env for item in observed_env)):
        return ImageAdmissionResult("DENY", "RECEIVER_ENV_MISMATCH")
    if config.get("ExposedPorts") or host.get("PortBindings") or host.get("PublishAllPorts"):
        return ImageAdmissionResult("DENY", "RECEIVER_PORTS_PRESENT")
    if (host.get("NetworkMode") != candidate["network"]["name"]
            or host.get("ReadonlyRootfs") is not True):
        return ImageAdmissionResult("DENY", "RECEIVER_HOST_POLICY_MISMATCH")
    if (host.get("Privileged") is not False or host.get("CapAdd")
            or host.get("Devices") or host.get("Binds")
            or host.get("PidMode") not in (None, "")
            or host.get("IpcMode") not in (None, "", "private")):
        return ImageAdmissionResult("DENY", "RECEIVER_EXTRA_HOST_ACCESS")
    network_settings = container.get("NetworkSettings")
    networks = network_settings.get("Networks") if isinstance(network_settings, Mapping) else None
    if (not isinstance(networks, Mapping)
            or set(networks) != {candidate["network"]["name"]}):
        return ImageAdmissionResult("DENY", "RECEIVER_NETWORK_MISMATCH")
    mounts = container.get("Mounts")
    expected_mounts = {
        ("bind", input_source, "/reviewed-input", False),
        ("bind", runtime_source, candidate["home_mount"]["destination"], True),
        ("tmpfs", "", candidate["workspace_mount"]["destination"], True),
    }
    if not isinstance(mounts, list) or len(mounts) != len(expected_mounts):
        return ImageAdmissionResult("DENY", "RECEIVER_MOUNT_COUNT_MISMATCH")
    try:
        observed_mounts = {
            (item["Type"], item.get("Source", ""), item["Destination"], item["RW"])
            for item in mounts if isinstance(item, Mapping)
        }
    except (KeyError, TypeError):
        return ImageAdmissionResult("DENY", "RECEIVER_MOUNT_METADATA_MISMATCH")
    if observed_mounts != expected_mounts:
        return ImageAdmissionResult("DENY", "RECEIVER_MOUNT_BINDING_MISMATCH")
    # Namespace identity, tmpfs options, security/resource limits, and peer
    # ownership require independent qualification before any start decision.
    return ImageAdmissionResult("MATCH", "CANDIDATE_METADATA_ONLY_START_DENIED")
