"""Default-disabled read boundary for exact Kilo container observations."""

from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_created_spec_review import (
    review_provisional_kilo_created_spec,
)
from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    verify_provisional_kilo_launch_spec,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.local_kilo_image_admission import ImageAdmissionResult


class AgentLocalKiloDaemonObserver:
    """Use an injected read client only; no concrete Docker binding exists."""

    def __init__(self, records: SQLiteAgentLocalKiloContainerRecordStore,
                 *, read_client=None):
        if type(records) is not SQLiteAgentLocalKiloContainerRecordStore:
            raise DelegationIntegrityError("Kilo daemon observer record store denied")
        self.records = records
        self.read_client = read_client

    def review(self, attempt_id: str, v1_plan: dict, prepared: dict,
               spec: dict, *, gateway_id: str) -> ImageAdmissionResult:
        """Compare fresh, exact-ID read reports; MATCH still denies start."""
        if self.read_client is None:
            return ImageAdmissionResult("DENY", "NO_DAEMON_READ_CLIENT")
        if any(not callable(getattr(self.read_client, name, None)) for name in (
            "inspect_container", "inspect_image", "inspect_network",
        )):
            return ImageAdmissionResult("DENY", "INVALID_DAEMON_READ_CLIENT")
        expected = verify_provisional_kilo_launch_spec(
            self.records.intents, attempt_id, v1_plan, prepared, spec,
        )
        report = self.records.get(attempt_id)
        if report is None or report.candidate_hash != expected["candidate_hash"]:
            return ImageAdmissionResult("DENY", "CREATED_REPORT_ABSENT_OR_CHANGED")
        try:
            container = self.read_client.inspect_container(report.container_id)
            image = self.read_client.inspect_image(expected["image_manifest"])
            network = self.read_client.inspect_network(report.network_id)
        except Exception:
            return ImageAdmissionResult("DENY", "DAEMON_READ_FAILED")
        if any(type(item) is not dict for item in (container, image, network)):
            return ImageAdmissionResult("DENY", "DAEMON_READ_SHAPE_DENIED")
        return review_provisional_kilo_created_spec(
            self.records, attempt_id, v1_plan, prepared, expected,
            container, image, network, gateway_id=gateway_id,
        )
