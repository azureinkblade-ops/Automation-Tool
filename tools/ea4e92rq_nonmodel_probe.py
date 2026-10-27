"""One-shot, shell-only inspection of the pinned Ollama image.

Run only under an exact authorization. This does not start Ollama or mount a model.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import secrets
import time
from uuid import uuid4

from tools.ea4e92rm_container_smoke import DockerCli, SmokeDenied, _json_object


IMAGE = "ollama/ollama@sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da"
IMAGE_ID = "sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da"
DOCKER = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
DOCKER_SHA256 = "c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c"
CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
MEMORY = 256 * 1024 * 1024
SHELL_CHECK = (
    'for p in /bin/cat /usr/bin/curl; do '
    'if test -x "$p"; then printf "tool:%s:yes\\n" "$p"; '
    'else printf "tool:%s:no\\n" "$p"; fi; done; '
    'while IFS= read -r line; do printf "net:%s\\n" "$line"; '
    'done < /proc/net/dev'
)
BASH_CHECK = (
    'if test -x /bin/bash; then '
    'printf "tool:/bin/bash:yes\\n"; '
    "LC_ALL=C /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/1' 2>&1 || :; "
    'else printf "tool:/bin/bash:no\\n"; fi; '
    'if test -x /bin/cat; then printf "tool:/bin/cat:yes\\n"; '
    'else printf "tool:/bin/cat:no\\n"; fi; '
    'while IFS= read -r line; do printf "net:%s\\n" "$line"; '
    'done < /proc/net/dev'
)


def _object(raw: bytes) -> dict:
    return _json_object(raw)


def run(mode: str = "tools", *, local_log: bool = False,
        json_file_log: bool = False) -> dict:
    if (mode not in ("tools", "bash") or type(local_log) is not bool
            or type(json_file_log) is not bool
            or (local_log and json_file_log)
            or ((local_log or json_file_log) and mode != "bash")):
        raise SmokeDenied("unreviewed non-model probe mode")
    deadline = time.monotonic() + 120
    work_deadline = deadline - 25
    client = DockerCli(DOCKER, DOCKER_SHA256)
    if json_file_log:
        prefix = "ea4e92ud"
    elif local_log:
        prefix = "ea4e92tz"
    else:
        prefix = "ea4e92rq" if mode == "tools" else "ea4e92ry"
    if json_file_log:
        log_driver = "json-file"
    elif local_log:
        log_driver = "local"
    else:
        log_driver = "none"
    log_args = (f"--log-driver={log_driver}",)
    if log_driver != "none":
        log_args += ("--log-opt", "max-size=16k", "--log-opt", "max-file=1")
    expected_log = {"Type": log_driver}
    if log_driver != "none":
        expected_log["Config"] = {"max-size": "16k", "max-file": "1"}
    label = prefix + ".owner"
    name = prefix + "-" + uuid4().hex
    owner = secrets.token_hex(16)
    container_id = None
    create_attempted = False
    cleanup_confirmed = False

    def call(*args: str, cleanup: bool = False) -> bytes:
        remaining = (deadline if cleanup else work_deadline) - time.monotonic()
        if remaining <= 0:
            raise SmokeDenied("probe deadline reached")
        return client.invoke(args, timeout=min(10, remaining))

    def inspect(target: str, *, cleanup: bool = False) -> dict:
        return _object(call("container", "inspect", target, cleanup=cleanup))

    def owned(observed: dict) -> bool:
        return (
            observed.get("Name") == "/" + name
            and (observed.get("Config") or {}).get("Labels", {}).get(label) == owner
            and bool(CONTAINER_ID.fullmatch(observed.get("Id") or ""))
        )

    try:
        image = _object(call("image", "inspect", IMAGE))
        if image.get("Id") != IMAGE_ID or IMAGE not in image.get("RepoDigests", []):
            raise SmokeDenied("pinned image identity mismatch")
        if image.get("Os") != "linux" or image.get("Architecture") != "amd64":
            raise SmokeDenied("image platform mismatch")
        create_attempted = True
        raw_id = call(
            "container", "create", "--pull=never", "--name", name,
            "--label", f"{label}={owner}", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=16", f"--memory={MEMORY}", f"--memory-swap={MEMORY}",
            "--cpus=1", "--restart=no", *log_args,
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=16777216",
            "--env", "NVIDIA_VISIBLE_DEVICES=void", "--entrypoint", "/bin/sh",
            IMAGE, "-c", "sleep 45",
        ).decode("ascii", "strict").strip()
        if not CONTAINER_ID.fullmatch(raw_id):
            raise SmokeDenied("created container ID invalid")
        container_id = raw_id
        observed = inspect(container_id)
        host = observed.get("HostConfig") or {}
        config = observed.get("Config") or {}
        network = observed.get("NetworkSettings") or {}
        valid = (
            owned(observed) and observed.get("Id") == container_id
            and observed.get("Image") == IMAGE_ID and config.get("Image") == IMAGE
            and config.get("Entrypoint") == ["/bin/sh"]
            and config.get("Cmd") == ["-c", "sleep 45"]
            and "NVIDIA_VISIBLE_DEVICES=void" in (config.get("Env") or [])
            and host.get("NetworkMode") == "none"
            and host.get("ReadonlyRootfs") is True
            and host.get("Privileged") is False
            and host.get("Memory") == MEMORY and host.get("MemorySwap") == MEMORY
            and host.get("PidsLimit") == 16 and host.get("NanoCpus") == 1_000_000_000
            and host.get("CapDrop") == ["ALL"] and not host.get("CapAdd")
            and not host.get("Devices") and not host.get("DeviceRequests")
            and any(x in ("no-new-privileges", "no-new-privileges:true")
                    for x in (host.get("SecurityOpt") or []))
            and (host.get("RestartPolicy") or {}).get("Name") == "no"
            and (host.get("LogConfig") == expected_log
                 if log_driver != "none"
                 else (host.get("LogConfig") or {}).get("Type") == "none")
            and host.get("Tmpfs") == {"/tmp": "rw,nosuid,nodev,size=16777216"}
            and not host.get("PortBindings")
            and all(not x for x in (network.get("Ports") or {}).values())
            and set((network.get("Networks") or {}).keys()) == {"none"}
            and not observed.get("Mounts")
            and (observed.get("State") or {}).get("Running") is False
        )
        if not valid:
            raise SmokeDenied("effective prestart restrictions mismatch")
        call("container", "start", container_id)
        observed = inspect(container_id)
        if not owned(observed) or (observed.get("State") or {}).get("Running") is not True:
            raise SmokeDenied("started container identity/state mismatch")
        raw = call("container", "exec", container_id, "/bin/sh", "-c",
                   SHELL_CHECK if mode == "tools" else BASH_CHECK)
        lines = raw.decode("ascii", "strict").splitlines()
        tools = {line for line in lines if line.startswith("tool:")}
        interfaces = {line[4:].split(":", 1)[0].strip()
                      for line in lines if line.startswith("net:") and ":" in line[4:]}
        if interfaces != {"lo"}:
            raise SmokeDenied("non-loopback interface or missing network observation")
        if mode == "bash" and (
                "tool:/bin/bash:yes" not in tools
                or "tool:/bin/cat:yes" not in tools
                or "Connection refused" not in raw.decode("ascii", "strict")):
            raise SmokeDenied("Bash local TCP transport unproven")
        return {"image": IMAGE_ID, "tools": sorted(tools), "interfaces": sorted(interfaces)}
    finally:
        if create_attempted:
            target = container_id or name
            try:
                observed = inspect(target, cleanup=True)
                if not owned(observed) or (container_id and observed.get("Id") != container_id):
                    raise SmokeDenied("cleanup identity mismatch")
                exact_id = observed["Id"]
                call("container", "rm", "--force", exact_id, cleanup=True)
                remaining = call("container", "ls", "-a", "--no-trunc", "--quiet",
                                 "--filter", f"id={exact_id}", cleanup=True)
                cleanup_confirmed = not remaining.strip()
            except Exception as error:
                raise SmokeDenied("exact container cleanup unconfirmed") from error
            if not cleanup_confirmed:
                raise SmokeDenied("exact container cleanup unconfirmed")


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
