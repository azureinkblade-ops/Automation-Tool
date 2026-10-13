"""Bind reviewed dummy config sources to a reserved Linux Kilo ping plan."""

from tools.hermes_core.agent_local_kilo_ping_intent import (
    SQLiteAgentLocalKiloPingIntentStore,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.local_kilo_inert_inputs import verified_inert_mount_sources


def build_agent_local_kilo_mount_candidate(
    intents: SQLiteAgentLocalKiloPingIntentStore,
    attempt_id: str,
    plan: dict,
    prepared: dict,
) -> dict:
    """Return source identities only; no Docker or launch authority is granted."""
    if type(intents) is not SQLiteAgentLocalKiloPingIntentStore:
        raise DelegationIntegrityError("Linux Kilo intent store denied")
    intent = intents.verify_plan(attempt_id, plan)
    try:
        input_source, runtime_source = verified_inert_mount_sources(prepared)
    except (OSError, TypeError, ValueError) as exc:
        raise DelegationIntegrityError("Linux Kilo prepared inputs denied") from exc
    intents.verify_plan(attempt_id, plan)
    return {
        "schema_id": "hermes.agent-local-kilo-mount-candidate/v1",
        "attempt_id": attempt_id,
        "plan_hash": intent.plan_hash,
        "intent_payload_sha256": intent.payload_sha256,
        "prepared_hash": sha256_payload(prepared),
        "mounts": [
            {"source": input_source, "destination": "/reviewed-input", "read_only": True},
            {"source": runtime_source, "destination": "/tmp/kilo-home", "read_only": False},
        ],
        "effective_mounts_checked": False,
        "launch_authorized": False,
    }
