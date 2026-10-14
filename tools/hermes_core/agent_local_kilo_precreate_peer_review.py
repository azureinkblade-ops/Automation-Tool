"""Read-only pre-create peer comparison; metadata never proves ownership."""

from tools.hermes_core.agent_local_kilo_create_issue_request import (
    build_kilo_create_issue_request,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.local_kilo_image_admission import ImageAdmissionResult


def review_precreate_kilo_peer(
    intents, attempt_id, v1_plan, prepared, spec, issue_request, *,
    read_client=None,
):
    if read_client is None:
        return ImageAdmissionResult("DENY", "NO_PRECREATE_READ_CLIENT")
    if any(not callable(getattr(read_client, name, None)) for name in (
        "inspect_network", "inspect_container", "inspect_image",
    )):
        return ImageAdmissionResult("DENY", "INVALID_PRECREATE_READ_CLIENT")
    if type(issue_request) is not dict:
        return ImageAdmissionResult("DENY", "CREATE_ISSUE_REQUEST_MISMATCH")
    try:
        expected = build_kilo_create_issue_request(
            intents, attempt_id, v1_plan, prepared, spec,
            governing_commit=issue_request["governing_commit"],
            docker_executable_sha256=issue_request["docker_executable_sha256"],
            network_id=issue_request["network_id"],
            gateway_id=issue_request["gateway_id"],
            operator_id=issue_request["operator_id"],
            nonce=issue_request["nonce"],
            requested_ttl_seconds=issue_request["requested_ttl_seconds"],
        )
    except (KeyError, TypeError, DelegationIntegrityError):
        return ImageAdmissionResult("DENY", "CREATE_ISSUE_REQUEST_MISMATCH")
    if issue_request != expected:
        return ImageAdmissionResult("DENY", "CREATE_ISSUE_REQUEST_MISMATCH")
    try:
        network = read_client.inspect_network(expected["network_id"])
        gateway = read_client.inspect_container(expected["gateway_id"])
        image = read_client.inspect_image(
            expected["gateway_image_index"],
            expected["gateway_image_manifest"],
        )
    except Exception:
        return ImageAdmissionResult("DENY", "PRECREATE_DAEMON_READ_FAILED")
    if any(type(value) is not dict for value in (network, gateway, image)):
        return ImageAdmissionResult("DENY", "PRECREATE_DAEMON_SHAPE_DENIED")
    members = network.get("Containers")
    member = members.get(expected["gateway_id"]) if type(members) is dict else None
    gateway_name = gateway.get("Name")
    settings = gateway.get("NetworkSettings")
    network_attachment = settings.get("Networks") if type(settings) is dict else None
    attachment = (network_attachment.get(expected["network_name"])
                  if type(network_attachment) is dict else None)
    state = gateway.get("State")
    config = gateway.get("Config")
    if (network.get("Id") != expected["network_id"]
            or network.get("Name") != expected["network_name"]
            or network.get("Driver") != "bridge"
            or network.get("Internal") is not True
            or network.get("EnableIPv6") is not False
            or type(members) is not dict
            or set(members) != {expected["gateway_id"]}
            or type(member) is not dict
            or type(gateway_name) is not str
            or not gateway_name.startswith("/")
            or member.get("Name") != gateway_name[1:]
            or gateway.get("Id") != expected["gateway_id"]
            or type(state) is not dict or state.get("Running") is not True
            or type(config) is not dict
            or config.get("Image") != expected["gateway_image"]
            or type(attachment) is not dict
            or attachment.get("NetworkID") != expected["network_id"]
            or type(attachment.get("Aliases")) is not list
            or "ea4e-fake-gateway" not in attachment["Aliases"]
            or image.get("Id") != expected["gateway_image_manifest"]
            or image.get("Os") != "linux"
            or image.get("Architecture") != "amd64"):
        return ImageAdmissionResult("DENY", "PRECREATE_PEER_METADATA_MISMATCH")
    return ImageAdmissionResult(
        "MATCH", "PRECREATE_METADATA_MATCH_OWNERSHIP_UNPROVEN",
    )
