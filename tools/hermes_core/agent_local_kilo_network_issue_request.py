"""Pure request for a separately governed, one-shot Docker network create."""

import re

from tools.hermes_core.agent_local_kilo_ping_intent import (
    SQLiteAgentLocalKiloPingIntentStore,
)
from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    verify_provisional_kilo_launch_spec,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ENGINE = "npipe:////./pipe/dockerDesktopLinuxEngine"


def build_kilo_network_issue_request(
    intents, attempt_id, v1_plan, prepared, spec, *,
    governing_commit, docker_executable_sha256, operator_id, nonce,
    requested_ttl_seconds,
):
    """Bind the exact candidate network; never issue or spend authority."""
    if type(intents) is not SQLiteAgentLocalKiloPingIntentStore:
        raise DelegationIntegrityError("Kilo network request intent denied")
    intent = intents.verify_plan(attempt_id, v1_plan)
    expected = verify_provisional_kilo_launch_spec(
        intents, attempt_id, v1_plan, prepared, spec,
    )
    if any(type(value) is not str or not _HEX.fullmatch(value) for value in (
        governing_commit, docker_executable_sha256,
    )):
        raise DelegationIntegrityError("Kilo network request identity denied")
    if (type(operator_id) is not str or not operator_id.strip()
            or type(nonce) is not str or not nonce.strip()
            or type(requested_ttl_seconds) is not int
            or not 0 < requested_ttl_seconds <= 300):
        raise DelegationIntegrityError("Kilo network request input denied")
    network = expected["network"]
    if (expected["credential_class"] != "DUMMY_LOCAL_ONLY"
            or expected["create_authorized"] is not False
            or expected["launch_authorized"] is not False
            or network["internal"] is not True):
        raise DelegationIntegrityError("Kilo network request scope denied")
    labels = dict(expected["labels"])
    labels["hermes.ea4e.cleanup_owner"] = expected["cleanup_owner"]
    argv = ["network", "create", "--driver", "bridge", "--internal"]
    for key, value in sorted(labels.items()):
        argv.extend(("--label", f"{key}={value}"))
    argv.append(network["name"])
    request = {
        "schema_id": "hermes.agent-local-kilo-network-issue-request/v1",
        "action": "network_create",
        "attempt_id": attempt_id,
        "intent_hash": intent.payload_sha256,
        "candidate_hash": expected["candidate_hash"],
        "spec_hash": expected["spec_hash"],
        "governing_commit": governing_commit,
        "docker_executable_sha256": docker_executable_sha256,
        "docker_engine_endpoint": _ENGINE,
        "network_name": network["name"],
        "network_driver": "bridge",
        "network_internal": True,
        "labels": labels,
        "argv": argv,
        "operator_id": operator_id,
        "nonce": nonce,
        "requested_ttl_seconds": requested_ttl_seconds,
        "operator_verified": False,
        "issue_authorized": False,
        "create_authorized": False,
        "launch_authorized": False,
    }
    request["request_hash"] = sha256_payload(request)
    return request
