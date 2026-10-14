"""Compare one fresh read-only peer observation to a durable untrusted report."""

from tools.hermes_core.agent_local_kilo_precreate_peer_report import (
    SQLiteAgentLocalKiloPrecreatePeerReportStore,
    _ReportedReadClient,
)
from tools.hermes_core.agent_local_kilo_precreate_peer_review import (
    review_precreate_kilo_peer,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.local_kilo_image_admission import ImageAdmissionResult


def review_fresh_precreate_kilo_peer(
    reports, attempt_id, v1_plan, prepared, spec, issue_request, *,
    read_client=None,
):
    """MATCH is a freshness comparison, never owner or create authority."""
    if type(reports) is not SQLiteAgentLocalKiloPrecreatePeerReportStore:
        raise DelegationIntegrityError("Kilo fresh peer report store denied")
    if read_client is None:
        return ImageAdmissionResult("DENY", "NO_FRESH_PEER_READ_CLIENT")
    if any(not callable(getattr(read_client, name, None)) for name in (
        "inspect_network", "inspect_container", "inspect_image",
    )):
        return ImageAdmissionResult("DENY", "INVALID_FRESH_PEER_READ_CLIENT")
    report = reports.get(attempt_id)
    if (report is None or type(issue_request) is not dict
            or issue_request.get("request_hash") != report.issue_request_hash
            or issue_request.get("network_id") != report.network_id
            or issue_request.get("gateway_id") != report.gateway_id):
        return ImageAdmissionResult("DENY", "PRECREATE_REPORT_ABSENT_OR_CHANGED")
    try:
        network = read_client.inspect_network(report.network_id)
        gateway = read_client.inspect_container(report.gateway_id)
        image = read_client.inspect_image(
            issue_request["gateway_image_index"],
            issue_request["gateway_image_manifest"],
        )
    except Exception:
        return ImageAdmissionResult("DENY", "FRESH_PEER_DAEMON_READ_FAILED")
    if any(type(value) is not dict for value in (network, gateway, image)):
        return ImageAdmissionResult("DENY", "FRESH_PEER_DAEMON_SHAPE_DENIED")
    checked = review_precreate_kilo_peer(
        reports.intents, attempt_id, v1_plan, prepared, spec, issue_request,
        read_client=_ReportedReadClient(network, gateway, image),
    )
    if checked.reason != "PRECREATE_METADATA_MATCH_OWNERSHIP_UNPROVEN":
        return ImageAdmissionResult("DENY", "FRESH_PEER_METADATA_MISMATCH")
    if (report.network_hash != sha256_payload(network)
            or report.gateway_hash != sha256_payload(gateway)
            or report.image_hash != sha256_payload(image)):
        return ImageAdmissionResult("DENY", "FRESH_PEER_BYTES_CHANGED")
    return ImageAdmissionResult(
        "MATCH", "FRESH_PRECREATE_REPORT_MATCH_OWNERSHIP_UNPROVEN",
    )
