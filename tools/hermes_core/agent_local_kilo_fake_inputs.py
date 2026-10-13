"""Stage and recheck revised dummy Kilo config bytes; no container activity."""

from pathlib import Path

from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.local_kilo_inert_inputs import (
    _prepare_planned_inputs,
    _verified_planned_mount_sources,
)


SCHEMA_ID = "hermes.agent-local-kilo-fake-inputs/v1"


def prepare_agent_local_kilo_fake_inputs(
    intents: SQLiteAgentLocalKiloPingIntentStore,
    attempt_id: str,
    v1_plan: dict,
    root: Path,
) -> dict:
    candidate = build_agent_local_kilo_fake_launch_candidate(
        intents, attempt_id, v1_plan,
    )
    prepared = _prepare_planned_inputs(root, candidate["planned_files"], SCHEMA_ID)
    prepared["attempt_id"] = attempt_id
    prepared["candidate_hash"] = candidate["candidate_hash"]
    build_agent_local_kilo_fake_launch_candidate(intents, attempt_id, v1_plan)
    return prepared


def verified_agent_local_kilo_fake_mount_sources(
    intents: SQLiteAgentLocalKiloPingIntentStore,
    attempt_id: str,
    v1_plan: dict,
    prepared: dict,
) -> tuple[str, str]:
    candidate = build_agent_local_kilo_fake_launch_candidate(
        intents, attempt_id, v1_plan,
    )
    if (type(prepared) is not dict
            or set(prepared) != {
                "schema_id", "root", "files", "launch_authorized",
                "attempt_id", "candidate_hash",
            }
            or prepared["attempt_id"] != attempt_id
            or prepared["candidate_hash"] != candidate["candidate_hash"]):
        raise DelegationIntegrityError("revised Kilo input manifest mismatch")
    try:
        sources = _verified_planned_mount_sources(
            prepared, candidate["planned_files"], SCHEMA_ID,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise DelegationIntegrityError("revised Kilo input bytes denied") from exc
    build_agent_local_kilo_fake_launch_candidate(intents, attempt_id, v1_plan)
    return sources
