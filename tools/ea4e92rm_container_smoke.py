"""Single-shot, non-default Docker-local Ollama smoke candidate.

This module has no CLI entry point. Calling ``run_smoke`` starts a real
container and model; it requires a separately reviewed, exact authorization.
Fake tests of this module do not qualify Docker, the image, or the model.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from typing import Protocol
from uuid import UUID


IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
CONTAINER_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
MAX_CLI_OUTPUT = 1024 * 1024
MAX_RESPONSE = 64 * 1024
WALL_SECONDS = 120
WORK_SECONDS = 90
EXPECTED_MODEL_FILES = (
    ("manifests/registry.ollama.ai/library/qwen3/14b",
     "bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8"),
    *tuple(("blobs/sha256-" + digest, digest) for digest in (
        "78b3b822087d5199783c8203553a5a92ce5eb7b683a5a81003f8efea9b399d74",
        "a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e",
        "ae370d884f108d16e7cc8fd5259ebc5773a0afa6e078b11f4ed7e39a27e0dfc4",
        "d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12",
        "cff3f395ef3756ab63e58b0ad1b32bb6f802905cae1472e6a12034e4246fbbdb",
    )),
)


class SmokeDenied(RuntimeError):
    """The preflight or bounded smoke did not establish a pass."""


class UnknownContainerOutcome(RuntimeError):
    """The exact container's creation or cleanup needs reconciliation."""


@dataclass(frozen=True)
class SmokePlan:
    image: str
    image_id: str
    models_root: Path
    ceremony_id: str
    model: str = "qwen3:14b"
    memory_bytes: int = 20 * 1024**3
    pids_limit: int = 64

    @property
    def name(self) -> str:
        return "ea4e92rm-" + UUID(self.ceremony_id).hex


class DockerBoundary(Protocol):
    def invoke(self, args: tuple[str, ...], *, timeout: float,
               stdin: bytes = b"", output_limit: int = MAX_CLI_OUTPUT) -> bytes: ...


class DockerCli:
    """Bounded CLI transport. The Docker daemon remains a separate trust boundary."""

    def __init__(self, binary: Path, expected_sha256: str):
        self.binary = str(binary.resolve(strict=True))
        if (_hash_file(Path(self.binary)) != expected_sha256
                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
            raise SmokeDenied("Docker CLI identity mismatch")

    def invoke(self, args: tuple[str, ...], *, timeout: float,
               stdin: bytes = b"", output_limit: int = MAX_CLI_OUTPUT) -> bytes:
        if not 0 < timeout <= WALL_SECONDS or not 0 < output_limit <= MAX_CLI_OUTPUT:
            raise ValueError("invalid Docker CLI bound")
        process = subprocess.Popen(
            (self.binary, "--host", LOCAL_DOCKER_HOST, *args), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")},
        )
        output = bytearray()
        errors = bytearray()
        exceeded = threading.Event()
        total_lock = threading.Lock()

        def read(stream, target):
            try:
                while chunk := stream.read(16384):
                    with total_lock:
                        remaining = output_limit - len(output) - len(errors)
                        target.extend(chunk[:max(0, remaining)])
                        overflow = len(chunk) > remaining
                    if overflow:
                        exceeded.set()
                        try:
                            process.kill()
                        except OSError:
                            pass
                        return
            except OSError:
                exceeded.set()
                try:
                    process.kill()
                except OSError:
                    pass

        readers = (
            threading.Thread(target=read, args=(process.stdout, output), daemon=True),
            threading.Thread(target=read, args=(process.stderr, errors), daemon=True),
        )
        for reader in readers:
            reader.start()
        try:
            if stdin:
                process.stdin.write(stdin)
            process.stdin.close()
            process.wait(timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            try:
                process.kill()
            except OSError:
                pass
            process.wait(timeout=3)
            raise SmokeDenied("Docker CLI write or deadline failed") from error
        finally:
            for reader in readers:
                reader.join(timeout=2)
        if any(reader.is_alive() for reader in readers) or exceeded.is_set():
            raise SmokeDenied("Docker CLI output bound failed")
        if process.returncode != 0:
            raise SmokeDenied("Docker CLI command failed")
        return bytes(output)


def _hash_file(path: Path, *, deadline: float | None = None,
               clock=time.monotonic) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if deadline is not None:
                _remaining(deadline, clock)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _plain_file(path: Path, root: Path) -> bool:
    if not path.is_file() or path.is_symlink() or root not in path.parents:
        return False
    current = path
    while current != root:
        if current.is_symlink():
            return False
        if os.name == "nt" and current.stat(follow_symlinks=False).st_file_attributes & 0x400:
            return False
        current = current.parent
    return not root.is_symlink()


def _plain_directory(path: Path, root: Path) -> bool:
    if not path.is_dir() or path.is_symlink() or root not in path.parents:
        return False
    if os.name == "nt" and path.stat(follow_symlinks=False).st_file_attributes & 0x400:
        return False
    return True


def _walk_error(error):
    raise SmokeDenied("model inventory traversal failed") from error


def validate_plan(plan: SmokePlan, *, deadline: float | None = None,
                  clock=time.monotonic) -> Path:
    if type(plan) is not SmokePlan or not IMAGE_RE.fullmatch(plan.image):
        raise SmokeDenied("digest-pinned image required")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", plan.image_id):
        raise SmokeDenied("exact image ID required")
    try:
        UUID(plan.ceremony_id)
    except (ValueError, TypeError) as error:
        raise SmokeDenied("fresh ceremony UUID required") from error
    if (plan.model != "qwen3:14b" or plan.memory_bytes != 20 * 1024**3
            or plan.pids_limit != 64):
        raise SmokeDenied("unreviewed model or resource budget")
    root = plan.models_root.resolve(strict=True)
    if root != plan.models_root or root.is_symlink() or not root.is_dir():
        raise SmokeDenied("model root identity mismatch")
    names = {name for name, _ in EXPECTED_MODEL_FILES}
    if len(names) != 6:
        raise SmokeDenied("reviewed model inventory invalid")
    observed_names = set()
    for current_root, directories, files in os.walk(
            root, followlinks=False, onerror=_walk_error):
        for directory in directories:
            if not _plain_directory(Path(current_root) / directory, root):
                raise SmokeDenied("model directory reparse point")
        for file_name in files:
            observed_names.add((Path(current_root) / file_name).relative_to(root).as_posix())
    if observed_names != names:
        raise SmokeDenied("model root contains missing or unrelated files")
    for name, expected in EXPECTED_MODEL_FILES:
        candidate = root / name
        if (not _plain_file(candidate, root)
                or _hash_file(candidate, deadline=deadline, clock=clock) != expected):
            raise SmokeDenied("model file identity mismatch")
    return root


def _json_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeDenied("Docker JSON invalid") from error
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise SmokeDenied("Docker inspect shape invalid")
    return value[0]


def _remaining(deadline: float, clock) -> float:
    remaining = deadline - clock()
    if remaining <= 0:
        raise SmokeDenied("smoke deadline reached")
    return min(remaining, WALL_SECONDS)


def _inspect(client: DockerBoundary, container_id: str, deadline: float, clock) -> dict:
    return _json_object(client.invoke(
        ("container", "inspect", container_id), timeout=_remaining(deadline, clock)))


def _owned(observed: dict, plan: SmokePlan, container_id: str,
           owner_token: str) -> bool:
    return (
        observed.get("Id") == container_id
        and observed.get("Name") == "/" + plan.name
        and (observed.get("Config") or {}).get("Labels", {}).get("ea4e92rm.owner")
        == owner_token
    )


def _verify_container(observed: dict, plan: SmokePlan, container_id: str,
                      owner_token: str, *, running: bool) -> None:
    host = observed.get("HostConfig") or {}
    config = observed.get("Config") or {}
    state = observed.get("State") or {}
    mounts = observed.get("Mounts") or []
    network = observed.get("NetworkSettings") or {}
    expected_mount = str(plan.models_root)
    environment = set(config.get("Env") or [])
    valid = (
        _owned(observed, plan, container_id, owner_token)
        and observed.get("Image") == plan.image_id
        and config.get("Image") == plan.image
        and config.get("Cmd") == ["serve"]
        and config.get("Entrypoint") == ["/bin/ollama"]
        and host.get("NetworkMode") == "none"
        and host.get("ReadonlyRootfs") is True
        and host.get("Privileged") is False
        and host.get("Memory") == plan.memory_bytes
        and host.get("MemorySwap") == plan.memory_bytes
        and host.get("PidsLimit") == plan.pids_limit
        and host.get("NanoCpus") == 4_000_000_000
        and host.get("CapDrop") == ["ALL"]
        and not host.get("CapAdd")
        and not host.get("Devices")
        and not host.get("DeviceRequests")
        and any(option in ("no-new-privileges", "no-new-privileges:true")
                for option in (host.get("SecurityOpt") or []))
        and (host.get("RestartPolicy") or {}).get("Name") == "no"
        and (host.get("LogConfig") or {}).get("Type") == "none"
        and host.get("Tmpfs") == {"/tmp": "rw,nosuid,nodev,size=2147483648"}
        and not host.get("PortBindings")
        and all(not value for value in (network.get("Ports") or {}).values())
        and set((network.get("Networks") or {}).keys()) == {"none"}
        and {"HOME=/tmp", "OLLAMA_MODELS=/models",
             "OLLAMA_HOST=127.0.0.1:11434", "OLLAMA_KEEP_ALIVE=0"}
        <= environment
        and not any(entry.upper().startswith(("HTTP_PROXY=", "HTTPS_PROXY=",
                                              "ALL_PROXY=", "NO_PROXY="))
                    for entry in environment)
        and len(mounts) == 1
        and mounts[0].get("Type") == "bind"
        and mounts[0].get("Source") == expected_mount
        and mounts[0].get("Destination") == "/models"
        and mounts[0].get("RW") is False
        and state.get("Running") is running
    )
    if not valid:
        raise SmokeDenied("effective container containment mismatch")


def _create_args(plan: SmokePlan, root: Path, owner_token: str) -> tuple[str, ...]:
    return (
        "container", "create", "--pull=never", "--name", plan.name,
        "--label", "ea4e92rm.owner=" + owner_token,
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=64",
        f"--memory={plan.memory_bytes}", f"--memory-swap={plan.memory_bytes}",
        "--cpus=4", "--restart=no", "--log-driver=none",
        "--mount", f"type=bind,source={root},target=/models,readonly",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=2147483648",
        "--env", "HOME=/tmp", "--env", "OLLAMA_MODELS=/models",
        "--env", "OLLAMA_HOST=127.0.0.1:11434",
        "--env", "OLLAMA_KEEP_ALIVE=0", "--entrypoint", "/bin/ollama",
        plan.image, "serve",
    )


def run_smoke(plan: SmokePlan, client: DockerBoundary, *, clock=time.monotonic) -> str:
    """Run one synthetic request, then stop only its exact owned container.

    Do not call without a new exact authorization for this container envelope.
    No retry follows an uncertain create or cleanup outcome.
    """
    deadline = clock() + WALL_SECONDS
    work_deadline = deadline - (WALL_SECONDS - WORK_SECONDS)
    root = validate_plan(plan, deadline=work_deadline, clock=clock)
    _remaining(work_deadline, clock)
    owner_token = secrets.token_hex(16)
    image = _json_object(client.invoke(
        ("image", "inspect", plan.image), timeout=_remaining(work_deadline, clock)))
    if (image.get("Id") != plan.image_id
            or plan.image not in (image.get("RepoDigests") or [])):
        raise SmokeDenied("local image identity mismatch")

    container_id = None
    verified_owner = False
    creation_attempted = False
    try:
        creation_attempted = True
        created = client.invoke(_create_args(plan, root, owner_token),
                                timeout=_remaining(work_deadline, clock))
        candidate = created.decode("ascii", "strict").strip()
        if not CONTAINER_RE.fullmatch(candidate):
            raise UnknownContainerOutcome("container creation identity unknown")
        container_id = candidate
        observed = _inspect(client, container_id, work_deadline, clock)
        if not _owned(observed, plan, container_id, owner_token):
            raise UnknownContainerOutcome("created container ownership unproven")
        verified_owner = True
        _verify_container(observed, plan, container_id, owner_token, running=False)
        client.invoke(("container", "start", container_id),
                      timeout=_remaining(work_deadline, clock))
        _verify_container(_inspect(client, container_id, work_deadline, clock),
                          plan, container_id, owner_token, running=True)

        interfaces = client.invoke(
            ("container", "exec", container_id, "/bin/cat", "/proc/net/dev"),
            timeout=_remaining(work_deadline, clock))
        names = {line.split(":", 1)[0].strip() for line in
                 interfaces.decode("ascii", "strict").splitlines()[2:] if ":" in line}
        if names != {"lo"}:
            raise SmokeDenied("container has non-loopback interface")

        client.invoke(("container", "exec", container_id, "/usr/bin/curl",
                       "--noproxy", "*", "--fail", "--silent", "--show-error",
                       "--max-time", "5", "http://127.0.0.1:11434/api/version"),
                      timeout=min(7, _remaining(work_deadline, clock)))

        request = json.dumps({
            "model": plan.model, "prompt": "Reply with exactly EA4E_LOCAL_SMOKE_OK.",
            "stream": False, "options": {"num_predict": 32},
        }, separators=(",", ":")).encode("ascii")
        raw = client.invoke(
            ("container", "exec", "--interactive", container_id,
             "/usr/bin/curl", "--noproxy", "*", "--fail", "--silent",
             "--show-error", "--max-time", "100", "--request", "POST",
             "--header", "Content-Type: application/json", "--data-binary", "@-",
             "http://127.0.0.1:11434/api/generate"),
            timeout=_remaining(work_deadline, clock), stdin=request,
            output_limit=MAX_RESPONSE)
        try:
            answer = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SmokeDenied("model response invalid") from error
        if (type(answer) is not dict or answer.get("model") != plan.model
                or answer.get("done") is not True
                or type(answer.get("response")) is not str):
            raise SmokeDenied("model response contract mismatch")
        validate_plan(plan, deadline=work_deadline, clock=clock)
        return answer["response"]
    except BaseException as error:
        if creation_attempted and container_id is None:
            try:
                observed = _json_object(client.invoke(
                    ("container", "inspect", plan.name),
                    timeout=_remaining(deadline, clock)))
                candidate = observed.get("Id")
                if (not isinstance(candidate, str)
                        or not CONTAINER_RE.fullmatch(candidate)
                        or not _owned(observed, plan, candidate, owner_token)):
                    raise UnknownContainerOutcome("creation ownership unproven")
                container_id = candidate
                verified_owner = True
            except BaseException:
                raise UnknownContainerOutcome(
                    "container creation requires reconciliation") from error
            raise UnknownContainerOutcome(
                "container creation failed after owned resource appeared") from error
        raise
    finally:
        if container_id is not None:
            try:
                if not verified_owner:
                    observed = _inspect(client, container_id, deadline, clock)
                    if not _owned(observed, plan, container_id, owner_token):
                        raise UnknownContainerOutcome("cleanup ownership unproven")
                try:
                    client.invoke(("container", "kill", container_id),
                                  timeout=min(5, _remaining(deadline, clock)))
                except SmokeDenied:
                    # A never-started or already-exited owned container also
                    # rejects kill. Inspect still must prove it is stopped.
                    pass
                observed = _inspect(client, container_id, deadline, clock)
                if (not _owned(observed, plan, container_id, owner_token)
                        or (observed.get("State") or {}).get("Running") is not False):
                    raise UnknownContainerOutcome("owned container did not stop")
            except Exception as error:
                raise UnknownContainerOutcome(
                    "owned container cleanup requires reconciliation") from error
