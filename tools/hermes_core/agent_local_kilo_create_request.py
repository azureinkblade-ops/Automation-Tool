"""Pure Docker create request proposal for the dummy local Kilo candidate."""

from decimal import Decimal

from tools.hermes_core.agent_local_kilo_provisional_launch_spec import (
    verify_provisional_kilo_launch_spec,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


def _mount_arg(mount):
    if (type(mount) is not dict or set(mount) !=
            {"type", "source", "target", "read_only"}
            or mount["type"] != "bind"
            or type(mount["source"]) is not str
            or not mount["source"] or "," in mount["source"]
            or type(mount["target"]) is not str
            or not mount["target"].startswith("/")
            or "," in mount["target"]
            or type(mount["read_only"]) is not bool):
        raise DelegationIntegrityError("Kilo create mount denied")
    return (f"type=bind,source={mount['source']},target={mount['target']}"
            + (",readonly" if mount["read_only"] else ""))


def build_provisional_kilo_create_request(
    intents, attempt_id, v1_plan, prepared, spec,
):
    """Build canonical argv but retain explicit no-create/no-start flags."""
    expected = verify_provisional_kilo_launch_spec(
        intents, attempt_id, v1_plan, prepared, spec,
    )
    if (expected["create_authorized"] is not False
            or expected["launch_authorized"] is not False
            or expected["credential_class"] != "DUMMY_LOCAL_ONLY"
            or expected["platform"] != "linux/amd64"
            or type(expected["entrypoint"]) is not list
            or len(expected["entrypoint"]) != 1
            or type(expected["entrypoint"][0]) is not str
            or not expected["entrypoint"][0]):
        raise DelegationIntegrityError("Kilo create proposal authority denied")
    policy = expected["host_policy"]
    if (set(policy) != {
            "nano_cpus", "memory_bytes", "pids_limit", "read_only_rootfs",
            "privileged", "cap_drop", "security_opt", "publish_all_ports",
            "auto_remove", "tmpfs",
        }
            or policy["read_only_rootfs"] is not True
            or policy["privileged"] is not False
            or policy["publish_all_ports"] is not False
            or policy["auto_remove"] is not False
            or policy["cap_drop"] != ["ALL"]
            or policy["security_opt"] != ["no-new-privileges"]
            or type(policy["nano_cpus"]) is not int
            or policy["nano_cpus"] <= 0
            or type(policy["memory_bytes"]) is not int
            or policy["memory_bytes"] <= 0
            or type(policy["pids_limit"]) is not int
            or policy["pids_limit"] <= 0
            or set(policy["tmpfs"]) != {"/work"}):
        raise DelegationIntegrityError("Kilo create host policy denied")
    argv = [
        "container", "create", "--name", expected["container_name"],
        "--pull", "never", "--platform", expected["platform"],
        "--network", expected["network"]["name"],
        "--user", expected["user"], "--workdir", expected["workdir"],
        "--entrypoint", expected["entrypoint"][0],
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--pids-limit", str(policy["pids_limit"]),
        "--memory", str(policy["memory_bytes"]),
        "--cpus", str(Decimal(policy["nano_cpus"]) / Decimal(1_000_000_000)),
        "--restart", "no",
        "--tmpfs", "/work:" + policy["tmpfs"]["/work"],
    ]
    for key, value in sorted(expected["labels"].items()):
        argv.extend(("--label", f"{key}={value}"))
    for key, value in sorted(expected["env"].items()):
        argv.extend(("--env", f"{key}={value}"))
    for mount in expected["mounts"]:
        argv.extend(("--mount", _mount_arg(mount)))
    argv.append(expected["image_index"])
    argv.extend(expected["argv"])
    request = {
        "schema_id": "hermes.agent-local-kilo-create-request/v1",
        "attempt_id": attempt_id,
        "spec_hash": expected["spec_hash"],
        "argv": argv,
        "create_authorized": False,
        "launch_authorized": False,
    }
    request["request_hash"] = sha256_payload(request)
    return request
