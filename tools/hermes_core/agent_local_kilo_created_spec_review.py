"""Pure comparison of a provisional Kilo spec and supplied create report."""

from collections.abc import Mapping

from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_host_policy_review import (
    review_reported_kilo_host_policy,
)
from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    verify_provisional_kilo_launch_spec,
)
from tools.hermes_core.local_kilo_image_admission import ImageAdmissionResult


def review_provisional_kilo_created_spec(
    records: SQLiteAgentLocalKiloContainerRecordStore,
    attempt_id: str,
    v1_plan: dict,
    prepared: dict,
    spec: dict,
    container: dict,
    image: dict,
    network: dict,
    *,
    gateway_id: str,
) -> ImageAdmissionResult:
    """Bind reported labels/name to reviewed spec; never permit start."""
    expected = verify_provisional_kilo_launch_spec(
        records.intents, attempt_id, v1_plan, prepared, spec,
    )
    base = review_reported_kilo_host_policy(
        records, attempt_id, v1_plan, prepared, container, image, network,
        gateway_id=gateway_id,
    )
    if base.reason != "HOST_POLICY_REVIEW_ONLY_START_DENIED":
        return ImageAdmissionResult("DENY", "HOST_POLICY_REVIEW_MISMATCH")
    config = container.get("Config") if isinstance(container, Mapping) else None
    host = container.get("HostConfig") if isinstance(container, Mapping) else None
    if not isinstance(config, Mapping) or not isinstance(host, Mapping):
        return ImageAdmissionResult("DENY", "CREATE_REPORT_CONFIG_MISSING")
    if (container.get("Name") != "/" + expected["container_name"]
            or config.get("Labels") != expected["labels"]
            or config.get("Entrypoint") != expected["entrypoint"]
            or config.get("Cmd") != expected["argv"]
            or config.get("WorkingDir") != expected["workdir"]
            or config.get("User") != expected["user"]):
        return ImageAdmissionResult("DENY", "CREATE_REPORT_SPEC_IDENTITY_MISMATCH")
    mounts = container.get("Mounts")
    if not isinstance(mounts, list):
        return ImageAdmissionResult("DENY", "CREATE_REPORT_MOUNTS_MISSING")
    for planned in expected["mounts"]:
        if not any(
            isinstance(observed, Mapping)
            and observed.get("Type") == planned["type"]
            and observed.get("Source") == planned["source"]
            and observed.get("Destination") == planned["target"]
            and type(observed.get("RW")) is bool
            and observed["RW"] is (not planned["read_only"])
            for observed in mounts
        ):
            return ImageAdmissionResult("DENY", "CREATE_REPORT_MOUNT_MISMATCH")
    restart = host.get("RestartPolicy")
    if (not isinstance(restart, Mapping) or restart.get("Name") != "no"
            or restart.get("MaximumRetryCount") not in (None, 0)
            or host.get("UsernsMode") not in (None, "")
            or host.get("UTSMode") not in (None, "")
            or host.get("CgroupnsMode") not in (None, "", "private")
            or host.get("Ulimits") not in (None, [])
            or host.get("DNS") not in (None, [])
            or host.get("DnsSearch") not in (None, [])
            or host.get("Links") not in (None, [])):
        return ImageAdmissionResult("DENY", "CREATE_REPORT_ADDITIONAL_HOST_ACCESS")
    return ImageAdmissionResult("MATCH", "CREATE_SPEC_REVIEW_ONLY_START_DENIED")
