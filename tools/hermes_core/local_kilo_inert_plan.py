"""Pure, non-launchable Linux Kilo plan for fake-provider qualification."""

from __future__ import annotations

import hashlib
import json

from tools.hermes_core.local_kilo_image_admission import IMAGE_ID, IMAGE_INDEX_ID


AGENT_ID = "hermes-ea4e-kilo-receiver"
MODEL = "openai-compatible/ea4e-inert"
HOME = "/tmp/kilo-home"
CONFIG_DIR = f"{HOME}/config"
DUMMY_KEY = "EA4E_INERT_ONLY"
FAKE_GATEWAY_URL = "http://fake-gateway.invalid/v1"


def build_inert_plan() -> dict:
    """Describe a dummy-only candidate; return no execution authority."""
    agent_profile = {
        "name": AGENT_ID,
        "live_authorized": False,
        "permission": {"*": "deny"},
    }
    provider_config = {
        "model": MODEL,
        "provider": {
            "openai-compatible": {
                "options": {
                    "apiKey": DUMMY_KEY,
                    "baseURL": FAKE_GATEWAY_URL,
                },
                "models": {"ea4e-inert": {"name": "EA-4E inert probe", "tool_call": False}},
            },
        },
    }
    config_text = json.dumps(provider_config, sort_keys=True, separators=(",", ":")) + "\n"
    agent_text = json.dumps(agent_profile, sort_keys=True, separators=(",", ":")) + "\n"
    return {
        "schema_id": "hermes.local-kilo-inert-plan/v1",
        "image_manifest": IMAGE_ID,
        "image_index": IMAGE_INDEX_ID,
        "platform": "linux/amd64",
        "entrypoint": ["/opt/kilo/kilo"],
        "argv": [
            "run", "--format", "json", "--pure", "--agent", AGENT_ID,
            "--model", MODEL, "Reply with exactly EA4E_INERT_OK. Do not use tools.",
        ],
        "workdir": "/work",
        "user": "65532:65532",
        "rootfs_readonly": True,
        "writable_paths": [HOME, "/work"],
        "env": {
            "HOME": HOME,
            "KILO_HOME": HOME,
            "KILO_CONFIG_DIR": CONFIG_DIR,
            "OPENCODE_CONFIG_DIR": CONFIG_DIR,
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "XDG_CONFIG_HOME": CONFIG_DIR,
            "KILO_PURE": "1",
            "OPENCODE_PURE": "1",
            "TMPDIR": f"{HOME}/tmp",
        },
        "agent_profile": agent_profile,
        "provider": {
            "model": MODEL,
            "base_url": FAKE_GATEWAY_URL,
            "api_key": DUMMY_KEY,
        },
        "planned_files": {
            f"{CONFIG_DIR}/kilo.jsonc": {
                "content": config_text,
                "sha256": hashlib.sha256(config_text.encode("ascii")).hexdigest(),
            },
            f"{HOME}/.kilo/agents/{AGENT_ID}/{AGENT_ID}.jsonc": {
                "content": agent_text,
                "sha256": hashlib.sha256(agent_text.encode("ascii")).hexdigest(),
            },
        },
        "config_delivery": "UNRESOLVED_NO_FILES_WRITTEN",
        "network_binding": "UNRESOLVED_FAKE_ONLY",
        "credential_class": "DUMMY_LOCAL_ONLY",
        "launch_authorized": False,
        "receiver_executed": False,
        "model_invoked": False,
    }
