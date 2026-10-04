"""One-shot host probe of Kilo against the EA-4E inert loopback provider.

Only run after explicit authorization. This does not prove zero host egress.
"""

from __future__ import annotations

import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time

import win32job

from tools.ea4e92ck_kilo_inert_probe import (
    DUMMY_KEY, InertProviderHandler, MARKER, MODEL, REPO_ROOT,
    pinned_binary, probe_config, probe_env,
)


PROBE_ROOT = Path(r"C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-inert-probe-92ck-20261004")
PROBE_PORT = 49321
SHAPE_PROBE_ROOT = Path(r"C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-shape-probe-92cr-20261004")
SHAPE_PROBE_PORT = 49322
TIMEOUT_SECONDS = 30
MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 128 * 1024


class ProbeRefused(RuntimeError):
    pass


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_plan(plan_path: Path) -> dict:
    """Fail closed if the plan or its credential-free home has drifted."""
    plan_path = Path(plan_path).resolve(strict=True)
    root = plan_path.parent
    if plan_path.name != "launch-plan.json":
        raise ProbeRefused("unexpected probe root or plan")
    if root == PROBE_ROOT.resolve():
        port = PROBE_PORT
    elif root == SHAPE_PROBE_ROOT.resolve():
        port = SHAPE_PROBE_PORT
    else:
        raise ProbeRefused("unexpected probe root or plan")
    if (root / "attempt.json").exists() or (root / "probe-result.json").exists():
        raise ProbeRefused("one-shot probe already claimed")
    plan = json.loads(plan_path.read_text(encoding="ascii"))
    binary, expected_sha = pinned_binary()
    binary = binary.resolve(strict=True)
    if _hash_file(binary) != expected_sha or plan.get("binary_sha256") != expected_sha:
        raise ProbeRefused("pinned binary identity mismatch")
    expected_argv = [str(binary), "run", "--format", "json", "--pure", "--agent",
                     "hermes-ea4e-kilo-receiver", "--model", MODEL,
                     f"Reply with exactly {MARKER}. Do not use tools."]
    if plan.get("argv") != expected_argv or plan.get("cwd") != str(root):
        raise ProbeRefused("inert command or cwd mismatch")
    config_text = json.dumps(probe_config(port), sort_keys=True)
    if (root / "config/kilo.jsonc").read_text(encoding="ascii").strip() != config_text:
        raise ProbeRefused("inert provider config mismatch")
    if plan.get("env") != probe_env(root, binary, config_text):
        raise ProbeRefused("isolated environment mismatch")
    agent_path = (root / "home/.kilo/agents/hermes-ea4e-kilo-receiver/"
                  "hermes-ea4e-kilo-receiver.jsonc")
    agent = json.loads(agent_path.read_text(encoding="ascii"))
    if agent.get("permission") != {"*": "deny"} or agent.get("name") != "hermes-ea4e-kilo-receiver":
        raise ProbeRefused("inert agent policy mismatch")
    if any((root / "home").rglob("kilo.db")):
        raise ProbeRefused("credential database present in probe home")
    if (plan.get("launch_authorized"), plan.get("network_isolation_verified"),
            plan.get("real_provider_calls_authorized")) != (False, False, False):
        raise ProbeRefused("probe plan authority flags changed")
    if plan.get("credential_class") != "DUMMY_LOCAL_ONLY" or DUMMY_KEY not in config_text:
        raise ProbeRefused("inert credential mismatch")
    if REPO_ROOT in root.parents:
        raise ProbeRefused("probe root inside repository")
    return plan


class RecordingServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, InertProviderHandler)
        self.events: list[dict] = []
        self.event_lock = threading.Lock()


def bounded_child(argv: list[str], *, cwd: str, env: dict[str, str], timeout: int) -> dict:
    """Start one child, attach a one-process kill-on-close Windows job, cap pipes."""
    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    basic = limits["BasicLimitInformation"]
    basic["LimitFlags"] |= (win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                            | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS)
    basic["ActiveProcessLimit"] = 1
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    proc = None
    start = time.monotonic()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = threading.Event()
    errors: list[str] = []
    readers: list[threading.Thread] = []
    timed_out = False
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, shell=False,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=False)
        try:
            win32job.AssignProcessToJobObject(job, int(proc._handle))
        except Exception as exc:
            proc.kill()
            proc.wait(timeout=3)
            raise ProbeRefused(f"child could not join one-process job: {type(exc).__name__}") from exc

        def capture(stream, name, limit):
            try:
                while chunk := stream.read(65536):
                    remaining = limit - len(buffers[name])
                    buffers[name].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        overflow.set()
                        win32job.TerminateJobObject(job, 1)
                        break
            except Exception as exc:
                errors.append(type(exc).__name__)
                win32job.TerminateJobObject(job, 1)

        readers = [threading.Thread(target=capture, args=(proc.stdout, "stdout", MAX_STDOUT_BYTES), daemon=True),
                   threading.Thread(target=capture, args=(proc.stderr, "stderr", MAX_STDERR_BYTES), daemon=True)]
        for reader in readers:
            reader.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            win32job.TerminateJobObject(job, 1)
            proc.wait(timeout=3)
        for reader in readers:
            reader.join(timeout=2)
        if any(reader.is_alive() for reader in readers):
            errors.append("capture_reader_unfinished")
        return {
            "pid": proc.pid, "returncode": proc.returncode,
            "timed_out": timed_out, "output_overflowed": overflow.is_set(),
            "capture_errors": errors, "elapsed_seconds": round(time.monotonic() - start, 3),
            "stdout": bytes(buffers["stdout"]), "stderr": bytes(buffers["stderr"]),
        }
    finally:
        if proc is not None and proc.poll() is None:
            win32job.TerminateJobObject(job, 1)
            proc.wait(timeout=3)
        job.Close()


def _exact_text_marker(output: bytes) -> bool:
    for raw_line in output.splitlines():
        try:
            event = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict) and part.get("text") == MARKER:
            return True
    return False


def run_once(plan_path: Path) -> Path:
    plan = validate_plan(plan_path)
    root = Path(plan["cwd"])
    if root != PROBE_ROOT.resolve():
        raise ProbeRefused("fresh shape probe launch requires separate authorization")
    with RecordingServer(("127.0.0.1", PROBE_PORT)) as server:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        claim = root / "attempt.json"
        try:
            with claim.open("x", encoding="ascii") as stream:
                json.dump({"class": "INERT_HOST_PROBE", "plan_sha256": _hash_file(Path(plan_path)),
                           "one_process_budget_consumed": True}, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                result = bounded_child(plan["argv"], cwd=plan["cwd"], env=plan["env"],
                                       timeout=TIMEOUT_SECONDS)
            except Exception as exc:
                result = {"launch_error_type": type(exc).__name__, "returncode": None,
                          "timed_out": False, "output_overflowed": False,
                          "capture_errors": [], "elapsed_seconds": None,
                          "stdout": b"", "stderr": b""}
        finally:
            server.shutdown()
            server_thread.join(timeout=3)
        output = result.pop("stdout")
        error_output = result.pop("stderr")
        report = {
            **result,
            "stdout_bytes": len(output), "stdout_sha256": hashlib.sha256(output).hexdigest(),
            "stderr_bytes": len(error_output), "stderr_sha256": hashlib.sha256(error_output).hexdigest(),
            "exact_text_marker": _exact_text_marker(output),
            "fake_provider_events": list(server.events),
            "fake_completion_request_count": sum(
                event["method"] == "POST" and event["path"] == "/v1/chat/completions"
                for event in server.events
            ),
            "external_egress_verified_absent": False,
            "real_model_invocation_proven_absent": False,
            "production_activation": False,
            "automatic_retry": False,
        }
        report_path = root / "probe-result.json"
        with report_path.open("x", encoding="ascii") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--accept-host-egress-risk", action="store_true", required=True)
    args = parser.parse_args()
    print(run_once(args.plan))


if __name__ == "__main__":
    main()
