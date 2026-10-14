"""Pure, non-authorizing request for a future Kilo create-only issuer."""

import re

from tools.hermes_core.agent_local_kilo_create_request import (
    build_provisional_kilo_create_request,
)
from tools.hermes_core.agent_local_kilo_ping_intent import (
    SQLiteAgentLocalKiloPingIntentStore,
)
from tools.hermes_core.kilo_fake_gateway_probe_plan import (
    GATEWAY_IMAGE, GATEWAY_INDEX_ID, GATEWAY_PLATFORM_MANIFEST,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ENGINE = "npipe:////./pipe/dockerDesktopLinuxEngine"


def build_kilo_create_issue_request(
    intents, attempt_id, v1_plan, prepared, spec, *,
    governing_commit, docker_executable_sha256, network_id, gateway_id,
    operator_id, nonce, requested_ttl_seconds,
):
    """Bind reported identities; never verify ownership or issue a permit."""
    if type(intents) is not SQLiteAgentLocalKiloPingIntentStore:
        raise DelegationIntegrityError("Kilo create issuer request intent denied")
    intent = intents.verify_plan(attempt_id, v1_plan)
    create_request = build_provisional_kilo_create_request(
        intents, attempt_id, v1_plan, prepared, spec,
    )
    for value in (
        governing_commit, docker_executable_sha256, network_id, gateway_id,
    ):
        if type(value) is not str or not _HEX.fullmatch(value):
            raise DelegationIntegrityError("Kilo create issuer request identity denied")
    if (type(operator_id) is not str or not operator_id.strip()
            or type(nonce) is not str or not nonce.strip()
            or type(requested_ttl_seconds) is not int
            or not 0 < requested_ttl_seconds <= 300):
        raise DelegationIntegrityError("Kilo create issuer request input denied")
    request = {
        "schema_id": "hermes.agent-local-kilo-create-issue-request/v2",
        "attempt_id": attempt_id,
        "intent_hash": intent.payload_sha256,
        "candidate_hash": spec["candidate_hash"],
        "spec_hash": spec["spec_hash"],
        "create_request_hash": create_request["request_hash"],
        "governing_commit": governing_commit,
        "docker_executable_sha256": docker_executable_sha256,
        "docker_engine_endpoint": _ENGINE,
        "image_index": spec["image_index"],
        "image_manifest": spec["image_manifest"],
        "container_name": spec["container_name"],
        "network_name": spec["network"]["name"],
        "network_id": network_id,
        "gateway_id": gateway_id,
        "gateway_image": GATEWAY_IMAGE,
        "gateway_image_index": GATEWAY_INDEX_ID,
        "gateway_image_manifest": GATEWAY_PLATFORM_MANIFEST,
        "operator_id": operator_id,
        "nonce": nonce,
        "requested_ttl_seconds": requested_ttl_seconds,
        "operator_verified": False,
        "network_ownership_verified": False,
        "gateway_ownership_verified": False,
        "issue_authorized": False,
        "create_authorized": False,
        "launch_authorized": False,
    }
    request["request_hash"] = sha256_payload(request)
    return request
