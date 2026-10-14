"""Supplemental, non-authoritative review of reported Docker host policy."""

import re
from collections.abc import Mapping

from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_fake_prestart import (
    inspect_agent_local_kilo_fake_prestart,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.local_kilo_image_admission import ImageAdmissionResult


_ID = re.compile(r"[0-9a-f]{64}\Z")
_TMPFS = frozenset({
    "rw", "nosuid", "nodev", "noexec", "uid=65532", "gid=65532",
    "mode=0700", "size=134217728",
})
_EXPECTED = {
    "NanoCpus": 2_000_000_000,
    "Memory": 2 * 1024 * 1024 * 1024,
    "PidsLimit": 64,
    "ReadonlyRootfs": True,
    "Privileged": False,
    "PublishAllPorts": False,
    "AutoRemove": False,
}


def review_reported_kilo_host_policy(
    records: SQLiteAgentLocalKiloContainerRecordStore,
    attempt_id: str,
    v1_plan: dict,
    prepared: dict,
    container: dict,
    image: dict,
    network: dict,
    *,
    gateway_id: str,
) -> ImageAdmissionResult:
    """Reject incomplete reports; MATCH is never a Docker start decision."""
    if type(records) is not SQLiteAgentLocalKiloContainerRecordStore:
        raise DelegationIntegrityError("Kilo host policy store denied")
    report = records.get(attempt_id)
    if report is None:
        raise DelegationIntegrityError("Kilo created report absent")
    candidate = build_agent_local_kilo_fake_launch_candidate(
        records.intents, attempt_id, v1_plan,
    )
    if report.candidate_hash != candidate["candidate_hash"]:
        raise DelegationIntegrityError("Kilo host policy candidate changed")
    base = inspect_agent_local_kilo_fake_prestart(
        records.intents, attempt_id, v1_plan, prepared, container, image,
    )
    if base.reason != "CANDIDATE_METADATA_ONLY_START_DENIED":
        return ImageAdmissionResult("DENY", "BASE_PRESTART_MISMATCH")
    if (not isinstance(container, Mapping) or not isinstance(network, Mapping)
            or type(gateway_id) is not str or not _ID.fullmatch(gateway_id)
            or gateway_id == report.container_id
            or container.get("Id") != report.container_id):
        return ImageAdmissionResult("DENY", "CONTAINER_IDENTITY_MISMATCH")
    state = container.get("State")
    config = container.get("Config")
    host = container.get("HostConfig")
    net_settings = container.get("NetworkSettings")
    if (not isinstance(state, Mapping) or not isinstance(config, Mapping)
            or not isinstance(host, Mapping) or not isinstance(net_settings, Mapping)
            or state.get("Status") != "created" or state.get("Running") is not False
            or config.get("User") != "65532:65532"):
        return ImageAdmissionResult("DENY", "CREATED_STATE_OR_USER_MISMATCH")
    if any(type(host.get(key)) is not type(value) or host[key] != value
           for key, value in _EXPECTED.items()):
        return ImageAdmissionResult("DENY", "RESOURCE_OR_LIFECYCLE_MISMATCH")
    if (host.get("CapDrop") != ["ALL"]
            or host.get("CapAdd") not in (None, [])
            or host.get("SecurityOpt") != ["no-new-privileges"]
            or host.get("PidMode") not in (None, "")
            or host.get("IpcMode") not in (None, "", "private")
            or host.get("Devices") not in (None, [])
            or host.get("Binds") not in (None, [])
            or host.get("PortBindings") not in (None, {})
            or host.get("ExtraHosts") not in (None, [])
            or host.get("NetworkMode") != candidate["network"]["name"]):
        return ImageAdmissionResult("DENY", "HOST_ISOLATION_MISMATCH")
    tmpfs = host.get("Tmpfs")
    if (not isinstance(tmpfs, Mapping) or set(tmpfs) != {"/work"}
            or type(tmpfs["/work"]) is not str
            or frozenset(tmpfs["/work"].split(",")) != _TMPFS
            or len(tmpfs["/work"].split(",")) != len(_TMPFS)):
        return ImageAdmissionResult("DENY", "WORKSPACE_TMPFS_MISMATCH")
    networks = net_settings.get("Networks")
    attached = networks.get(candidate["network"]["name"]) if isinstance(networks, Mapping) else None
    if (not isinstance(attached, Mapping)
            or attached.get("NetworkID") != report.network_id
            or network.get("Id") != report.network_id
            or network.get("Name") != candidate["network"]["name"]
            or network.get("Driver") != "bridge"
            or network.get("Internal") is not True
            or network.get("EnableIPv6") is not False):
        return ImageAdmissionResult("DENY", "NETWORK_IDENTITY_MISMATCH")
    members = network.get("Containers")
    if (not isinstance(members, Mapping)
            or set(members) != {report.container_id, gateway_id}):
        return ImageAdmissionResult("DENY", "NETWORK_MEMBERSHIP_MISMATCH")
    return ImageAdmissionResult("MATCH", "HOST_POLICY_REVIEW_ONLY_START_DENIED")
