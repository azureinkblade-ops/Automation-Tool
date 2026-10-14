"""Explicit construction of the read-only Kilo daemon observer."""

import subprocess

from tools.hermes_core.agent_local_kilo_bounded_inspect_runner import (
    BoundedDockerInspectRunner,
)
from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_local_kilo_daemon_observer import (
    AgentLocalKiloDaemonObserver,
)
from tools.hermes_core.agent_local_kilo_docker_read_client import (
    AgentLocalKiloDockerReadClient,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


def build_local_kilo_read_only_observer(
    records: SQLiteAgentLocalKiloContainerRecordStore,
    executable: str,
    executable_sha256: str,
    empty_config_dir: str,
    *,
    popen_factory=subprocess.Popen,
) -> AgentLocalKiloDaemonObserver:
    """Compose exact-ID reads; a match still never authorizes start."""
    if type(records) is not SQLiteAgentLocalKiloContainerRecordStore:
        raise DelegationIntegrityError("Kilo read-only observer store denied")
    runner = BoundedDockerInspectRunner(
        executable, executable_sha256, empty_config_dir,
        popen_factory=popen_factory,
    )
    client = AgentLocalKiloDockerReadClient(
        executable, executable_sha256, runner=runner,
    )
    return AgentLocalKiloDaemonObserver(records, read_client=client)
