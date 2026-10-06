"""No receiver, network, or provider execution in this plan test."""

import hashlib
import inspect
import json

from tools.hermes_core import local_kilo_inert_plan as subject


def test_inert_plan_is_fixed_and_non_launchable():
    plan = subject.build_inert_plan()
    assert plan == subject.build_inert_plan()
    assert plan["launch_authorized"] is False
    assert plan["receiver_executed"] is False
    assert plan["model_invoked"] is False
    assert plan["platform"] == "linux/amd64"
    assert plan["image_manifest"].startswith("sha256:")
    assert plan["image_index"].startswith("sha256:")
    assert plan["image_manifest"] != plan["image_index"]
    assert plan["entrypoint"] == ["/opt/kilo/kilo"]
    assert plan["argv"][plan["argv"].index("--model") + 1] == subject.MODEL
    assert "--auto" not in plan["argv"]


def test_inert_plan_uses_linux_isolated_paths_and_dummy_provider():
    plan = subject.build_inert_plan()
    assert plan["user"] == "65532:65532"
    assert plan["rootfs_readonly"] is True
    assert plan["writable_paths"] == ["/tmp/kilo-home", "/work"]
    assert plan["workdir"] == "/work"
    assert plan["env"]["HOME"] == "/tmp/kilo-home"
    assert plan["env"]["KILO_CONFIG_DIR"].startswith(plan["env"]["HOME"])
    assert plan["provider"]["base_url"].endswith(".invalid/v1")
    assert plan["provider"]["api_key"] == "EA4E_INERT_ONLY"
    assert plan["credential_class"] == "DUMMY_LOCAL_ONLY"
    assert plan["network_binding"] == "UNRESOLVED_FAKE_ONLY"
    assert not any(key in plan["env"] for key in ("USERPROFILE", "HOMEDRIVE", "SYSTEMROOT"))


def test_inert_plan_agent_denies_everything_and_has_no_runtime_capability():
    plan = subject.build_inert_plan()
    assert plan["agent_profile"]["permission"] == {"*": "deny"}
    assert plan["agent_profile"]["live_authorized"] is False
    source = inspect.getsource(subject).lower()
    assert not any(name in source for name in ("subprocess", "requests", "socket", "popen", "exec("))


def test_planned_config_bytes_are_deterministic_dummy_only_and_not_delivered():
    plan = subject.build_inert_plan()
    assert plan["config_delivery"] == "UNRESOLVED_NO_FILES_WRITTEN"
    assert len(plan["planned_files"]) == 2
    for path, item in plan["planned_files"].items():
        assert path.startswith(subject.HOME + "/")
        assert item["sha256"] == hashlib.sha256(item["content"].encode("ascii")).hexdigest()
        assert item["content"].endswith("\n")

    config = json.loads(plan["planned_files"][f"{subject.CONFIG_DIR}/kilo.jsonc"]["content"])
    provider = config["provider"]["openai-compatible"]
    assert config["model"] == subject.MODEL
    assert provider["options"] == {
        "apiKey": "EA4E_INERT_ONLY",
        "baseURL": "http://fake-gateway.invalid/v1",
    }
    assert provider["models"]["ea4e-inert"]["tool_call"] is False

    agent_path = f"{subject.HOME}/.kilo/agents/{subject.AGENT_ID}/{subject.AGENT_ID}.jsonc"
    agent = json.loads(plan["planned_files"][agent_path]["content"])
    assert agent == plan["agent_profile"]
    assert agent["permission"] == {"*": "deny"}
