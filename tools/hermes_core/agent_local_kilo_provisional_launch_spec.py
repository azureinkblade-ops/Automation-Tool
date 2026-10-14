"""Pure, non-launchable Docker create proposal for the dummy Kilo receiver."""

from tools.hermes_core.agent_local_kilo_fake_inputs import (
    verified_agent_local_kilo_fake_mount_sources,
)
from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.delegated_task import DelegationIntegrityError


HOST_POLICY = {
    "nano_cpus": 2_000_000_000,
    "memory_bytes": 2 * 1024 * 1024 * 1024,
    "pids_limit": 64,
    "read_only_rootfs": True,
    "privileged": False,
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "publish_all_ports": False,
    "auto_remove": False,
    "tmpfs": {
        "/work": "rw,nosuid,nodev,noexec,uid=65532,gid=65532,mode=0700,size=134217728",
    },
}


def build_provisional_kilo_launch_spec(intents, attempt_id, v1_plan, prepared):
    """Bind reviewed dummy inputs and proposed limits; never grant create/start."""
    candidate = build_agent_local_kilo_fake_launch_candidate(
        intents, attempt_id, v1_plan,
    )
    input_source, runtime_source = verified_agent_local_kilo_fake_mount_sources(
        intents, attempt_id, v1_plan, prepared,
    )
    identity = sha256_payload({
        "attempt_id": attempt_id,
        "candidate_hash": candidate["candidate_hash"],
        "input_source": input_source,
        "runtime_source": runtime_source,
    })
    spec = {
        "schema_id": "hermes.agent-local-kilo-provisional-launch-spec/v1",
        "attempt_id": attempt_id,
        "candidate_hash": candidate["candidate_hash"],
        "image_index": candidate["image_index"],
        "image_manifest": candidate["image_manifest"],
        "platform": candidate["platform"],
        "container_name": f"ea4e-kilo-{identity[:32]}",
        "labels": {
            "hermes.ea4e.attempt": attempt_id,
            "hermes.ea4e.candidate_sha256": candidate["candidate_hash"],
            "hermes.ea4e.profile": "FAKE_ONLY_LOCAL_CONTAINER",
        },
        "entrypoint": list(candidate["entrypoint"]),
        "argv": list(candidate["argv"]),
        "user": candidate["user"],
        "workdir": candidate["workdir"],
        "env": dict(candidate["env"]),
        "mounts": [
            {"type": "bind", "source": input_source,
             "target": "/reviewed-input", "read_only": True},
            {"type": "bind", "source": runtime_source,
             "target": candidate["home_mount"]["destination"],
             "read_only": False},
        ],
        "host_policy": {
            **HOST_POLICY,
            "cap_drop": list(HOST_POLICY["cap_drop"]),
            "security_opt": list(HOST_POLICY["security_opt"]),
            "tmpfs": dict(HOST_POLICY["tmpfs"]),
        },
        "network": {
            "name": candidate["network"]["name"],
            "internal": True,
            "gateway_alias": candidate["network"]["gateway_alias"],
        },
        "cleanup_owner": f"ea4e-kilo-owner-{identity[:32]}",
        "credential_class": "DUMMY_LOCAL_ONLY",
        "create_authorized": False,
        "launch_authorized": False,
        "provenance_checked": False,
    }
    spec["spec_hash"] = sha256_payload(spec)
    return spec


def verify_provisional_kilo_launch_spec(
    intents, attempt_id, v1_plan, prepared, spec,
):
    """Reject any altered caller copy and recheck the prepared input bytes."""
    expected = build_provisional_kilo_launch_spec(
        intents, attempt_id, v1_plan, prepared,
    )
    if type(spec) is not dict or spec != expected:
        raise DelegationIntegrityError("provisional Kilo launch spec mismatch")
    return expected
