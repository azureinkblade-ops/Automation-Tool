"""No receiver, network, or provider execution in this plan test."""

import inspect

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
