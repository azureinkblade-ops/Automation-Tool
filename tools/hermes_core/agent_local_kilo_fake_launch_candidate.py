"""Pure revised Kilo fake-network candidate derived from a reserved v1 plan."""

from copy import deepcopy
import hashlib
import json

from tools.hermes_core.agent_local_kilo_ping_intent import (
    SQLiteAgentLocalKiloPingIntentStore,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.local_kilo_inert_plan import CONFIG_DIR, HOME


GATEWAY_ALIAS = "ea4e-fake-gateway"
GATEWAY_URL = f"http://{GATEWAY_ALIAS}:8181/v1"


def build_agent_local_kilo_fake_launch_candidate(
    intents: SQLiteAgentLocalKiloPingIntentStore,
    attempt_id: str,
    v1_plan: dict,
) -> dict:
    """Revise dummy-only config and workspace policy without modifying v1."""
    if type(intents) is not SQLiteAgentLocalKiloPingIntentStore:
        raise DelegationIntegrityError("Linux Kilo intent store denied")
    intent = intents.verify_plan(attempt_id, v1_plan)
    config_path = f"{CONFIG_DIR}/kilo.jsonc"
    files = deepcopy(v1_plan["planned_files"])
    config = json.loads(files[config_path]["content"])
    config["provider"]["openai-compatible"]["options"]["baseURL"] = GATEWAY_URL
    config_text = json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n"
    files[config_path] = {
        "content": config_text,
        "sha256": hashlib.sha256(config_text.encode("ascii")).hexdigest(),
    }
    run_id = sha256_payload({
        "attempt_id": attempt_id,
        "v1_plan_hash": intent.plan_hash,
    })[:32]
    candidate = {
        "schema_id": "hermes.agent-local-kilo-fake-launch-candidate/v1",
        "attempt_id": attempt_id,
        "v1_plan_hash": intent.plan_hash,
        "v1_intent_payload_sha256": intent.payload_sha256,
        "image_manifest": v1_plan["image_manifest"],
        "image_index": v1_plan["image_index"],
        "platform": v1_plan["platform"],
        "entrypoint": deepcopy(v1_plan["entrypoint"]),
        "argv": deepcopy(v1_plan["argv"]),
        "user": v1_plan["user"],
        "workdir": v1_plan["workdir"],
        "env": deepcopy(v1_plan["env"]),
        "planned_files": files,
        "home_mount": {"destination": HOME, "kind": "isolated_runtime_copy"},
        "workspace_mount": {
            "destination": "/work", "kind": "tmpfs",
            "uid": 65532, "gid": 65532, "mode": "0700",
        },
        "network": {
            "name": f"ea4e-kilo-{run_id}",
            "gateway_alias": GATEWAY_ALIAS,
            "gateway_url": GATEWAY_URL,
            "internal": True,
        },
        "credential_class": "DUMMY_LOCAL_ONLY",
        "source_bytes_prepared": False,
        "effective_config_checked": False,
        "peer_qualified": False,
        "gateway_body_qualified": False,
        "model_qualified": False,
        "launch_authorized": False,
    }
    candidate["candidate_hash"] = sha256_payload(candidate)
    return candidate
